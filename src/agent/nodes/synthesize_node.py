"""
synthesize_node.py
==================
Runs after all parallel map-reduce workers complete.
Responsibilities:
  1. Detect and surface fatal SQL errors gracefully
  2. Optionally call explain_data MCP tool to generate a rich narrative
  3. Write the final result to semantic cache
  4. Append the completed interaction to session memory
  5. Return ONLY the delta fields (not the full state)

Bug fixes applied:
  - tool_calls no longer mutated in-place (was breaking LangGraph's immutability contract)
  - cached_hit path now returns a delta, not the full state
  - Error detection via has_fatal_error sentinel, not fragile string prefix matching
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
    """Call an MCP tool and return the parsed JSON response."""
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
    """Build a rich, context-aware prompt for the explain_data MCP tool."""
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
    """
    Produce the final response after all parallel workers have completed.
    Returns only the delta fields that changed — LangGraph merges into full state.
    """
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default-tenant")
    session_id = state.get("session_id", f"session-{tenant_id}")
    raw_results = state.get("clean_dataset", [])
    sql_query = state.get("sql_query", "")
    retrieved_schemas = state.get("retrieved_schemas", [])
    settings = get_settings()
    cache_enabled = state.get("enable_cache", settings.enable_semantic_cache)

    plan = state.get("supervisor_plan", {})
    needs_explanation = plan.get("needs_explanation", False)

    # ── Fast path: cache hit — return minimal delta ─────────────────────────
    # Bug fix: was returning full `state` (incorrect — must return delta only)
    if state.get("cached_hit"):
        summary = state.get("summary", "")
        return {
            "summary": summary,
            "current_phase": "complete",
        }

    # ── Fatal error path — surface a clean user-facing error ────────────────
    has_fatal = state.get("has_fatal_error", False)
    error_detail = state.get("error_detail", "")

    # Legacy fallback: check old summary-embedded errors for backwards compat
    legacy_summary = state.get("summary", "")
    if not has_fatal and legacy_summary and (
        legacy_summary.startswith("MCP execution error")
        or legacy_summary.startswith("SQL generation failed")
    ):
        has_fatal = True
        error_detail = legacy_summary

    if has_fatal:
        friendly = (
            "I wasn't able to execute that query. "
            f"Details: {error_detail}" if error_detail else
            "I wasn't able to execute that query. Please try rephrasing or simplifying."
        )
        await append_session_event(session_id, {
            "phase": "summary", "prompt": prompt, "sql_query": sql_query,
            "summary": friendly, "error": error_detail,
        })
        return {
            "summary": friendly,
            "current_phase": "complete",
        }

    # ── Build new tool_calls list — do NOT mutate state list in-place ───────
    # Bug fix: state.get("tool_calls", []) returns a reference; appending to it
    # mutates state directly, breaking LangGraph's immutable-update contract.
    # We build a fresh list and return it as the delta.
    extra_tool_calls: list[dict[str, Any]] = []

    visualizations = state.get("visualizations", [])
    chart_spec = next((v for v in visualizations if "type" in v), {})
    diagram_specs = [v for v in visualizations if "diagram_type" in v]

    # ── MCP session ─────────────────────────────────────────────────────────
    try:
        session = await get_mcp_session()
    except RuntimeError as exc:
        logger.error("synthesize_node: MCP session unavailable: %s", exc)
        session = None

    # ── Optional explain_data call ──────────────────────────────────────────
    summary = ""
    if needs_explanation and session:
        explain_rows = raw_results if raw_results else (
            [{"table": t.get("table_name", ""), "columns": len(t.get("columns", []))}
             for t in retrieved_schemas]
            if retrieved_schemas else []
        )
        if explain_rows:
            t0 = time.monotonic()
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
                summary = payload.get("summary", "")
                duration_ms = round((time.monotonic() - t0) * 1000, 1)
                extra_tool_calls.append({"tool": "explain_data", "status": "done", "duration_ms": duration_ms})
            except Exception as exc:
                logger.warning("explain_data tool failed: %s", exc)
                extra_tool_calls.append({"tool": "explain_data", "status": "error", "duration_ms": 0})

    # ── Fallback summary if explain_data didn't run or returned empty ────────
    if not summary:
        parts: list[str] = []
        if diagram_specs:
            parts.append(f"{len(diagram_specs)} diagram(s) generated")
        if raw_results:
            parts.append(f"{len(raw_results)} rows returned")
        summary = " · ".join(parts) if parts else "Done."

    # ── Semantic cache update ────────────────────────────────────────────────
    if cache_enabled and (raw_results or diagram_specs):
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

    # ── Session memory update ────────────────────────────────────────────────
    try:
        await append_session_event(session_id, {
            "phase": "summary",
            "prompt": prompt,
            "sql_query": sql_query,
            "summary": summary,
            "chart_type": chart_spec.get("type"),
            "diagram_types": [d.get("diagram_type") for d in diagram_specs],
            "rows_count": len(raw_results),
        })
    except Exception as exc:
        logger.warning("Session memory append failed: %s", exc)

    # Return delta only — include new tool_calls so operator.add can merge them
    return {
        "summary": summary,
        "tool_calls": extra_tool_calls,
        "current_phase": "complete",
    }
