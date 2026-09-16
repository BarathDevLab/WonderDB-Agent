import json

from mcp_server.server import (
    _build_decision_tree,
    _build_process_flow,
    _detect_decision_mode,
    _detect_process_mode,
    generate_flowchart,
)


SCHEMA = [
    {
        "table_name": "customers",
        "columns": [{"name": "customer_id", "type": "integer", "is_pk": True}],
        "foreign_keys": [],
    },
    {
        "table_name": "orders",
        "columns": [
            {"name": "order_id", "type": "integer", "is_pk": True},
            {"name": "customer_id", "type": "integer", "is_fk": True},
        ],
        "foreign_keys": [{
            "column": "customer_id",
            "foreign_table": "customers",
            "foreign_column": "customer_id",
        }],
    },
    {
        "table_name": "order_items",
        "columns": [{"name": "item_id", "type": "integer", "is_pk": True}],
        "foreign_keys": [{
            "column": "order_id",
            "foreign_table": "orders",
            "foreign_column": "order_id",
        }],
    },
]


def test_analytical_rows_render_actual_schema_flow_not_agent_workflow() -> None:
    rows = [
        {"month": "2026-02-01", "product_name": "Keyboard", "total_revenue": 150},
        {"month": "2026-03-01", "product_name": "Laptop", "total_revenue": 1200},
    ]

    assert _detect_process_mode(rows, SCHEMA) == "schema_flow"
    mermaid = _build_process_flow(
        rows,
        "Explain revenue and show the process flow",
        schema=SCHEMA,
    )

    assert 'T0["customers<br/>PK: customer_id"]' in mermaid
    assert "T0 -->" in mermaid
    assert "orders.customer_id" in mermaid
    assert "Discover relevant schema" not in mermaid
    assert "Repair failed task" not in mermaid
    assert "2026-02-01" not in mermaid


def test_analytical_rows_without_schema_relationships_are_not_a_process() -> None:
    rows = [{"month": "2026-02-01", "total_revenue": 150}]

    assert _detect_process_mode(rows, []) == "not_applicable"
    mermaid = _build_process_flow(rows, "Show a process flow", schema=[])

    assert "NOT_APPLICABLE" in mermaid
    assert "Discover relevant schema" not in mermaid


def test_er_relationship_cardinality_runs_from_parent_to_child() -> None:
    result = json.loads(generate_flowchart("er", schema=SCHEMA))

    assert 'CUSTOMERS ||--o{ ORDERS : "customer_id -> customer_id"' in result["mermaid"]
    assert 'ORDERS ||--o{ ORDER_ITEMS : "order_id -> order_id"' in result["mermaid"]
    assert result["generation_basis"] == "schema_metadata"


def test_process_tool_reports_foreign_keys_as_generation_basis() -> None:
    result = json.loads(generate_flowchart("process", raw_data=[], schema=SCHEMA))

    assert result["process_mode"] == "schema_flow"
    assert result["generation_basis"] == "schema_foreign_keys"
    assert "customers" in result["mermaid"]


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


def test_aggregated_outcomes_build_probability_decision_tree() -> None:
    rows = [
        {"status": "Delivered", "status_count": 18},
        {"status": "Processing", "status_count": 2},
    ]

    assert _detect_decision_mode(rows) == "probability_outcomes"
    result = json.loads(generate_flowchart("decision", raw_data=rows))

    assert result["decision_mode"] == "probability_outcomes"
    assert result["generation_basis"] == "query_outcome_distribution"
    assert result["decision_target"] == "status"
    assert "Delivered" in result["mermaid"]
    assert "90.0% · n=18" in result["mermaid"]
    assert "Processing" in result["mermaid"]
    assert "10.0% · n=2" in result["mermaid"]
    assert "NOT_APPLICABLE" not in result["mermaid"]


def test_transition_probabilities_build_branching_decision_tree() -> None:
    rows = [
        {"source_state": "Order placed", "outcome": "Delivered", "transition_count": 8},
        {"source_state": "Order placed", "outcome": "Cancelled", "transition_count": 2},
    ]

    assert _detect_decision_mode(rows) == "probability_transitions"
    result = json.loads(generate_flowchart("decision", raw_data=rows))

    assert result["decision_mode"] == "probability_transitions"
    assert result["generation_basis"] == "query_transition_probabilities"
    assert result["decision_target"] == "outcome"
    assert 'D0{"Order placed?"}' in result["mermaid"]
    assert "80.0% · n=8" in result["mermaid"]
    assert "20.0% · n=2" in result["mermaid"]


def test_segmented_outcomes_branch_by_conditioning_dimension() -> None:
    rows = [
        {"membership_tier": "VIP", "purchase_outcome": "Laptop", "outcome_count": 8},
        {"membership_tier": "VIP", "purchase_outcome": "Accessories", "outcome_count": 2},
        {"membership_tier": "Standard", "purchase_outcome": "Laptop", "outcome_count": 3},
        {"membership_tier": "Standard", "purchase_outcome": "Accessories", "outcome_count": 7},
    ]

    result = json.loads(generate_flowchart("decision", raw_data=rows))

    assert result["decision_mode"] == "probability_outcomes"
    assert result["decision_target"] == "purchase_outcome"
    assert 'ROOT{"Membership Tier?"}' in result["mermaid"]
    assert "ROOT -->|VIP| G0" in result["mermaid"]
    assert "ROOT -->|Standard| G1" in result["mermaid"]
    assert "80.0% · n=8" in result["mermaid"]
    assert "70.0% · n=7" in result["mermaid"]
