"""
plan_node
=========
Intent classifier + SQL generator.
Makes ONE Gemini API call that returns:
  - intent classification (query/schema/chat/contextual)
  - all visualization flags
  - generated SQL (if needed)

Also handles semantic cache fast-return path.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from agent.state import AgentState
from app.config import get_settings
from db.postgres import get_shared_pool
from services.schema_rag import retrieve_schema_context
from services.semantic_cache import get_semantic_cache
from services.session_memory import append_session_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DDL Formatter
# ---------------------------------------------------------------------------

def _format_schema_ddl(schemas: list[dict[str, Any]]) -> str:
    """Format structured table schemas into concise DDL definitions for LLM context."""
    ddl_lines: list[str] = []
    for table in schemas:
        t_name = table.get("table_name", "unknown")
        desc = table.get("description", "")
        cols = ", ".join(
            f"{c['name']} {c['type']}{' PRIMARY KEY' if c.get('is_pk') else ''}{' (PII)' if c.get('is_pii') else ''}"
            for c in table.get("columns", [])
        )
        fks = [
            f"FOREIGN KEY ({fk['column']}) REFERENCES {fk['foreign_table']}({fk['foreign_column']})"
            for fk in table.get("foreign_keys", [])
        ]
        fk_str = f", {', '.join(fks)}" if fks else ""
        ddl_lines.append(f"-- {desc}\nCREATE TABLE {t_name} ({cols}{fk_str});")
    return "\n\n".join(ddl_lines)


# ---------------------------------------------------------------------------
# Intent + SQL Classifier (single LLM call)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are an AI database assistant intent classifier and SQL generator.
Analyze the user's message and return a JSON object with these exact fields:

{
  "intent": "query" | "schema" | "chat" | "contextual",
  "needs_sql": true | false,
  "needs_chart": true | false,
  "chart_type": "auto" | "bar" | "line" | "pie" | "scatter",
  "needs_er_diagram": true | false,
  "needs_process_flow": true | false,
  "needs_explanation": true | false,
  "sql": "SELECT ..." | null
}

RULES:
DATA QUERY (intent="query"):
- User asks a measurable/data question about the database
- Set needs_sql=true, generate valid PostgreSQL SELECT with LIMIT 100
- needs_chart=true if: "chart", "plot", "visualize", "graph", "show me", "compare"
- chart_type="scatter" if: "scatter", "correlation", "vs"
- chart_type="pie" if: "pie", "distribution", "proportion", "share", "breakdown"
- chart_type="line" if: "trend", "over time", "by month", "by year", "by week", "timeline"
- chart_type="bar" for most comparisons (default)
- chart_type="auto" if chart needed but type unclear

SCHEMA (intent="schema"):
- User asks about table structure, relationships, ER diagram
- Set needs_sql=false, needs_er_diagram=true
- Examples: "ER diagram", "schema", "table structure", "relationships", "explain [table]"
- needs_process_flow=true if: "process", "flow", "pipeline", "steps", "workflow"

CHAT (intent="chat"):
- Greeting: "hi", "hello", "hey", "good morning"
- Help: "what can you do", "help", "how does this work"
- General conversation not about data or schema
- Set needs_sql=false, all other flags false

CONTEXTUAL (intent="contextual"):
- Follow-up referencing previous result: "simpler", "explain above",
  "continue", "tell me more", "elaborate", "more details", "and?",
  "explain that", "what does this mean"
- Set needs_sql=false, needs_explanation=true

IMPORTANT:
- Output ONLY valid JSON, no markdown, no explanation.
- sql must be a valid PostgreSQL SELECT only (no DML). null if not needed.
- Always set needs_explanation=true for query and schema intents.
"""


