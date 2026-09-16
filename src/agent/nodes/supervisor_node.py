"""
supervisor_node
===============
Phase 1 — Semantic cache gate (fast-path return when query was seen before).
Phase 2 — Deterministic keyword routing (greetings/follow-ups skip LLM call).
Phase 3 — LLM intent classification (one Gemini call, JSON output).
Phase 4 — Schema retrieval via pgvector (only for data/schema intents).

Does NOT generate SQL. Does NOT execute queries.
"""
from __future__ import annotations

import json
from typing import Any

from agent.state import GlobalState
from app.config import get_settings
from db.postgres import get_shared_pool
from services.schema_rag import retrieve_schema_context, schema_rag_service
from services.semantic_cache import get_semantic_cache
from services.session_memory import append_session_event, get_session_history
from services.conversation_context import build_conversation_context, format_context_for_model
from services.request_requirements import (
    is_schema_visualization_request,
    requested_visualizations_from_prompt,
    resolve_followup_visualizations,
)
from services.task_ledger import build_task_ledger, finalize_task_ledger
from services.request_compiler import compile_request
from services.execution_control import schema_fingerprint
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# System prompt — intent classification
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are WonderDB Agent, a database analytics assistant and intent classifier.
Analyze the user's message and return a single JSON object with these exact fields:

{
  "intent": "query" | "schema" | "chat" | "contextual" | "error",
  "visualizations": [],
  "needs_explanation": true | false
}

═══════════════════════════════════════════════════
INTENT CLASSIFICATION RULES
═══════════════════════════════════════════════════

── DATA QUERY (intent="query") ──────────────────
Trigger: User asks a measurable/quantitative question about the database data.
Examples:
  • "Show me total revenue by month"
  • "Who are the top 10 customers by spend?"
  • "What is the average order value this quarter?"
  • "How many orders were placed last week?"
Visualizations: Select chart types that best fit the data shape:
  • Trend over time             → "line_chart"
  • Comparison across groups   → "bar_chart"
  • Part-of-whole distribution → "pie_chart"
  • Two numeric dimensions     → "scatter_chart"
  • Explicit process/workflow/schema-flow request → "process_flow"
    - State-transition columns produce a state flow.
    - Ordered-step columns produce a workflow.
    - Otherwise, real foreign keys produce a schema relationship flow.
    - Never show the AI agent's internal execution pipeline as the user's process.
  • Explicit decision-tree request → "decision_tree" only when the data contains
    an explicit rule hierarchy or labeled outcomes suitable for classification.
  Only include a chart type if it genuinely adds insight.
  Never infer process or decision diagrams from ordinary time-series/category rows.
  Empty list [] is valid when the data is best shown as a table.
needs_explanation: true

── SCHEMA ONLY (intent="schema") ─────────────────
Trigger: User asks ONLY about table structure, relationships, or wants a diagram.
No data values are needed — no SQL will be executed.
Examples:
  • "Show the ER diagram"
  • "What tables exist in the database?"
  • "How are orders and customers related?"
Visualizations: Include "er_diagram" if user explicitly requests it or it is implied.
If the user explicitly asks for a schema/data flow, also include "process_flow";
it will be grounded in foreign-key direction rather than invented business steps.
needs_explanation: true

── CHAT (intent="chat") ─────────────────────────
Trigger: Greeting, small talk, or help requests — no database interaction needed.
Examples:
  • "Hi", "Hello", "Hey", "Good morning"
  • "What can you do?", "Help", "How does this work?"
  • "Thanks!", "That's great"
  • Any message that is NOT about data or schema
Visualizations: [] (always empty)
needs_explanation: false

── CONTEXTUAL (intent="contextual") ─────────────
Trigger: Follow-up that references the previous response without requesting new data.
Examples:
  • "Explain that in simpler terms"
  • "Can you elaborate?"
  • "Tell me more", "Continue"
  • "What does that mean for the business?"
Visualizations: [] (always empty)
needs_explanation: true

── ERROR (intent="error") ────────────────────────
Trigger: Query is malformed, ambiguous beyond interpretation, or asks for something
the agent fundamentally cannot do (e.g. write data, delete rows, access external URLs).
Examples:
  • "DELETE all orders" — DML not allowed
  • "asdf xyz 123" — unintelligible
  • "Buy me a coffee" — unrelated to database
