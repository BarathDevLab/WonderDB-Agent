from services.response_verification import verify_agent_response


def test_verifier_accepts_complete_multi_artifact_response() -> None:
    result = verify_agent_response(
        supervisor_plan={
            "intent": "query",
            "visualizations": ["line_chart", "er_diagram"],
            "needs_explanation": True,
        },
        sql_query="SELECT month, revenue FROM monthly_revenue",
        raw_data=[{"month": "2026-01", "revenue": 100}],
        visualizations=[
            {"type": "line", "data": {"datasets": [{"data": [100]}]}},
            {"diagram_type": "er", "mermaid": "erDiagram\n  A ||--o{ B : has"},
        ],
        summary="Revenue was 100 in January.",
        data_analysis={"row_count": 1, "data_quality": {}},
        schema_available=True,
    )

    assert result["verified"] is True
    assert result["status"] == "complete"
    assert result["missing_artifacts"] == []


def test_verifier_reports_partial_response_and_failed_tool() -> None:
    result = verify_agent_response(
        supervisor_plan={
            "intent": "query",
            "visualizations": ["pie_chart"],
            "needs_explanation": True,
        },
        sql_query="SELECT status, COUNT(*) FROM orders GROUP BY status",
        raw_data=[{"status": "complete", "count": 4}],
        summary="Four orders are complete.",
        data_analysis={"row_count": 1, "data_quality": {}},
        tool_calls=[{"tool": "generate_chart", "status": "error"}],
    )

    assert result["verified"] is False
    assert result["status"] == "partial"
    assert result["missing_artifacts"] == ["pie_chart"]
    assert "Tool failed: generate_chart" in result["warnings"]


def test_verifier_reports_fatal_query_failure() -> None:
    result = verify_agent_response(
        supervisor_plan={"intent": "query", "visualizations": [], "needs_explanation": True},
        summary="The query could not be completed.",
        fatal_error="permission denied",
    )

    assert result["status"] == "failed"
    assert "query_execution" in result["missing_artifacts"]
    assert result["warnings"] == ["Fatal execution error: permission denied"]


def test_verifier_preserves_artifact_omitted_by_planner() -> None:
    result = verify_agent_response(
        supervisor_plan={"intent": "query", "visualizations": ["line_chart"], "needs_explanation": True},
        sql_query="SELECT month, revenue FROM orders",
        raw_data=[{"month": "Jan", "revenue": 10}],
        visualizations=[{"type": "line", "data": {"datasets": [{"data": [10]}]}}],
        summary="Revenue was 10.",
        data_analysis={"row_count": 1, "data_quality": {}},
        original_prompt="Show a line chart and an ER diagram.",
    )

    assert result["status"] == "partial"
    assert result["missing_artifacts"] == ["er_diagram"]


def test_verifier_rejects_placeholder_er_diagram() -> None:
    result = verify_agent_response(
        supervisor_plan={"intent": "schema", "visualizations": ["er_diagram"], "needs_explanation": False},
        visualizations=[{"diagram_type": "er", "mermaid": "erDiagram\n  NO_SCHEMA_LOADED"}],
        schema_available=False,
    )

    assert result["verified"] is False
    assert result["missing_artifacts"] == ["schema_context", "er_diagram"]


def test_verifier_requires_semantic_process_mode() -> None:
    common = {
        "supervisor_plan": {
            "intent": "query",
            "visualizations": ["process_flow"],
            "needs_explanation": False,
        },
        "sql_query": "SELECT month, revenue FROM monthly_revenue",
        "raw_data": [{"month": "2026-01", "revenue": 100}],
        "data_analysis": {"row_count": 1, "data_quality": {}},
    }

    invalid = verify_agent_response(
        **common,
        visualizations=[{
            "diagram_type": "process",
            "mermaid": "flowchart TD\n  A --> B",
        }],
    )
    valid = verify_agent_response(
        **common,
        visualizations=[{
            "diagram_type": "process",
            "process_mode": "agent_pipeline",
            "mermaid": "flowchart LR\n  REQUEST --> VERIFY",
        }],
    )

    assert invalid["missing_artifacts"] == ["process_flow"]
    assert valid["verified"] is True
