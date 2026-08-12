"""Deterministic completion checks for an agent response."""
from __future__ import annotations

from typing import Any

from services.request_requirements import requested_visualizations_from_prompt


_CHART_TYPES = {"bar", "line", "pie", "scatter"}
_DIAGRAM_TYPES = {"er", "process", "decision"}


def _requested_artifacts(
    plan: dict[str, Any], has_rows: bool, original_prompt: str = "",
) -> list[str]:
    intent = plan.get("intent", "query")
    requested: list[str] = []
    if intent == "query":
        requested.append("query_execution")
        if has_rows:
            requested.append("analysis")
    elif intent == "schema":
        requested.append("schema_context")

    if plan.get("needs_explanation"):
        requested.append("explanation")

    for visualization in plan.get("visualizations", []):
        if visualization not in requested:
            requested.append(visualization)
    for visualization in requested_visualizations_from_prompt(original_prompt):
        if visualization not in requested:
            requested.append(visualization)
    return requested


def verify_agent_response(
    supervisor_plan: dict[str, Any],
    sql_query: str = "",
    raw_data: list[dict[str, Any]] | None = None,
    visualizations: list[dict[str, Any]] | None = None,
    summary: str = "",
    data_analysis: dict[str, Any] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    schema_available: bool = False,
    fatal_error: str = "",
    original_prompt: str = "",
) -> dict[str, Any]:
    """Compare the requested plan with the artifacts actually produced."""
    rows = raw_data or []
    visuals = visualizations or []
    calls = tool_calls or []
    analysis = data_analysis or {}
    requested = _requested_artifacts(supervisor_plan, bool(rows), original_prompt)

    delivered: set[str] = set()
    if sql_query.strip() and not fatal_error:
        delivered.add("query_execution")
    if schema_available:
        delivered.add("schema_context")
    explain_failed = any(
        call.get("tool") == "explain_data" and call.get("status") == "error"
        for call in calls
    )
    if summary.strip() and not explain_failed:
        delivered.add("explanation")
    if analysis and analysis.get("row_count", 0) == len(rows):
        delivered.add("analysis")

    for visual in visuals:
        chart_type = visual.get("type")
        if chart_type in _CHART_TYPES and visual.get("data"):
            delivered.add(f"{chart_type}_chart")
        diagram_type = visual.get("diagram_type")
        mermaid = visual.get("mermaid", "")
        diagram_is_real = (
            mermaid
            and "NO_SCHEMA_LOADED" not in mermaid
            and "NO_DATA" not in mermaid
            and "NOT_APPLICABLE" not in mermaid
        )
        if diagram_type == "process":
            diagram_is_real = diagram_is_real and visual.get("process_mode") in {
                "state_transitions",
                "ordered_steps",
                "agent_pipeline",
            }
        if diagram_type in _DIAGRAM_TYPES and diagram_is_real:
            delivered.add({
                "er": "er_diagram",
                "process": "process_flow",
                "decision": "decision_tree",
            }[diagram_type])
            if diagram_type == "er":
                delivered.add("schema_context")

    missing = [artifact for artifact in requested if artifact not in delivered]
    warnings: list[str] = []
    if fatal_error:
        warnings.append(f"Fatal execution error: {fatal_error}")
    if supervisor_plan.get("intent") == "query" and sql_query.strip() and not rows and not fatal_error:
        warnings.append("The query completed but returned no rows.")
    for call in calls:
        if call.get("status") == "error":
            warnings.append(f"Tool failed: {call.get('tool', 'unknown')}")
    quality = analysis.get("data_quality", {})
    if quality.get("null_cells", 0):
        warnings.append(f"Returned data contains {quality['null_cells']} null cell(s).")
    if quality.get("duplicate_rows", 0):
        warnings.append(f"Returned data contains {quality['duplicate_rows']} duplicate row(s).")

    completion_ratio = 1.0 if not requested else round(
        sum(1 for artifact in requested if artifact in delivered) / len(requested), 3
    )
    if fatal_error or (requested and not delivered):
        status = "failed"
    elif missing:
        status = "partial"
    else:
        status = "complete"

    return {
        "verified": status == "complete",
        "status": status,
        "completion_ratio": completion_ratio,
        "requested_artifacts": requested,
        "delivered_artifacts": sorted(delivered),
        "missing_artifacts": missing,
        "warnings": list(dict.fromkeys(warnings)),
    }
