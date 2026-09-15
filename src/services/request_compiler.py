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

    return {
        "version": "1.0",
        "original_question": prompt,
        "resolved_question": context.get("resolved_prompt", prompt),
        "intent": plan.get("intent", "query"),
        "operation": operation,
        "measures": measures,
        "dimensions": dimensions,
        "filters": filters,
        "time_grain": grain,
        "row_limit": int(limit_match.group(1)) if limit_match else None,
        "requested_artifacts": artifacts,
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
