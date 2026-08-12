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
from services.schema_rag import retrieve_schema_context
from services.semantic_cache import get_semantic_cache
from services.session_memory import append_session_event
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# System prompt — intent classification
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an AI database assistant intent classifier and orchestration planner.
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
  • Complex transitions        → "process_flow"
  • Hierarchical splits        → "decision_tree"
  Only include a chart type if it genuinely adds insight.
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
- Maximum 3 visualization types per response.
- Always set needs_explanation=true for query and schema intents.
"""


_MAX_PROMPT_CHARS = 2000


# ─────────────────────────────────────────────────────────────────────────────
# LLM call
# ─────────────────────────────────────────────────────────────────────────────

async def _classify_intent(
    prompt: str,
    api_key: str,
    model: str,
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
        user_content = f"User message to classify:\n<user_message>\n{prompt}\n</user_message>"

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
            plan["visualizations"] = list(dict.fromkeys(
                v for v in raw_viz if v in allowed_viz
            ))[:3]  # deduplicate, cap at 3
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
            "has_fatal_error": False,
            "error_detail": "",
            "current_phase": "planning_complete",
        }

    # Truncate silently if over limit (API caller should enforce this too)
    if len(prompt) > _MAX_PROMPT_CHARS:
        prompt = prompt[:_MAX_PROMPT_CHARS]


    # ── 3. Semantic cache gate ──────────────────────────────────────────────
    if cache_enabled:
        try:
            cached = await get_semantic_cache(prompt, tenant_id)
        except Exception as exc:
            logger.warning("Semantic cache lookup failed, proceeding without cache: %s", exc)
            cached = None

        if cached:
            await append_session_event(session_id, {
                "phase": "plan", "prompt": prompt,
                "sql_query": cached.get("sql_query", ""), "cache_hit": True,
            })
            # Reconstruct visualizations list from cached chart/diagram specs
            viz: list[dict] = []
            if cached.get("chart_spec"):
                viz.append(cached["chart_spec"])
            for d in cached.get("diagram_spec", []):
                viz.append(d)

            return {
                "cached_hit": True,
                "sql_query": cached.get("sql_query", ""),
                "clean_dataset": cached.get("raw_results", []),
                "summary": cached.get("summary", ""),
                "visualizations": viz,
                "has_fatal_error": False,
                "error_detail": "",
                # Cache hit bypasses all workers; supervisor_plan not used for routing
                "supervisor_plan": {"intent": "query", "visualizations": [], "needs_explanation": False},
                "current_phase": "planning_complete",
            }

    # ── 4a. Schema retrieval ────────────────────────────────────────────────
    try:
        pool = await get_shared_pool()
        retrieved_schemas = await retrieve_schema_context(prompt, tenant_id, pool)
    except Exception as exc:
        logger.error("Schema retrieval failed: %s", exc)
        retrieved_schemas = []

    # ── 4b. LLM intent classification ──────────────────────────────────────
    if not settings.gemini_api_key or not settings.gemini_model:
        logger.error("Gemini API key or model not configured — cannot classify intent")
        return {
            "cached_hit": False,
            "retrieved_schemas": retrieved_schemas,
            "supervisor_plan": {"intent": "error", "visualizations": [], "needs_explanation": False},
            "has_fatal_error": False,
            "error_detail": "LLM configuration missing.",
            "current_phase": "planning_failed",
        }

    plan = await _classify_intent(
        prompt=prompt,
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )

    if not plan:
        # Fallback: treat as a query so user gets a best-effort response
        logger.warning("Intent classification returned None — defaulting to query intent")
        plan = {"intent": "query", "visualizations": [], "needs_explanation": True}

    await append_session_event(session_id, {
        "phase": "plan",
        "prompt": prompt,
        "intent": plan.get("intent", "query"),
        "cache_hit": False,
    })

    logger.info(f"Supervisor classification complete. Intent: {plan.get('intent')}, Plan: {plan}")

    return {
        "cached_hit": False,
        "retrieved_schemas": retrieved_schemas,
        "supervisor_plan": plan,
        "has_fatal_error": False,
        "error_detail": "",
        "current_phase": "planning_complete",
    }
