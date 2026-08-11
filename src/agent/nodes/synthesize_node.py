"""
synthesize_node.py
==================
Runs *after* all parallel map-reduce workers.
Receives combined dataset and visualizations array.
Invokes explain_data if needed, updates cache and session memory.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from agent.mcp_client import get_mcp_session
from agent.state import GlobalState
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
    """Build a rich, context-aware prompt for explain_data."""
    _DIAGRAM_LABELS = {
        "er": "Entity-Relationship (ER) schema diagram",
        "process": "Business process flow diagram",
        "decision": "Decision tree diagram",
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


async def synthesize_node(state: GlobalState) -> GlobalState:
    """Synthesize results from workers, optionally explain, and update memory."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default-tenant")
    session_id = state.get("session_id", f"session-{tenant_id}")
    raw_results = state.get("clean_dataset", [])
    sql_query = state.get("sql_query", "")
    retrieved_schemas = state.get("retrieved_schemas", [])
    settings = get_settings()
    cache_enabled = state.get("enable_cache", settings.enable_semantic_cache)
    tool_calls = state.get("tool_calls", [])
    
    plan = state.get("supervisor_plan", {})
    needs_explanation = plan.get("needs_explanation", False)

    summary = state.get("summary", "") # Might contain error from SQL engine
    visualizations = state.get("visualizations", [])
    
    # Separate visualizations
    chart_spec = next((v for v in visualizations if "type" in v), {})
    diagram_specs = [v for v in visualizations if "diagram_type" in v]

    # Fast path: cache hit
    if state.get("cached_hit") and summary:
        return state

    try:
        session = await get_mcp_session()
    except RuntimeError as exc:
        logger.error("synthesize_node: MCP session unavailable: %s", exc)
        session = None

    if needs_explanation and session and not summary.startswith("MCP execution error") and not summary.startswith("SQL generation failed"):
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

    if not summary:
        parts = []
        if diagram_specs:
            parts.append(f"{len(diagram_specs)} diagram(s) generated")
        if raw_results:
            parts.append(f"{len(raw_results)} rows returned")
        summary = " · ".join(parts) if parts else "Done."

    # Semantic Cache Update
    if cache_enabled and not summary.startswith("MCP execution error") and (raw_results or diagram_specs):
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

    # Session Memory Update
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
        "summary": summary,
        "tool_calls": [{"tool": tc["tool"], "status": tc["status"], "duration_ms": tc["duration_ms"]} for tc in tool_calls],
        "current_phase": "complete",
    }
