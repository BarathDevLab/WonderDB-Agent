"""
summarize_node
==============
Conditionally calls MCP tools based on intent flags set by plan_node:
  - needs_explanation → explain_data tool
  - needs_chart       → generate_chart tool
  - needs_er_diagram  → generate_flowchart(er) tool
  - needs_process_flow→ generate_flowchart(process) tool

Also handles cache hits (summary already in state) and updates
semantic cache + session memory.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from agent.mcp_client import get_mcp_session
from agent.state import AgentState
from app.config import get_settings
from services.semantic_cache import set_semantic_cache
from services.session_memory import append_session_event

logger = logging.getLogger(__name__)


async def _call_tool(session: Any, tool_name: str, arguments: dict) -> dict[str, Any]:
    """Call an MCP tool and return parsed JSON response."""
    result = await session.call_tool(tool_name, arguments=arguments)
    raw_text = result.content[0].text if result.content else "{}"
    return json.loads(raw_text)


async def summarize_node(state: AgentState) -> AgentState:
    """Conditionally invoke MCP tools based on intent flags, then cache and store."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default-tenant")
    session_id = state.get("session_id", f"session-{tenant_id}")
    raw_results: list[dict[str, Any]] = state.get("raw_results", [])
    sql_query = state.get("sql_query", "")
    error_message = state.get("error_message", "")
    retrieved_schemas: list[dict[str, Any]] = state.get("retrieved_schemas", [])
    settings = get_settings()
    cache_enabled = state.get("enable_cache", settings.enable_semantic_cache)
    tool_calls: list[dict[str, Any]] = list(state.get("tool_calls") or [])

    summary = state.get("summary", "")
    chart_spec: dict[str, Any] = state.get("chart_spec") or {}
    diagram_spec: dict[str, Any] = state.get("diagram_spec") or {}

    # Fast path: cache hit — summary already in state
    if state.get("cached_hit") and summary:
        await append_session_event(session_id, {
            "phase": "summary", "summary": summary,
            "chart_type": chart_spec.get("type"),
            "rows_count": len(raw_results), "cache_hit": True,
        })
        return {
            **state,
            "summary": summary,
            "chart_spec": chart_spec,
            "diagram_spec": diagram_spec,
            "current_phase": "summarize_complete",
        }

    # Error fallback — no MCP tools needed
    if error_message and not raw_results:
        summary = f"The query could not be completed: {error_message}"
        await append_session_event(session_id, {
            "phase": "summary", "summary": summary, "error": error_message
        })
        return {
            **state,
            "summary": summary,
            "chart_spec": {},
            "diagram_spec": {},
            "tool_calls": tool_calls,
            "current_phase": "summarize_complete",
        }

    try:
        session = await get_mcp_session()
    except RuntimeError as exc:
        logger.error("summarize_node: MCP session unavailable: %s", exc)
        session = None

    # ── 1. Explain Data ──────────────────────────────────────────────────
    if state.get("needs_explanation") and session and raw_results:
        t0 = time.monotonic()
        try:
            payload = await _call_tool(session, "explain_data", {
                "prompt": prompt,
                "raw_results": raw_results,
            })
            summary = payload.get("summary", summary)
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            tool_calls.append({"tool": "explain_data", "status": "done", "duration_ms": duration_ms})
        except Exception as exc:
            logger.warning("explain_data tool failed: %s", exc)
            summary = f"Query returned {len(raw_results)} rows."
            tool_calls.append({"tool": "explain_data", "status": "error", "duration_ms": 0})
    elif not summary and error_message:
        summary = f"Execution failed: {error_message}"
    elif not summary:
        summary = f"Query returned {len(raw_results)} rows."

    # ── 2. Generate Chart ────────────────────────────────────────────────
    if state.get("needs_chart") and session and raw_results:
        t0 = time.monotonic()
        try:
            chart_spec = await _call_tool(session, "generate_chart", {
                "raw_data": raw_results,
                "chart_type": state.get("chart_type", "auto"),
            })
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            tool_calls.append({"tool": "generate_chart", "status": "done", "duration_ms": duration_ms})
        except Exception as exc:
            logger.warning("generate_chart tool failed: %s", exc)
            tool_calls.append({"tool": "generate_chart", "status": "error", "duration_ms": 0})

    # ── 3. ER Diagram ────────────────────────────────────────────────────
    if state.get("needs_er_diagram") and session:
        t0 = time.monotonic()
        try:
            diagram_spec = await _call_tool(session, "generate_flowchart", {
                "diagram_type": "er",
                "schema": retrieved_schemas,
            })
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            tool_calls.append({"tool": "generate_flowchart", "status": "done", "duration_ms": duration_ms})
            if not summary or summary.startswith("Query returned"):
                summary = "Here is the Entity-Relationship (ER) diagram for your database schema, displaying table attributes, primary keys, and foreign key relationships."
        except Exception as exc:
            logger.warning("generate_flowchart(er) tool failed: %s", exc)
            tool_calls.append({"tool": "generate_flowchart", "status": "error", "duration_ms": 0})

    # ── 4. Process Flow ──────────────────────────────────────────────────
    elif state.get("needs_process_flow") and session and raw_results:
        t0 = time.monotonic()
        try:
            diagram_spec = await _call_tool(session, "generate_flowchart", {
                "diagram_type": "process",
                "raw_data": raw_results,
                "title": prompt[:60],
            })
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            tool_calls.append({"tool": "generate_flowchart", "status": "done", "duration_ms": duration_ms})
            if not summary or summary.startswith("Query returned"):
                summary = "Here is the visual process flow diagram for your dataset."
        except Exception as exc:
            logger.warning("generate_flowchart(process) tool failed: %s", exc)
            tool_calls.append({"tool": "generate_flowchart", "status": "error", "duration_ms": 0})

    # ── 5. Semantic Cache Update ─────────────────────────────────────────
    if cache_enabled and not error_message and raw_results:
        try:
            await set_semantic_cache(
                prompt,
                {
                    "sql_query": sql_query,
                    "summary": summary,
                    "chart_spec": chart_spec,
                    "diagram_spec": diagram_spec,
                    "raw_results": raw_results,
                },
                tenant_id,
            )
        except Exception as exc:
            logger.warning("Semantic cache set failed: %s", exc)

    # ── 6. Session Memory ────────────────────────────────────────────────
    await append_session_event(session_id, {
        "phase": "summary",
        "prompt": prompt,
        "sql_query": sql_query,
        "summary": summary,
        "chart_type": chart_spec.get("type"),
        "diagram_type": diagram_spec.get("diagram_type"),
        "rows_count": len(raw_results),
    })

    return {
        **state,
        "summary": summary,
        "chart_spec": chart_spec,
        "diagram_spec": diagram_spec,
        "tool_calls": tool_calls,
        "current_phase": "summarize_complete",
    }