async def _classify_intent(
    prompt: str,
    schema_ddl: str,
    error_message: str | None,
    api_key: str,
    model: str,
) -> dict[str, Any] | None:
    """Call Gemini to classify intent and generate SQL in one shot."""
    try:
        import httpx
        user_content = f"Database Schema:\n{schema_ddl}\n\nUser Message: {prompt}"
        if error_message:
            user_content += (
                f"\n\nPrevious SQL attempt FAILED with: {error_message}\n"
                "Generate corrected SQL."
            )

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
            # Strip markdown fences if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1]
                raw_text = raw_text.rsplit("```", 1)[0].strip()
            return json.loads(raw_text)

    except Exception as exc:
        logger.warning("Intent classification failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# plan_node
# ---------------------------------------------------------------------------

async def plan_node(state: AgentState) -> AgentState:
    """
    Phase 1: Semantic cache gate.
    Phase 2: Vector search for relevant schemas (if data query).
    Phase 3: LLM intent classification + SQL generation.
    """
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default-tenant")
    session_id = state.get("session_id", f"session-{tenant_id}")
    error_message = state.get("error_message")
    settings = get_settings()
    cache_enabled = state.get("enable_cache", settings.enable_semantic_cache)

    # ── Fast path: detect obvious chat/contextual without LLM ───────────
    prompt_lower = prompt.lower().strip()
    _QUICK_CHAT = {"hi", "hello", "hey", "hiya", "howdy"}
    _QUICK_CONTEXTUAL = ["simpler", "continue", "tell me more", "elaborate",
                         "explain above", "explain that", "more details"]
    if prompt_lower in _QUICK_CHAT:
        return {**state, "intent": "chat", "needs_sql": False, "needs_chart": False,
                "needs_er_diagram": False, "needs_process_flow": False,
                "needs_explanation": False, "current_phase": "planning_complete"}
    if any(kw in prompt_lower for kw in _QUICK_CONTEXTUAL) and not error_message:
        return {**state, "intent": "contextual", "needs_sql": False, "needs_chart": False,
                "needs_er_diagram": False, "needs_process_flow": False,
                "needs_explanation": True, "current_phase": "planning_complete"}

    # ── Semantic Cache Gate ──────────────────────────────────────────────
    if cache_enabled and not error_message:
        cached = await get_semantic_cache(prompt, tenant_id)
        if cached:
            await append_session_event(session_id, {
                "phase": "plan", "prompt": prompt,
                "sql_query": cached.get("sql_query", ""), "cache_hit": True,
            })
            return {
                **state,
                "cached_hit": True,
                "ast_valid": True,
                "plan_strategy": "Semantic cache hit",
                "sql_query": cached.get("sql_query", ""),
                "raw_results": cached.get("raw_results", []),
                "summary": cached.get("summary", ""),
                "chart_spec": cached.get("chart_spec", {}),
                "diagram_spec": cached.get("diagram_spec", {}),
                "needs_sql": False,
                "needs_chart": bool(cached.get("chart_spec")),
                "needs_er_diagram": False,
                "needs_process_flow": False,
                "needs_explanation": False,
                "intent": "query",
                "error_message": "",
                "current_phase": "planning_complete",
            }

    # ── Schema Retrieval (for data queries) ─────────────────────────────
    pool = await get_shared_pool()
    retrieved_schemas = await retrieve_schema_context(prompt, tenant_id, pool)
    schema_ddl = _format_schema_ddl(retrieved_schemas) if retrieved_schemas else "(no schema available)"

    # ── LLM Intent Classification + SQL Generation ───────────────────────
    if not settings.gemini_api_key or not settings.gemini_model:
        return {
            **state,
            "cached_hit": False,
            "retrieved_schemas": retrieved_schemas,
            "error_message": "Gemini API key/model not configured.",
            "current_phase": "planning_failed",
        }

    classification = await _classify_intent(
        prompt=prompt,
        schema_ddl=schema_ddl,
        error_message=error_message,
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )

    if not classification:
        return {
            **state,
            "cached_hit": False,
            "retrieved_schemas": retrieved_schemas,
            "error_message": "Failed to classify intent. Check Gemini API key.",
            "current_phase": "planning_failed",
        }

    intent = classification.get("intent", "query")
    sql_query = classification.get("sql") or ""

    # Validate: if intent=query but no SQL generated, treat as failure
    if intent == "query" and not sql_query:
        return {
            **state,
            "intent": intent,
            "cached_hit": False,
            "retrieved_schemas": retrieved_schemas,
            "error_message": "SQL generation failed. Rephrase your question.",
            "current_phase": "planning_failed",
        }

    await append_session_event(session_id, {
        "phase": "plan",
        "prompt": prompt,
        "intent": intent,
        "sql_query": sql_query,
        "cache_hit": False,
    })

    return {
        **state,
        "cached_hit": False,
        "retrieved_schemas": retrieved_schemas,
        "intent": intent,
        "needs_sql": classification.get("needs_sql", False),
        "needs_chart": classification.get("needs_chart", False),
        "chart_type": classification.get("chart_type", "auto"),
        "needs_er_diagram": classification.get("needs_er_diagram", False),
        "needs_process_flow": classification.get("needs_process_flow", False),
        "needs_explanation": classification.get("needs_explanation", True),
        "plan_strategy": f"LLM intent: {intent}",
        "sql_query": sql_query,
        "error_message": "",
        "current_phase": "planning_complete",
    }
