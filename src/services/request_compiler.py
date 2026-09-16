"""Compile natural language and conversation state into a stable request contract."""
from __future__ import annotations

import re
from typing import Any

from services.request_requirements import requested_visualizations_from_prompt


_TIME_GRAINS = ("day", "week", "month", "quarter", "year")
_MEASURE_WORDS = (
    "revenue", "sales", "profit", "cost", "spend", "amount", "quantity",
    "count", "average", "total", "growth", "rate", "margin",
)


def _unique_matches(pattern: str, text: str) -> list[str]:
    return list(dict.fromkeys(match.lower() for match in re.findall(pattern, text, re.IGNORECASE)))


def compile_request(
    prompt: str,
    conversation_context: dict[str, Any] | None,
    plan: dict[str, Any],
    schemas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create deterministic IR that constrains a weaker planning/SQL model."""
    context = conversation_context or {}
    lowered = prompt.lower()
    explicit_visuals = requested_visualizations_from_prompt(prompt)
    planned_visuals = list(plan.get("visualizations", []))
    artifacts = list(dict.fromkeys(planned_visuals + explicit_visuals))

    grain = next(
        (item for item in _TIME_GRAINS if re.search(rf"\b(?:by|per|each|grouped by)\s+{item}\b", lowered)),
        None,
    )
    measures = [word for word in _MEASURE_WORDS if re.search(rf"\b{word}\b", lowered)]
    dimensions = _unique_matches(
        r"\b(?:by|per|for each|grouped by)\s+([a-z][a-z0-9_]*)\b",
        lowered,
    )
    based_on = re.search(
        r"\bbased on\s+([a-z][a-z0-9_]*(?:\s+[a-z][a-z0-9_]*)?)(?=\s*(?:[.,;]|$))",
        lowered,
    )
    if based_on:
        dimension = "_".join(based_on.group(1).split())
        if dimension not in dimensions:
            dimensions.append(dimension)
    if grain and grain not in dimensions:
        dimensions.append(grain)

    limit_match = re.search(r"\b(?:top|bottom|limit(?:ed)? to)\s+(\d{1,4})\b", lowered)
    filters = _unique_matches(
        r"\b(?:where|with|only|excluding|exclude)\s+([^,.;]+)",
        prompt,
    )
    operation = "read"
    if re.search(
        r"\b(?:delete\s+from|drop\s+(?:table|schema|database)|truncate(?:\s+table)?|"
        r"update\s+[a-z_][a-z0-9_.]*\s+set|insert\s+into|alter\s+table|"
        r"grant\s+.+\s+on|revoke\s+.+\s+(?:on|from))\b",
        lowered,
    ):
        operation = "rejected_write"

    decision_mode = None
    if "decision_tree" in artifacts:
        if re.search(r"\b(?:probability|probabilities|likelihood|path|paths|transition)\b", lowered):
            decision_mode = "probability_paths"
        elif re.search(r"\b(?:rule|rules|policy|policies|condition|conditions)\b", lowered):
            decision_mode = "rule_hierarchy"
        else:
            decision_mode = "classification"

    schema_columns = {
        str(column.get("name", "")).lower()
        for table in schemas or []
        for column in table.get("columns", [])
        if column.get("name")
    }
    unavailable_dimensions = [
        dimension for dimension in dimensions
        if schema_columns and dimension.lower() not in schema_columns
    ]

    return {
        "version": "1.0",
        "original_question": prompt,
        "resolved_question": context.get("resolved_prompt", prompt),
        "intent": plan.get("intent", "query"),
        "operation": operation,
        "measures": measures,
        "dimensions": dimensions,
        "unavailable_dimensions": unavailable_dimensions,
        "filters": filters,
        "time_grain": grain,
        "row_limit": int(limit_match.group(1)) if limit_match else None,
        "requested_artifacts": artifacts,
        "decision_tree_mode": decision_mode,
        "needs_explanation": bool(plan.get("needs_explanation")),
        "is_followup": bool(context.get("is_followup")),
        "followup_kind": context.get("followup_kind", "none"),
        "previous_sql": context.get("previous_sql", "") if context.get("is_followup") else "",
        "constraints": [
            "read_only_sql",
            "use_only_provided_schema",
            "current_request_overrides_history",
            "deliver_every_requested_artifact",
        ],
    }
