from mcp_server.server import _build_process_flow, _detect_process_mode


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
