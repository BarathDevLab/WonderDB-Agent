"""Validate whether query rows can ground a non-fabricated decision tree."""
from __future__ import annotations

from typing import Any
import re


_TARGET_NAMES = {
    "decision", "outcome", "status", "result", "target", "label", "class",
    "prediction", "recommendation",
}
_SOURCE_NAMES = {
    "source", "source_state", "from_state", "from_status", "previous_state",
    "previous_status",
}
_NODE_IDS = {"node_id", "decision_node_id", "rule_id"}
_PARENT_IDS = {"parent_id", "parent_node_id", "parent_rule_id"}
_RULE_LABELS = {"node_label", "question", "condition", "rule"}
_METRIC_SUFFIXES = (
    "count", "total", "frequency", "probability", "percentage", "percent",
    "pct", "share", "likelihood",
)


def _target_key(keys: list[str]) -> str | None:
    for key in keys:
        normalized = key.lower().strip()
        if normalized in _TARGET_NAMES or normalized.endswith(
            ("_outcome", "_status", "_result", "_decision", "_label", "_class")
        ):
            return key
    return None


def assess_decision_tree_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return readiness plus actionable repair details for SQL regeneration."""
    if not rows:
        return {"ready": False, "mode": "none", "reason": "The query returned no rows."}
    keys = list(dict.fromkeys(key for row in rows for key in row))
    normalized = {key.lower().strip(): key for key in keys}
    if (
        any(key in normalized for key in _NODE_IDS)
        and any(key in normalized for key in _PARENT_IDS)
        and any(key in normalized for key in _RULE_LABELS)
    ):
        return {"ready": True, "mode": "rule_hierarchy", "reason": ""}

    target = _target_key(keys)
    outcomes = {
        str(row.get(target)) for row in rows
        if target and row.get(target) is not None
    }
    metric_keys = [
        key for key in keys
        if key.lower().strip() in _METRIC_SUFFIXES
        or key.lower().strip().endswith(tuple(f"_{suffix}" for suffix in _METRIC_SUFFIXES))
    ]
    source = next(
        (key for key in keys if key.lower().strip() in _SOURCE_NAMES),
        None,
    )
    excluded = {target, source, *metric_keys}
    group_keys = [
        key for key in keys
        if key not in excluded
        and not key.lower().endswith("_id")
        and len({str(row.get(key)) for row in rows if row.get(key) is not None}) >= 2
    ]

    if metric_keys and target and (len(outcomes) >= 2 or group_keys):
        return {
            "ready": True,
            "mode": "probability_transitions" if source else "probability_outcomes",
            "reason": "",
        }
    if target and len(rows) >= 4 and len(outcomes) >= 2 and group_keys:
        return {"ready": True, "mode": "learned_classification", "reason": ""}

    reason_parts = []
    if not target:
        reason_parts.append("no outcome/target column was returned")
    elif len(outcomes) < 2:
        reason_parts.append(
            f"only {len(outcomes)} distinct outcome was returned ({', '.join(sorted(outcomes)) or 'none'})"
        )
    if not metric_keys and len(rows) < 4:
        reason_parts.append("aggregated rows have no count or probability column")
    if not group_keys and len(outcomes) < 2:
        reason_parts.append("there is no usable branching dimension")
    return {
        "ready": False,
        "mode": "not_applicable",
        "reason": "; ".join(reason_parts) or "The returned rows cannot ground a decision tree.",
        "keys": keys,
    }


def normalize_decision_tree_rows(
    rows: list[dict[str, Any]],
    sql: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Promote a genuine varying source into outcomes when the outcome is constant."""
    if not rows:
        return rows, False
    keys = list(dict.fromkeys(key for row in rows for key in row))
    source = next((key for key in keys if key.lower().strip() in _SOURCE_NAMES), None)
    target = _target_key(keys)
    count_key = next(
        (key for key in keys if key.lower().endswith("count") or key.lower() in {"count", "total", "frequency"}),
        None,
    )
    if not source or not target or not count_key:
        return rows, False
    sources = {str(row[source]) for row in rows if row.get(source) is not None}
    outcomes = {str(row[target]) for row in rows if row.get(target) is not None}
    if len(sources) < 2 or len(outcomes) >= 2 or "***" in sources:
        return rows, False
    if re.search(
        r"\bCASE\b[\s\S]*?\bEND\s+AS\s+\"?" + re.escape(source) + r"\"?",
        sql,
        re.IGNORECASE,
    ):
        return rows, False

    counts: dict[str, float] = {}
    for row in rows:
        if row.get(source) is None:
            continue
        try:
            count = float(row.get(count_key, 0) or 0)
        except (TypeError, ValueError):
            continue
        label = str(row[source])
        counts[label] = counts.get(label, 0.0) + max(0.0, count)
    total = sum(counts.values())
    if len(counts) < 2 or total <= 0:
        return rows, False
    normalized = [
        {
            "outcome": label,
            "outcome_count": int(count) if count.is_integer() else round(count, 4),
            "outcome_probability": round(count / total * 100, 4),
        }
        for label, count in counts.items()
    ]
    return normalized, True


def decision_repair_feedback(
    assessment: dict[str, Any],
    schemas: list[dict[str, Any]],
    compiled_request: dict[str, Any],
    previous_sql: str,
) -> str:
    """Create concrete SQL repair instructions from schema and failed row shape."""
    categorical: list[str] = []
    for table in schemas:
        table_name = table.get("table_name", "")
        for column in table.get("columns", []):
            name = str(column.get("name", ""))
            data_type = str(column.get("type", "")).lower()
            if (
                name
                and not column.get("is_pii")
                and not name.lower().endswith("_id")
                and name.lower() not in {"id", "name", "full_name", "email", "ssn"}
                and any(token in data_type for token in ("char", "text", "enum", "bool"))
            ):
                categorical.append(f"{table_name}.{name}")
    requested = compiled_request.get("dimensions", [])
    return (
        "Decision-tree data contract failure: " + assessment.get("reason", "invalid row shape") + ". "
        f"The previous SQL was: {previous_sql}. "
        f"Requested conditioning dimensions: {requested or 'not specified'}. "
        f"Available factual categorical columns include: {categorical[:12] or 'none discovered'}. "
        "Generate a different SELECT using only real schema columns. Never alias an ID or a constant "
        "literal as a segment/outcome. For a probability tree return at least two observed outcomes "
        "as outcome, plus outcome_count and outcome_probability. If conditioning on a real category, "
        "alias it source_state. Probabilities must be calculated from database rows."
    )