Visualizations: []
needs_explanation: false

═══════════════════════════════════════════════════
OUTPUT RULES
═══════════════════════════════════════════════════
- Output ONLY valid JSON. No markdown fences. No explanation text.
- The "visualizations" array must contain only values from this allowed set:
  ["bar_chart", "line_chart", "pie_chart", "scatter_chart",
   "er_diagram", "process_flow", "decision_tree"]
- Never include duplicate visualization types.
- Include every visualization explicitly requested by the user.
- Always set needs_explanation=true for query and schema intents.
"""


_MAX_PROMPT_CHARS = 2000


def _cached_payload_satisfies_visualizations(
    cached: dict[str, Any],
    required: list[str],
) -> bool:
    """Reject semantically similar cache hits missing newly requested artifacts."""
    if not required:
        return True
    cached_charts = cached.get("chart_specs") or (
        [cached["chart_spec"]] if cached.get("chart_spec") else []
    )
    cached_diagrams = cached.get("diagram_spec") or []
    if isinstance(cached_diagrams, dict):
        cached_diagrams = [cached_diagrams]
    delivered = {
        f"{chart.get('type')}_chart"
        for chart in cached_charts
        if chart.get("type") in {"bar", "line", "pie", "scatter"}
    }
    diagram_names = {
        "er": "er_diagram",
        "process": "process_flow",
        "decision": "decision_tree",
    }
    delivered.update(
        diagram_names[diagram.get("diagram_type")]
        for diagram in cached_diagrams
        if diagram.get("diagram_type") in diagram_names
    )
    return set(required).issubset(delivered)


# ─────────────────────────────────────────────────────────────────────────────
# LLM call
# ─────────────────────────────────────────────────────────────────────────────

async def _classify_intent(
    prompt: str,
    api_key: str,
    model: str,
    conversation_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Single Gemini API call to classify intent and build an orchestration plan.
    Returns a dict with {intent, visualizations, needs_explanation} or None on failure.
    """
    try:
        import httpx

        clean_model = model.strip()
        if clean_model.startswith("models/"):
            clean_model = clean_model[len("models/"):]

        # NOTE: user prompt is placed in a clearly delimited section to reduce
        # prompt-injection risk — the model sees its own instructions first.
        context_block = format_context_for_model(conversation_context or {})
        user_content = (
            "Conversation dependency (trusted application context):\n"
            f"<conversation_context>\n{context_block}\n</conversation_context>\n\n"
            f"Current user message to classify:\n<user_message>\n{prompt}\n</user_message>\n\n"
            "A data follow-up requires query intent and new SQL. An explanation "
            "follow-up requires contextual intent. Preserve explicit visualizations."
        )

        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{_SYSTEM_PROMPT}\n\n{user_content}"}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
                "maxOutputTokens": 256,
            },
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{clean_model}:generateContent?key={api_key}"
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                logger.warning("Gemini intent classification returned %s: %s", res.status_code, res.text[:200])
                return None

            data = res.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Defensive strip of any accidental markdown fence
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1]
                raw_text = raw_text.rsplit("```", 1)[0].strip()

            plan = json.loads(raw_text)

            # Validate and sanitise the response
            allowed_intents = {"query", "schema", "chat", "contextual", "error"}
            allowed_viz = {
                "bar_chart", "line_chart", "pie_chart", "scatter_chart",
                "er_diagram", "process_flow", "decision_tree",
            }
            plan["intent"] = plan.get("intent", "query") if plan.get("intent") in allowed_intents else "query"
            raw_viz = plan.get("visualizations", [])
            planned_viz = [v for v in raw_viz if v in allowed_viz]
            explicit_viz = requested_visualizations_from_prompt(prompt)
            plan["visualizations"] = list(dict.fromkeys(planned_viz + explicit_viz))
            plan["needs_explanation"] = bool(plan.get("needs_explanation", True))

            return plan

    except Exception as exc:
        logger.warning("Intent classification failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────

async def supervisor_node(state: GlobalState) -> GlobalState:
    """
    Orchestration entry point. Executes in four phases:

    1. Input validation & prompt length guard
    2. Deterministic fast-path for trivial chat/contextual inputs
    3. Semantic cache gate — return instantly if cached
    4. Schema retrieval + LLM intent classification
    """
    prompt = state.get("prompt", "").strip()
    tenant_id = state.get("tenant_id", "default-tenant")
    session_id = state.get("session_id", f"session-{tenant_id}")
    settings = get_settings()
    cache_enabled = state.get("enable_cache", settings.enable_semantic_cache)

    # ── 1. Prompt validation ────────────────────────────────────────────────
    logger.info(f"Supervisor starting for session {session_id} with prompt: {prompt!r}")
    if not prompt:
        return {
            "supervisor_plan": {"intent": "error", "visualizations": [], "needs_explanation": False},
            "has_fatal_error": True,
            "error_detail": "",
            "current_phase": "planning_complete",
        }

    # Truncate silently if over limit (API caller should enforce this too)
    if len(prompt) > _MAX_PROMPT_CHARS:
        prompt = prompt[:_MAX_PROMPT_CHARS]

    history = [
        event for event in await get_session_history(session_id, limit=20)
        if event.get("tenant_id") == tenant_id
    ]
    conversation_context = build_conversation_context(history, prompt)
    resolved_prompt = conversation_context.get("resolved_prompt", prompt)
    schema_prompt = conversation_context.get("schema_prompt", prompt)
    cache_prompt = resolved_prompt
    explicit_visualizations = requested_visualizations_from_prompt(prompt)
    schema_visualization_only = is_schema_visualization_request(prompt)
    current_schema_fingerprint = schema_fingerprint(schema_rag_service._live_catalog)

    # ── 3. Semantic cache gate ──────────────────────────────────────────────
    if cache_enabled:
        try:
            cached = await get_semantic_cache(
                cache_prompt,
                tenant_id,
                exact_only=conversation_context.get("is_followup", False),
                schema_fingerprint=current_schema_fingerprint,
            )
        except Exception as exc:
            logger.warning("Semantic cache lookup failed, proceeding without cache: %s", exc)
            cached = None

        if cached and not _cached_payload_satisfies_visualizations(
            cached, explicit_visualizations,
        ):
            logger.info(
                "Semantic cache hit rejected because requested visualizations are missing"
            )
            cached = None

        if cached:
            cached_charts = cached.get("chart_specs") or (
                [cached["chart_spec"]] if cached.get("chart_spec") else []
            )
            cached_diagrams = cached.get("diagram_spec", [])
            await append_session_event(session_id, {
                "phase": "summary", "prompt": prompt,
                "tenant_id": tenant_id,
                "sql_query": cached.get("sql_query", ""),
                "summary": cached.get("summary", ""),
                "rows_count": len(cached.get("raw_results", [])),
                "result_sample": cached.get("raw_results", [])[:5],
                "chart_type": cached_charts[0].get("type") if cached_charts else None,
                "chart_types": [chart.get("type") for chart in cached_charts],
                "diagram_types": [diagram.get("diagram_type") for diagram in cached_diagrams],
                "cache_hit": True,
            })
            # Reconstruct visualizations list from cached chart/diagram specs
            viz: list[dict] = []
            viz.extend(cached_charts)
            for d in cached_diagrams:
                viz.append(d)
            cached_plan = cached.get("supervisor_plan") or {
                "intent": "query",
                "visualizations": explicit_visualizations,
                "needs_explanation": bool(cached.get("summary")),
            }
            cached_compiled_request = cached.get("compiled_request") or compile_request(
                prompt, conversation_context, cached_plan,
            )
            cached_task_ledger = cached.get("task_ledger") or finalize_task_ledger(
                build_task_ledger(cached_plan, prompt),
                sql_query=cached.get("sql_query", ""),
                raw_data=cached.get("raw_results", []),
                visualizations=viz,
                summary=cached.get("summary", ""),
                data_analysis=cached.get("data_analysis", {}),
                schema_available=bool(current_schema_fingerprint),
                verification=cached.get("response_verification", {}),
                tool_calls=[],
            )

            return {
                "cached_hit": True,
                "sql_query": cached.get("sql_query", ""),
                "clean_dataset": cached.get("raw_results", []),
                "data_analysis": cached.get("data_analysis", {}),
                "response_verification": cached.get("response_verification", {}),
                "summary": cached.get("summary", ""),
                "visualizations": viz,
                "has_fatal_error": False,
                "error_detail": "",
                # Cache hit bypasses all workers; supervisor_plan not used for routing
                "supervisor_plan": cached_plan,
                "current_phase": "planning_complete",
                "resolved_prompt": resolved_prompt,
                "cache_prompt": cache_prompt,
                "conversation_context": conversation_context,
                "schema_fingerprint": current_schema_fingerprint,
                "execution_status": "complete",
                "execution_trace": [{"phase": "cache", "status": "hit"}],
                "compiled_request": cached_compiled_request,
                "task_ledger": cached_task_ledger,
            }

    # ── 4a. Schema retrieval ────────────────────────────────────────────────
    try:
        pool = await get_shared_pool()
        retrieved_schemas = await retrieve_schema_context(
            schema_prompt,
            tenant_id,
            pool,
            prefer_full_catalog=(
                schema_visualization_only
                or "er_diagram" in explicit_visualizations
            ),
            fallback_to_catalog=True,
        )
    except Exception as exc:
        logger.error("Schema retrieval failed: %s", exc)
        retrieved_schemas = []
    current_schema_fingerprint = schema_fingerprint(
        schema_rag_service._live_catalog or retrieved_schemas
    )

    # ── 4b. LLM intent classification ──────────────────────────────────────
    if schema_visualization_only:
        # Schema visualization is fully deterministic and should not disappear
        # because an intent-model call is slow, unavailable, or malformed.
        plan = {
            "intent": "schema",
            "visualizations": explicit_visualizations,
            "needs_explanation": True,
        }
    elif not settings.gemini_api_key or not settings.gemini_model:
        logger.error("Gemini API key or model not configured — cannot classify intent")
        return {
            "cached_hit": False,
            "retrieved_schemas": retrieved_schemas,
            "supervisor_plan": {"intent": "error", "visualizations": [], "needs_explanation": False},
            "has_fatal_error": True,
            "error_detail": "LLM configuration missing.",
            "current_phase": "planning_failed",
        }

    else:
        plan = await _classify_intent(
            prompt=prompt,
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            conversation_context=conversation_context,
        )

    if not plan:
        # Fallback: treat as a query so user gets a best-effort response
        logger.warning("Intent classification returned None — defaulting to query intent")
        plan = {
            "intent": "query",
            "visualizations": explicit_visualizations,
            "needs_explanation": True,
        }

    plan["visualizations"] = resolve_followup_visualizations(
        prompt,
        conversation_context,
        plan.get("visualizations", []),
    )

    followup_kind = conversation_context.get("followup_kind")
    if schema_visualization_only:
        plan["intent"] = "schema"
    elif followup_kind == "data":
        plan["intent"] = "query"
        plan["needs_explanation"] = True
    elif followup_kind == "explanation":
        plan["intent"] = "contextual"
        plan["visualizations"] = []
        plan["needs_explanation"] = True

    compiled_request = compile_request(prompt, conversation_context, plan, retrieved_schemas)
    planning_error = ""
    if compiled_request["operation"] == "rejected_write":
        plan = {"intent": "error", "visualizations": [], "needs_explanation": False}
        compiled_request["intent"] = "error"
        compiled_request["requested_artifacts"] = []
        planning_error = "Only read-only database requests are allowed."
    task_ledger = build_task_ledger(plan, prompt)

    await append_session_event(session_id, {
        "phase": "plan",
        "prompt": prompt,
        "tenant_id": tenant_id,
        "intent": plan.get("intent", "query"),
        "cache_hit": False,
    })

    logger.info(f"Supervisor classification complete. Intent: {plan.get('intent')}, Plan: {plan}")

    return {
        "cached_hit": False,
        "retrieved_schemas": retrieved_schemas,
        "supervisor_plan": plan,
        "has_fatal_error": bool(planning_error),
        "error_detail": planning_error,
        "current_phase": "planning_complete",
        "resolved_prompt": resolved_prompt,
        "cache_prompt": cache_prompt,
        "conversation_context": conversation_context,
        "task_ledger": task_ledger,
        "execution_status": "running",
        "compiled_request": compiled_request,
        "schema_fingerprint": current_schema_fingerprint,
        "execution_trace": [{
            "phase": "planning",
            "status": "completed",
            "intent": plan.get("intent", "query"),
            "tasks": len(task_ledger),
        }],
    }
