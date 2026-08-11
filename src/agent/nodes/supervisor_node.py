"""
supervisor_node
===============
Intent classifier and orchestration planner.
Makes ONE Gemini API call to determine the plan (intent, visualizations needed).
Does NOT generate SQL.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from agent.state import GlobalState
from app.config import get_settings
from db.postgres import get_shared_pool
from services.schema_rag import retrieve_schema_context
from services.semantic_cache import get_semantic_cache
from services.session_memory import append_session_event

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """
You are an AI database assistant intent classifier and orchestrator.
Analyze the user's message and return a JSON object with these exact fields:

{
  "intent": "query" | "schema" | "chat" | "contextual",
  "visualizations": ["bar_chart", "line_chart", "pie_chart", "scatter_chart", "er_diagram", "process_flow", "decision_tree"],
  "needs_explanation": true | false
}

INTENT RULES:

DATA QUERY (intent="query"):
- User asks a measurable/data question about the database
- Visualizations: Include chart types if user asks to "chart", "plot", "visualize", "compare", "trend".
- Choose chart type intelligently based on the query.

SCHEMA ONLY (intent="schema"):
- User asks ONLY about table structure, relationships, or ER diagram with NO data request
- Include "er_diagram" in visualizations if requested.

HYBRID (intent="query"):
- User asks for BOTH schema/diagrams AND data.
- Include all requested visualizations.

CHAT (intent="chat"):
- Greeting: "hi", "hello", "hey", "good morning"
- Help: "what can you do", "help", "how does this work"
- General conversation not about data or schema
- Empty visualizations.

CONTEXTUAL (intent="contextual"):
- Follow-up referencing previous result: "simpler", "explain above", "continue"
- Empty visualizations, needs_explanation=true.

IMPORTANT:
- Output ONLY valid JSON, no markdown, no explanation.
- Always set needs_explanation=true for query and schema intents.
"""


async def _classify_intent(
    prompt: str,
    api_key: str,
    model: str,
) -> dict[str, Any] | None:
    """Call Gemini to classify intent and generate a plan."""
    try:
        import httpx
        user_content = f"User Message: {prompt}"

        clean_model = model.strip()
        if clean_model.startswith("models/"):
            clean_model = clean_model[len("models/"):]

        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{_SYSTEM_PROMPT}\n\n{user_content}"}]}],
            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
        }
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{clean_model}:generateContent?key={api_key}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                logger.warning("Gemini classify intent returned %s: %s", res.status_code, res.text)
                return None

            data = res.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1]
                raw_text = raw_text.rsplit("```", 1)[0].strip()
            return json.loads(raw_text)

    except Exception as exc:
        logger.warning("Intent classification failed: %s", exc)
        return None


async def supervisor_node(state: GlobalState) -> GlobalState:
    """
    Phase 1: Semantic cache gate.
    Phase 2: Intent classification for orchestration plan.
    Phase 3: Schema retrieval (passed down to SQL Subgraph if needed).
    """
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default-tenant")
    session_id = state.get("session_id", f"session-{tenant_id}")
    settings = get_settings()
    cache_enabled = state.get("enable_cache", settings.enable_semantic_cache)

    # ── Fast path: detect obvious chat/contextual without LLM ───────────
    prompt_lower = prompt.lower().strip()
    _QUICK_CHAT = {"hi", "hello", "hey", "hiya", "howdy"}
    _QUICK_CONTEXTUAL = ["simpler", "continue", "tell me more", "elaborate",
                         "explain above", "explain that", "more details"]
    if prompt_lower in _QUICK_CHAT:
        return {**state, "supervisor_plan": {"intent": "chat", "visualizations": [], "needs_explanation": False}, "current_phase": "planning_complete"}
    if any(kw in prompt_lower for kw in _QUICK_CONTEXTUAL):
        return {**state, "supervisor_plan": {"intent": "contextual", "visualizations": [], "needs_explanation": True}, "current_phase": "planning_complete"}

    # ── Semantic Cache Gate ──────────────────────────────────────────────
    if cache_enabled:
        cached = await get_semantic_cache(prompt, tenant_id)
        if cached:
            await append_session_event(session_id, {
                "phase": "plan", "prompt": prompt,
                "sql_query": cached.get("sql_query", ""), "cache_hit": True,
            })
            # Reconstruct visualizations from cache
            viz = []
            if cached.get("chart_spec"): viz.append(cached["chart_spec"])
            for d in cached.get("diagram_spec", []): viz.append(d)
            
            return {
                **state,
                "cached_hit": True,
                "sql_query": cached.get("sql_query", ""),
                "clean_dataset": cached.get("raw_results", []),
                "summary": cached.get("summary", ""),
                "visualizations": viz,
                "supervisor_plan": {"intent": "query", "visualizations": [], "needs_explanation": False}, # Cache hit bypasses worker routing
                "current_phase": "planning_complete",
            }

    # ── Schema Retrieval ─────────────────────────────────────────────
    pool = await get_shared_pool()
    retrieved_schemas = await retrieve_schema_context(prompt, tenant_id, pool)

    # ── LLM Intent Classification ───────────────────────
    if not settings.gemini_api_key or not settings.gemini_model:
        return {
            **state,
            "cached_hit": False,
            "retrieved_schemas": retrieved_schemas,
            "supervisor_plan": {"intent": "error"},
            "current_phase": "planning_failed",
        }

    plan = await _classify_intent(
        prompt=prompt,
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )

    if not plan:
        return {
            **state,
            "cached_hit": False,
            "retrieved_schemas": retrieved_schemas,
            "supervisor_plan": {"intent": "error"},
            "current_phase": "planning_failed",
        }

    await append_session_event(session_id, {
        "phase": "plan",
        "prompt": prompt,
        "intent": plan.get("intent", "query"),
        "cache_hit": False,
    })

    return {
        **state,
        "cached_hit": False,
        "retrieved_schemas": retrieved_schemas,
        "supervisor_plan": plan,
        "current_phase": "planning_complete",
    }
