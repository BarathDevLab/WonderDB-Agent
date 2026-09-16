import pytest

import agent.sql_subgraph as sql_subgraph
from services.decision_tree_contract import (
    assess_decision_tree_rows,
    normalize_decision_tree_rows,
)
from services.request_compiler import compile_request


def test_contract_rejects_constant_outcome_and_masked_identifier() -> None:
    assessment = assess_decision_tree_rows([
        {"membership": "***", "outcome": "completed", "outcome_count": 2},
        {"membership": "***", "outcome": "completed", "outcome_count": 1},
    ])

    assert assessment["ready"] is False
    assert "only 1 distinct outcome" in assessment["reason"]
    assert "no usable branching dimension" in assessment["reason"]


def test_contract_accepts_grounded_segmented_probabilities() -> None:
    assessment = assess_decision_tree_rows([
        {"source_state": "Completed", "outcome": "Electronics", "outcome_count": 8},
        {"source_state": "Completed", "outcome": "Accessories", "outcome_count": 2},
    ])

    assert assessment == {
        "ready": True,
        "mode": "probability_transitions",
        "reason": "",
    }


def test_sql_assessment_rejects_synthetic_tier_for_missing_dimension() -> None:
    assessment = sql_subgraph._assess_decision_result(
        {
            "dataset": [
                {"source_state": "Low", "outcome": "Active", "outcome_count": 2},
                {"source_state": "Low", "outcome": "Inactive", "outcome_count": 1},
            ],
            "generated_sql": (
                "SELECT CASE WHEN COUNT(*) > 5 THEN 'High' ELSE 'Low' END AS source_state, "
                "status AS outcome, COUNT(*) AS outcome_count FROM orders GROUP BY status"
            ),
        },
        {"unavailable_dimensions": ["membership_tier"]},
    )

    assert assessment["ready"] is False
    assert "synthetic replacement segment" in assessment["reason"]


def test_normalizer_promotes_real_varying_source_when_outcome_is_constant() -> None:
    rows, adapted = normalize_decision_tree_rows(
        [
            {"source_state": "Cloud Services", "outcome": "High Value", "outcome_count": 2},
            {"source_state": "Software", "outcome": "High Value", "outcome_count": 2},
        ],
        "SELECT p.category AS source_state, 'High Value' AS outcome, COUNT(*) AS outcome_count",
    )

    assert adapted is True
    assert rows == [
        {"outcome": "Cloud Services", "outcome_count": 2, "outcome_probability": 50.0},
        {"outcome": "Software", "outcome_count": 2, "outcome_probability": 50.0},
    ]


def test_compiler_flags_dimension_missing_from_real_schema() -> None:
    compiled = compile_request(
        "Generate a decision tree showing outcome probabilities based on membership tier.",
        {},
        {"intent": "query", "visualizations": ["decision_tree"], "needs_explanation": True},
        [{
            "table_name": "products",
            "columns": [{"name": "category", "type": "VARCHAR"}],
        }],
    )

    assert compiled["dimensions"] == ["membership_tier"]
    assert compiled["unavailable_dimensions"] == ["membership_tier"]


@pytest.mark.asyncio
async def test_sql_wrapper_requeries_semantically_invalid_decision_rows(monkeypatch) -> None:
    class FakeSQLGraph:
        def __init__(self) -> None:
            self.calls = []

        async def ainvoke(self, state):
            self.calls.append(state)
            if len(self.calls) == 1:
                return {
                    "dataset": [
                        {"membership": "***", "outcome": "completed", "outcome_count": 2},
                        {"membership": "***", "outcome": "completed", "outcome_count": 1},
                    ],
                    "generated_sql": "SELECT id AS membership, 'completed' AS outcome FROM orders",
                    "db_error": "",
                    "tool_calls": [{"tool": "execute_query", "status": "done"}],
                }
            return {
                "dataset": [
                    {"source_state": "Completed", "outcome": "Electronics", "outcome_count": 8},
                    {"source_state": "Completed", "outcome": "Accessories", "outcome_count": 2},
                ],
                "generated_sql": "SELECT status AS source_state, category AS outcome, COUNT(*) AS outcome_count",
                "db_error": "",
                "tool_calls": [{"tool": "execute_query", "status": "done"}],
            }

    fake_graph = FakeSQLGraph()
    monkeypatch.setattr(sql_subgraph, "compiled_sql_subgraph", fake_graph)
    result = await sql_subgraph.sql_engine_wrapper({
        "tenant_id": "tenant-a",
        "prompt": "Generate a probability decision tree based on membership tier",
        "resolved_prompt": "Generate a probability decision tree based on membership tier",
        "supervisor_plan": {"intent": "query", "visualizations": ["decision_tree"]},
        "compiled_request": {
            "dimensions": ["membership_tier"],
            "unavailable_dimensions": ["membership_tier"],
        },
        "retrieved_schemas": [{
            "table_name": "products",
            "columns": [{"name": "category", "type": "VARCHAR", "is_pii": False}],
        }],
    })

    assert len(fake_graph.calls) == 2
    assert "Decision-tree data contract failure" in fake_graph.calls[1]["error_message"]
    assert result["clean_dataset"][0]["outcome"] == "Electronics"
    assert len(result["tool_calls"]) == 2
    assert result["execution_trace"][0]["semantic_repair_count"] == 1
    assert result["execution_trace"][0]["decision_dataset_mode"] == "probability_transitions"
