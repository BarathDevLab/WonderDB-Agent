"""
summarize_node
==============
Orchestration layer — calls MCP tools in this order:
  1. generate_chart        (if needs_chart)
  2. generate_flowchart(er)        (if needs_er_diagram)
  3. generate_flowchart(process)   (if needs_process_flow)
  4. generate_flowchart(decision)  (if needs_decision_tree)
  5. explain_data          (LAST — so it knows every visual that was built)
  6. Semantic cache update
  7. Session memory append

explain_data runs LAST so it receives a context-rich prompt describing
every diagram and dataset generated, producing a coherent multi-section
explanation rather than a generic row count summary.
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


def _build_explain_prompt(
    original_prompt: str,
    diagram_specs: list[dict[str, Any]],
    has_chart: bool,
    raw_results: list[dict[str, Any]],
    retrieved_schemas: list[dict[str, Any]],
) -> str:
    """
    Build a rich, context-aware prompt for explain_data.
    Describes every visual artifact generated so Gemini can explain them all.
    """
    _DIAGRAM_LABELS = {
        "er": "Entity-Relationship (ER) schema diagram — shows all tables, columns, PKs, FKs, and relationships",
        "process": "Business process flow diagram — shows the sequential lifecycle/steps in the data",
        "decision": "Decision tree diagram — splits data above/below a threshold to show high vs low segments",
    }

    sections: list[str] = [f"User request: {original_prompt}"]

    if diagram_specs:
        types = [_DIAGRAM_LABELS.get(d.get("diagram_type", ""), d.get("diagram_type", "")) for d in diagram_specs]
        sections.append("Diagrams generated:\n" + "\n".join(f"  • {t}" for t in types))

    if has_chart:
        sections.append("A chart visualization was also generated for the numeric data.")

    if raw_results:
        sections.append(f"Query returned {len(raw_results)} rows of data (first 10 shown below).")

    if retrieved_schemas and not raw_results:
        table_names = [t.get("table_name", "") for t in retrieved_schemas]
        sections.append(f"Schema contains tables: {', '.join(table_names)}")

    return "\n\n".join(sections)


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
    diagram_specs: list[dict[str, Any]] = list(state.get("diagram_spec") or [])

    # ── Fast path: cache hit ─────────────────────────────────────────────
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
            "diagram_spec": diagram_specs,
            "current_phase": "summarize_complete",
        }

    # ── Error fallback ───────────────────────────────────────────────────
    if error_message and not raw_results:
        summary = f"The query could not be completed: {error_message}"
        await append_session_event(session_id, {
            "phase": "summary", "summary": summary, "error": error_message
        })
        return {
            **state,
            "summary": summary,
            "chart_spec": {},
            "diagram_spec": [],
            "tool_calls": tool_calls,
            "current_phase": "summarize_complete",
        }

    try:
        session = await get_mcp_session()
    except RuntimeError as exc:
        logger.error("summarize_node: MCP session unavailable: %s", exc)
        session = None

    # ── 1. Chart ─────────────────────────────────────────────────────────
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

    # ── 2. ER Diagram ─────────────────────────────────────────────────────
    if state.get("needs_er_diagram") and session:
        t0 = time.monotonic()
        try:
            er_spec = await _call_tool(session, "generate_flowchart", {
                "diagram_type": "er",
                "schema": retrieved_schemas,
            })
            diagram_specs.append(er_spec)
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            tool_calls.append({"tool": "generate_flowchart[er]", "status": "done", "duration_ms": duration_ms})
        except Exception as exc:
            logger.warning("generate_flowchart(er) tool failed: %s", exc)
            tool_calls.append({"tool": "generate_flowchart[er]", "status": "error", "duration_ms": 0})

    # ── 3. Process Flow ───────────────────────────────────────────────────
    if state.get("needs_process_flow") and session and raw_results:
        t0 = time.monotonic()
        try:
            process_spec = await _call_tool(session, "generate_flowchart", {
                "diagram_type": "process",
                "raw_data": raw_results,
                "title": prompt[:60],
            })
            diagram_specs.append(process_spec)
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            tool_calls.append({"tool": "generate_flowchart[process]", "status": "done", "duration_ms": duration_ms})
        except Exception as exc:
            logger.warning("generate_flowchart(process) tool failed: %s", exc)
            tool_calls.append({"tool": "generate_flowchart[process]", "status": "error", "duration_ms": 0})

    # ── 4. Decision Tree ──────────────────────────────────────────────────
    if state.get("needs_decision_tree") and session and raw_results:
        t0 = time.monotonic()
        try:
            decision_spec = await _call_tool(session, "generate_flowchart", {
                "diagram_type": "decision",
                "raw_data": raw_results,
                "title": prompt[:60],
            })
            diagram_specs.append(decision_spec)
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            tool_calls.append({"tool": "generate_flowchart[decision]", "status": "done", "duration_ms": duration_ms})
        except Exception as exc:
            logger.warning("generate_flowchart(decision) tool failed: %s", exc)
            tool_calls.append({"tool": "generate_flowchart[decision]", "status": "error", "duration_ms": 0})

    # ── 5. Explain Data (LAST — full context of everything generated) ─────
    if state.get("needs_explanation") and session:
        t0 = time.monotonic()
        explain_rows = raw_results if raw_results else (
            [{"table": t.get("table_name", ""), "columns": len(t.get("columns", []))}
             for t in retrieved_schemas]
            if retrieved_schemas else []
        )
        if explain_rows:
            try:
                rich_prompt = _build_explain_prompt(
                    original_prompt=prompt,
                    diagram_specs=diagram_specs,
                    has_chart=bool(chart_spec),
                    raw_results=raw_results,
                    retrieved_schemas=retrieved_schemas,
                )
                payload = await _call_tool(session, "explain_data", {
                    "prompt": rich_prompt,
                    "raw_results": explain_rows,
                })
                summary = payload.get("summary", summary)
                duration_ms = round((time.monotonic() - t0) * 1000, 1)
                tool_calls.append({"tool": "explain_data", "status": "done", "duration_ms": duration_ms})
            except Exception as exc:
                logger.warning("explain_data tool failed: %s", exc)
                tool_calls.append({"tool": "explain_data", "status": "error", "duration_ms": 0})

    # Final fallback summary
    if not summary and error_message:
        summary = f"Execution failed: {error_message}"
    elif not summary:
        parts = []
        if diagram_specs:
            parts.append(f"{len(diagram_specs)} diagram(s) generated")
        if raw_results:
            parts.append(f"{len(raw_results)} rows returned")
        summary = " · ".join(parts) if parts else "Done."

    # ── 6. Semantic Cache ─────────────────────────────────────────────────
    if cache_enabled and not error_message and (raw_results or diagram_specs):
        try:
            await set_semantic_cache(
                prompt,
                {
                    "sql_query": sql_query,
                    "summary": summary,
                    "chart_spec": chart_spec,
                    "diagram_spec": diagram_specs,
                    "raw_results": raw_results,
                },
                tenant_id,
            )
        except Exception as exc:
            logger.warning("Semantic cache set failed: %s", exc)

    # ── 7. Session Memory ─────────────────────────────────────────────────
    await append_session_event(session_id, {
        "phase": "summary",
        "prompt": prompt,
        "sql_query": sql_query,
        "summary": summary,
        "chart_type": chart_spec.get("type"),
        "diagram_types": [d.get("diagram_type") for d in diagram_specs],
        "rows_count": len(raw_results),
    })

    return {
        **state,
        "summary": summary,
        "chart_spec": chart_spec,
        "diagram_spec": diagram_specs,
        "tool_calls": tool_calls,
        "current_phase": "summarize_complete",
    }
