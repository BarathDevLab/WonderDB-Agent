"""
synthesize_node.py
==================
Runs after all parallel map-reduce workers complete.
Responsibilities:
  1. Detect and surface fatal SQL errors gracefully
  2. Call analyze_data to compute grounded metrics
  3. Optionally call explain_data MCP tool to generate a rich narrative
  4. Call verify_response to detect missing or failed deliverables
  5. Write the final result to semantic cache and session memory
  6. Return ONLY the delta fields (not the full state)

Bug fixes applied:
  - tool_calls no longer mutated in-place (was breaking LangGraph's immutability contract)
  - cached_hit path now returns a delta, not the full state
  - Error detection via has_fatal_error sentinel, not fragile string prefix matching
"""
from __future__ import annotations

import json
import time
from typing import Any

from agent.mcp_client import get_mcp_session
from agent.state import GlobalState
from app.config import get_settings
from services.semantic_cache import set_semantic_cache
from services.session_memory import append_session_event
from utils.logger import get_logger

logger = get_logger(__name__)


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
    data_analysis: dict[str, Any] | None = None,
) -> str:
    """Build a rich, context-aware prompt for the explain_data MCP tool."""
    _DIAGRAM_LABELS = {
        "er": "Entity-Relationship (ER) schema diagram",
        "process": "Business process flow diagram",
        "decision": "Decision tree diagram",
    }

    schema_context = "(No schema provided)"
    if retrieved_schemas:
        schema_context = ", ".join(t.get("table_name", "") for t in retrieved_schemas)

    visuals_context = []
    if diagram_specs:
        types = [_DIAGRAM_LABELS.get(d.get("diagram_type", ""), d.get("diagram_type", "")) for d in diagram_specs]
        visuals_context.append("Diagrams generated: " + ", ".join(types))
    if has_chart:
        visuals_context.append("A chart visualization was generated.")

    prompt_template = f"""Act as an expert data analyst and business intelligence specialist.

**The Goal:**
Explain the results of the database query based on the user's original request: "{original_prompt}"

**Database Schema / Structure Context:**
Relevant tables involved: {schema_context}

**Visualizations / Artifacts:**
{chr(10).join(visuals_context) if visuals_context else "None"}

**Data Results:**
{f"Query returned {len(raw_results)} rows of data." if raw_results else "No data returned."}

**Verified Deterministic Analysis:**
{json.dumps(data_analysis, default=str) if data_analysis else "No computed analysis available."}

**Strict Output Rules:**
1. You MUST format your response exactly using the Markdown template below. Do not deviate from this structure.
2. Treat the verified deterministic analysis as the source of truth for all calculations. Do not invent or recalculate metrics.
3. DO NOT explain the database schema or ER diagrams unless the user explicitly asked how the database works. Focus strictly on the data and business insights.

**Mandatory Markdown Template to use for your response:**
### **Executive Performance Summary**

**Overview**
[1-2 sentences summarizing the main finding answering the user's prompt]

**Key Data Insights**
*   **[Insight 1 Heading]:** [Brief explanation with specific numbers]
*   **[Insight 2 Heading]:** [Brief explanation with specific numbers]

**Strategic Recommendations**
1.  **[Actionable Recommendation 1]**
2.  **[Actionable Recommendation 2]**
"""
    return prompt_template


