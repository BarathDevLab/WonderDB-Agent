import json

from mcp_server.server import (
    _build_decision_tree,
    _build_process_flow,
    _detect_decision_mode,
    _detect_process_mode,
    generate_flowchart,
)


def test_analytical_rows_render_agent_workflow_not_a_row_chain() -> None:
    rows = [
        {"month": "2026-02-01", "product_name": "Keyboard", "total_revenue": 150},
        {"month": "2026-03-01", "product_name": "Laptop", "total_revenue": 1200},
    ]

    assert _detect_process_mode(rows) == "agent_pipeline"
    mermaid = _build_process_flow(rows, "Explain revenue and show the process flow")

    assert "Discover relevant schema" in mermaid
    assert "All requested outputs delivered?" in mermaid
    assert "Repair failed task" in mermaid
    assert "2026-02-01" not in mermaid
    assert "Revenue: 150" not in mermaid


def test_transition_rows_render_aggregated_state_flow() -> None:
    rows = [
        {"from_status": "New", "to_status": "Paid", "transition_count": 4},
        {"from_status": "New", "to_status": "Paid", "transition_count": 3},
        {"from_status": "Paid", "to_status": "Shipped", "transition_count": 6},
    ]

    assert _detect_process_mode(rows) == "state_transitions"
    mermaid = _build_process_flow(rows)

    assert 'S0["New"]' in mermaid
    assert 'S1["Paid"]' in mermaid
    assert "S0 -->|7| S1" in mermaid
    assert 'S2["Shipped"]' in mermaid


def test_ordered_step_rows_render_step_details_in_order() -> None:
    rows = [
        {"step_order": 2, "step_name": "Approve", "owner": "Finance"},
        {"step_order": 1, "step_name": "Review", "owner": "Sales"},
    ]

    assert _detect_process_mode(rows) == "ordered_steps"
    mermaid = _build_process_flow(rows)

    assert mermaid.index("Review<br/>Owner: Sales") < mermaid.index("Approve<br/>Owner: Finance")
    assert "START --> STEP0" in mermaid
    assert "STEP1 --> DONE" in mermaid


def test_arbitrary_analytics_do_not_fabricate_a_decision_tree() -> None:
    rows = [
        {"month": "2026-01", "product": "Keyboard", "revenue": 150},
        {"month": "2026-02", "product": "Laptop", "revenue": 1200},
    ]

    assert _detect_decision_mode(rows) == "not_applicable"
    mermaid = _build_decision_tree(rows, "Show revenue as a decision tree")

    assert "NOT_APPLICABLE" in mermaid
    assert "revenue >" not in mermaid
    assert "2026-01" not in mermaid


def test_labeled_rows_build_a_data_learned_classification_tree() -> None:
    rows = [
        {"risk_score": 20, "income": 25_000, "outcome": "Decline"},
        {"risk_score": 30, "income": 32_000, "outcome": "Decline"},
        {"risk_score": 40, "income": 45_000, "outcome": "Decline"},
        {"risk_score": 70, "income": 55_000, "outcome": "Approve"},
        {"risk_score": 80, "income": 70_000, "outcome": "Approve"},
        {"risk_score": 90, "income": 90_000, "outcome": "Approve"},
    ]

    assert _detect_decision_mode(rows) == "learned_classification"
    mermaid = _build_decision_tree(rows)

    assert "risk_score <= 55?" in mermaid
    assert "outcome: Decline" in mermaid
    assert "outcome: Approve" in mermaid
    assert "-->|Yes|" in mermaid
    assert "-->|No|" in mermaid


def test_explicit_rule_hierarchy_preserves_parent_and_branch_meaning() -> None:
    rows = [
        {"node_id": "root", "parent_id": None, "node_label": "Risk score above 70?", "node_type": "decision"},
        {"node_id": "yes", "parent_id": "root", "node_label": "Manual review", "node_type": "outcome", "branch": "Yes"},
        {"node_id": "no", "parent_id": "root", "node_label": "Auto approve", "node_type": "outcome", "branch": "No"},
    ]

    assert _detect_decision_mode(rows) == "rule_hierarchy"
    mermaid = _build_decision_tree(rows)

    assert 'D0{"Risk score above 70?"}' in mermaid
    assert 'D1(["Manual review"])' in mermaid
    assert "D0 -->|Yes| D1" in mermaid
    assert "D0 -->|No| D2" in mermaid


def test_decision_tool_returns_mode_and_prediction_target() -> None:
    rows = [
        {"score": 10, "outcome": "No"},
        {"score": 20, "outcome": "No"},
        {"score": 80, "outcome": "Yes"},
        {"score": 90, "outcome": "Yes"},
    ]

    result = json.loads(generate_flowchart("decision", raw_data=rows))

    assert result["diagram_type"] == "decision"
    assert result["decision_mode"] == "learned_classification"
    assert result["decision_target"] == "outcome"
    assert result["process_mode"] is None
