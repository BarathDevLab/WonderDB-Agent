"""Deterministic structural validation for generated visual artifacts."""
from __future__ import annotations

from typing import Any


_PROCESS_BASES = {
    "state_transitions": "query_state_transitions",
    "ordered_steps": "query_ordered_steps",
    "schema_flow": "schema_foreign_keys",
}
_DECISION_BASES = {
    "rule_hierarchy": "query_rule_hierarchy",
    "learned_classification": "query_labeled_outcomes",
    "probability_outcomes": "query_outcome_distribution",
    "probability_transitions": "query_transition_probabilities",
}


def validate_visualization(
    artifact: str,
    visual: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate one chart/diagram without relying on an LLM judgment."""
    errors: list[str] = []
    visual = visual or {}

    if artifact.endswith("_chart"):
        expected_type = artifact.removesuffix("_chart")
        if visual.get("type") != expected_type:
            errors.append(f"expected chart type {expected_type!r}")
        data = visual.get("data")
        if not isinstance(data, dict):
            errors.append("chart data must be an object")
        else:
            datasets = data.get("datasets")
            if not isinstance(datasets, list) or not datasets:
                errors.append("chart has no datasets")
            else:
                for index, dataset in enumerate(datasets):
                    points = dataset.get("data") if isinstance(dataset, dict) else None
                    if not isinstance(points, list) or not points:
                        errors.append(f"dataset {index} has no points")
            labels = data.get("labels")
            if expected_type != "scatter" and isinstance(datasets, list) and isinstance(labels, list):
                for index, dataset in enumerate(datasets):
                    points = dataset.get("data", []) if isinstance(dataset, dict) else []
                    if len(points) != len(labels):
                        errors.append(f"dataset {index} length does not match labels")

    else:
        expected_type = {
            "er_diagram": "er",
            "process_flow": "process",
            "decision_tree": "decision",
        }.get(artifact)
        if visual.get("diagram_type") != expected_type:
            errors.append(f"expected diagram type {expected_type!r}")
        mermaid = visual.get("mermaid", "")
        if not isinstance(mermaid, str) or not mermaid.strip():
            errors.append("diagram has no Mermaid source")
        elif any(marker in mermaid for marker in ("NO_SCHEMA_LOADED", "NO_DATA", "NOT_APPLICABLE")):
            errors.append("diagram is a placeholder or not applicable")
        elif expected_type == "er" and not mermaid.lstrip().startswith("erDiagram"):
            errors.append("ER diagram must start with erDiagram")
        elif expected_type in {"process", "decision"} and not mermaid.lstrip().startswith("flowchart"):
            errors.append("flow diagram must start with flowchart")

        if expected_type == "er" and visual.get("generation_basis") != "schema_metadata":
            errors.append("ER diagram is not grounded in schema metadata")
        elif expected_type == "process":
            mode = visual.get("process_mode")
            if mode not in _PROCESS_BASES or visual.get("generation_basis") != _PROCESS_BASES.get(mode):
                errors.append("process flow has no supported grounding mode")
        elif expected_type == "decision":
            mode = visual.get("decision_mode")
            if mode not in _DECISION_BASES or visual.get("generation_basis") != _DECISION_BASES.get(mode):
                errors.append("decision tree has no supported grounding mode")

    return {"valid": not errors, "artifact": artifact, "errors": errors}


def visual_for_artifact(
    artifact: str,
    visualizations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the first generated visual that corresponds to an artifact name."""
    if artifact.endswith("_chart"):
        expected = artifact.removesuffix("_chart")
        candidates = [item for item in visualizations if item.get("type") == expected]
    else:
        expected = {"er_diagram": "er", "process_flow": "process", "decision_tree": "decision"}.get(artifact)
        candidates = [item for item in visualizations if item.get("diagram_type") == expected]
    return next(
        (item for item in reversed(candidates) if validate_visualization(artifact, item)["valid"]),
        candidates[-1] if candidates else None,
    )


def deduplicate_visualizations(
    visualizations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer the latest retry result for each artifact while preserving order."""
    keyed: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for index, item in enumerate(visualizations):
        if item.get("type"):
            key = f"chart:{item['type']}"
        elif item.get("diagram_type"):
            key = f"diagram:{item['diagram_type']}"
        else:
            key = f"other:{index}"
        if key not in keyed:
            order.append(key)
        keyed[key] = item
    return [keyed[key] for key in order]