async def synthesize_node(state: GlobalState) -> GlobalState:
    """
    Produce the final response after all parallel workers have completed.
    Returns only the delta fields that changed — LangGraph merges into full state.
    """
    prompt = state.get("prompt", "")
    cache_prompt = state.get("cache_prompt") or prompt
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
    logger.info(f"Synthesize node starting for session {session_id}. Needs explanation: {needs_explanation}")
    if state.get("cached_hit"):
        summary = state.get("summary", "")
        return {
            "summary": summary,
            "data_analysis": state.get("data_analysis", {}),
            "response_verification": state.get("response_verification", {}),
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
        verification: dict[str, Any] = {}
        verification_calls: list[dict[str, Any]] = []
        try:
            verification_session = await get_mcp_session()
            t0 = time.monotonic()
            verification = await _call_tool(verification_session, "verify_response", {
                "supervisor_plan": plan,
                "summary": friendly,
                "schema_available": bool(retrieved_schemas),
                "fatal_error": error_detail or "Query execution failed.",
                "original_prompt": prompt,
                "tool_calls": state.get("tool_calls", []),
            })
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            verification_calls.append({
                "tool": "verify_response", "status": "done", "duration_ms": duration_ms,
            })
        except Exception as exc:
            logger.warning("verify_response tool failed on fatal path: %s", exc)
            verification_calls.append({
                "tool": "verify_response", "status": "error", "duration_ms": 0,
            })
        await append_session_event(session_id, {
            "phase": "summary", "prompt": prompt, "sql_query": sql_query,
            "summary": friendly, "error": error_detail,
            "verification_status": verification.get("status", "unavailable"),
        })
        return {
            "summary": friendly,
            "response_verification": verification,
            "tool_calls": verification_calls,
            "current_phase": "complete",
        }

    # ── Build new tool_calls list — do NOT mutate state list in-place ───────
    # Bug fix: state.get("tool_calls", []) returns a reference; appending to it
    # mutates state directly, breaking LangGraph's immutable-update contract.
    # We build a fresh list and return it as the delta.
    extra_tool_calls: list[dict[str, Any]] = []

    visualizations = state.get("visualizations", [])
    chart_specs = [v for v in visualizations if "type" in v]
    chart_spec = chart_specs[0] if chart_specs else {}
    diagram_specs = [v for v in visualizations if "diagram_type" in v]

    # ── MCP session ─────────────────────────────────────────────────────────
    try:
        session = await get_mcp_session()
    except RuntimeError as exc:
        logger.error("synthesize_node: MCP session unavailable: %s", exc)
        session = None

    # Ground the narrative in deterministic calculations before involving an
    # LLM. Failure is non-fatal: raw rows and other artifacts remain usable.
    data_analysis: dict[str, Any] = {}
    if raw_results and session:
        t0 = time.monotonic()
        try:
            data_analysis = await _call_tool(session, "analyze_data", {
                "raw_data": raw_results,
                "analysis_types": ["summary", "trend", "outliers", "quality", "contributors"],
            })
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            extra_tool_calls.append({"tool": "analyze_data", "status": "done", "duration_ms": duration_ms})
        except Exception as exc:
            logger.warning("analyze_data tool failed: %s", exc)
            extra_tool_calls.append({"tool": "analyze_data", "status": "error", "duration_ms": 0})

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
                    has_chart=bool(chart_specs),
                    raw_results=raw_results,
                    retrieved_schemas=retrieved_schemas,
                    data_analysis=data_analysis,
                )
                payload = await _call_tool(session, "explain_data", {
                    "prompt": rich_prompt,
                    "raw_results": explain_rows,
                })
                logger.info("explain_data tool call succeeded.")
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
    # Final completion gate. It compares the supervisor plan with the actual
    # artifacts and makes partial results explicit instead of silently passing.
    response_verification: dict[str, Any] = {}
    if session:
        t0 = time.monotonic()
        try:
            response_verification = await _call_tool(session, "verify_response", {
                "supervisor_plan": plan,
                "sql_query": sql_query,
                "raw_data": raw_results,
                "visualizations": visualizations,
                "summary": summary,
                "data_analysis": data_analysis,
                "tool_calls": list(state.get("tool_calls", [])) + extra_tool_calls,
                "schema_available": bool(retrieved_schemas),
                "fatal_error": "",
                "original_prompt": prompt,
            })
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            extra_tool_calls.append({
                "tool": "verify_response", "status": "done", "duration_ms": duration_ms,
            })
            missing = response_verification.get("missing_artifacts", [])
            if missing:
                readable = ", ".join(item.replace("_", " ") for item in missing)
                summary += (
                    "\n\nResponse verification: the following requested output "
                    f"was not produced: {readable}."
                )
        except Exception as exc:
            logger.warning("verify_response tool failed: %s", exc)
            extra_tool_calls.append({
                "tool": "verify_response", "status": "error", "duration_ms": 0,
            })

    if cache_enabled and (raw_results or diagram_specs):
        try:
            await set_semantic_cache(
                cache_prompt,
                {
                    "sql_query": sql_query,
                    "summary": summary,
                    "chart_spec": chart_spec,
                    "chart_specs": chart_specs,
                    "diagram_spec": diagram_specs,
                    "raw_results": raw_results,
                    "data_analysis": data_analysis,
                    "response_verification": response_verification,
                },
                tenant_id,
            )
        except Exception as exc:
            logger.warning("Semantic cache set failed: %s", exc)

    # ── Session memory update ────────────────────────────────────────────────
    try:
        result_sample = [
            {key: row[key] for key in list(row)[:8]}
            for row in raw_results[:5]
        ]
        await append_session_event(session_id, {
            "phase": "summary",
            "prompt": prompt,
            "tenant_id": tenant_id,
            "sql_query": sql_query,
            "summary": summary,
            "chart_type": chart_spec.get("type"),
            "chart_types": [chart.get("type") for chart in chart_specs],
            "diagram_types": [d.get("diagram_type") for d in diagram_specs],
            "rows_count": len(raw_results),
            "result_sample": result_sample,
            "analysis_available": bool(data_analysis),
            "verification_status": response_verification.get("status", "unavailable"),
        })
    except Exception as exc:
        logger.warning("Session memory append failed: %s", exc)

    # Return delta only — include new tool_calls so operator.add can merge them
    logger.info(f"Synthesis complete for session {session_id}. Summary length: {len(summary)}")
    return {
        "summary": summary,
        "data_analysis": data_analysis,
        "response_verification": response_verification,
        "tool_calls": extra_tool_calls,
        "current_phase": "complete",
    }
