"""Request-scoped task ledger and dependency graph for agent completion."""
from __future__ import annotations

from typing import Any

from services.artifact_validation import validate_visualization, visual_for_artifact
from services.response_verification import requested_artifacts


_VISUAL_ARTIFACTS = {
    "bar_chart", "line_chart", "pie_chart", "scatter_chart",
    "er_diagram", "process_flow", "decision_tree",
}


def _dependencies(artifact: str) -> list[str]:
    if artifact == "query_execution":
        return ["schema_context"]
    if artifact == "analysis":
        return ["query_execution"]
    if artifact.endswith("_chart") or artifact == "decision_tree":
        return ["query_execution"]
    if artifact in {"er_diagram", "process_flow"}:
        return ["schema_context"]
    if artifact == "explanation":
        return []
    return []


def build_task_ledger(
    plan: dict[str, Any],
    original_prompt: str = "",
) -> list[dict[str, Any]]:
    """Compile a supervisor plan into an explicit, ordered task DAG."""
    intent = plan.get("intent", "query")
    if intent in {"chat", "contextual"}:
        return [{
            "task_id": "chat_response",
            "type": "chat_response",
            "required": True,
            "dependencies": [],
            "status": "pending",
            "attempts": 0,
            "max_attempts": 1,
            "errors": [],
        }]
    artifacts = requested_artifacts(plan, has_rows=True, original_prompt=original_prompt)
    # Schema is an execution prerequisite for queries even though it is not a
    # user-facing deliverable in ordinary query responses.
    if plan.get("intent") == "query" and "schema_context" not in artifacts:
        artifacts.insert(0, "schema_context")
    tasks = [
        {
            "task_id": artifact,
            "type": artifact,
            "required": artifact != "schema_context" or plan.get("intent") == "schema",
            "dependencies": _dependencies(artifact),
            "status": "pending",
            "attempts": 0,
            "max_attempts": 6 if artifact in _VISUAL_ARTIFACTS else 2,
            "errors": [],
        }
        for artifact in artifacts
    ]
    dependencies = [task["task_id"] for task in tasks if task["required"]]
    tasks.append({
        "task_id": "verification",
        "type": "verification",
        "required": True,
        "dependencies": dependencies,
        "status": "pending",
        "attempts": 0,
        "max_attempts": 1,
        "errors": [],
    })
    return tasks


def finalize_task_ledger(
    ledger: list[dict[str, Any]],
    *,
    sql_query: str,
    raw_data: list[dict[str, Any]],
    visualizations: list[dict[str, Any]],
    summary: str,
    data_analysis: dict[str, Any],
    schema_available: bool,
    verification: dict[str, Any],
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return an immutable final ledger derived from actual outputs."""
    failed_tools = [call.get("tool", "unknown") for call in tool_calls if call.get("status") == "error"]
    result: list[dict[str, Any]] = []
    for original in ledger:
        task = {**original, "errors": list(original.get("errors", []))}
        artifact = task["type"]
        valid = False
        validation: dict[str, Any] = {}
        if artifact == "schema_context":
            valid = schema_available
        elif artifact == "query_execution":
            valid = bool(sql_query.strip())
        elif artifact == "analysis":
            valid = bool(data_analysis) and data_analysis.get("row_count") == len(raw_data)
        elif artifact == "explanation":
            valid = bool(summary.strip()) and "explain_data" not in failed_tools
        elif artifact == "chat_response":
            valid = bool(summary.strip())
        elif artifact in _VISUAL_ARTIFACTS:
            validation = validate_visualization(artifact, visual_for_artifact(artifact, visualizations))
            valid = validation["valid"]
            task["attempts"] = sum(
                int(call.get("attempts", 1))
                for call in tool_calls
                if call.get("artifact") == artifact
            )
            task["errors"].extend(validation.get("errors", []))
        elif artifact == "verification":
            valid = bool(verification)
            task["attempts"] = 1 if verification else 0
        task["status"] = "completed" if valid else ("failed" if task.get("required") else "skipped")
        if artifact not in _VISUAL_ARTIFACTS and task["attempts"] == 0 and valid:
            task["attempts"] = 1
        if validation:
            task["validation"] = validation
        result.append(task)
    return result


def ledger_status(ledger: list[dict[str, Any]]) -> str:
    required = [task for task in ledger if task.get("required")]
    if required and all(task.get("status") == "completed" for task in required):
        return "complete"
    if any(task.get("status") == "completed" for task in required):
        return "partial"
    return "failed"
