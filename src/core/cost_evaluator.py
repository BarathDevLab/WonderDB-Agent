from typing import Any
from pydantic import BaseModel


class CostEvaluation(BaseModel):
    total_cost: float
    within_threshold: bool
    has_unindexed_seq_scan: bool = False
    reason: str | None = None


def _inspect_plan_nodes(plan: dict[str, Any], scan_threshold_rows: int = 50000) -> tuple[float, bool]:
    """Recursively traverse EXPLAIN plan node to extract total cost and check sequential scans."""
    total_cost = float(plan.get("Total Cost", 0.0))
    node_type = str(plan.get("Node Type", ""))
    plan_rows = int(plan.get("Plan Rows", 0))

    has_seq_scan = (node_type == "Seq Scan" and plan_rows > scan_threshold_rows)

    for child in plan.get("Plans", []):
        child_cost, child_seq = _inspect_plan_nodes(child, scan_threshold_rows)
        total_cost = max(total_cost, child_cost)
        if child_seq:
            has_seq_scan = True

    return total_cost, has_seq_scan


def evaluate_cost(
    explain_data: float | dict[str, Any] | list[Any],
    threshold: float = 10000.0,
    scan_threshold_rows: int = 50000,
) -> CostEvaluation:
    """Evaluate query cost and index efficiency against architectural limits."""
    if isinstance(explain_data, (int, float)):
        cost = float(explain_data)
        within = cost <= threshold
        reason = None if within else f"Total estimated cost ({cost:.2f}) exceeds threshold ({threshold:.2f})."
        return CostEvaluation(total_cost=cost, within_threshold=within, reason=reason)

    # Handle PostgreSQL EXPLAIN (FORMAT JSON) output
    plan_root: dict[str, Any] | None = None
    if isinstance(explain_data, list) and explain_data:
        first = explain_data[0]
        if isinstance(first, dict) and "Plan" in first:
            plan_root = first["Plan"]
    elif isinstance(explain_data, dict):
        plan_root = explain_data.get("Plan", explain_data)

    if plan_root:
        total_cost, has_seq = _inspect_plan_nodes(plan_root, scan_threshold_rows)
        within = total_cost <= threshold and not has_seq
        reasons = []
        if total_cost > threshold:
            reasons.append(f"Total cost {total_cost:.2f} > {threshold:.2f}")
        if has_seq:
            reasons.append("Unindexed sequential scan detected on large table")
        reason = "; ".join(reasons) if reasons else None

        return CostEvaluation(
            total_cost=total_cost,
            within_threshold=within,
            has_unindexed_seq_scan=has_seq,
            reason=reason,
        )

    return CostEvaluation(total_cost=0.0, within_threshold=True)
