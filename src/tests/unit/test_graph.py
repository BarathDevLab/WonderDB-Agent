import pytest

from agent.graph import get_graph
from agent.state import AgentState

SAMPLE_TENANT_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


@pytest.mark.asyncio
async def test_langgraph_compilation_and_execution() -> None:
    graph = get_graph()
    assert graph is not None

    initial_state: AgentState = {
        "prompt": "Show monthly revenue",
        "tenant_id": SAMPLE_TENANT_ID,
        "user_id": "user-abc",
        "retry_count": 0,
    }

    final_state = await graph.ainvoke(initial_state)

    assert final_state["current_phase"] == "summarize_complete"
    assert any(k in final_state["sql_query"].lower() for k in ("revenue", "total_amount", "sum"))
    assert final_state["ast_valid"] is True
    assert len(final_state["raw_results"]) > 0
    assert final_state["summary"] != ""
    assert final_state["chart_spec"]["type"] in ("line", "bar")


@pytest.mark.asyncio
async def test_langgraph_reflection_on_customer_spending() -> None:
    graph = get_graph()
    initial_state: AgentState = {
        "prompt": "Who are top customers by total spent?",
        "tenant_id": SAMPLE_TENANT_ID,
        "user_id": "user-xyz",
        "retry_count": 0,
    }

    final_state = await graph.ainvoke(initial_state)

    assert final_state["current_phase"] == "summarize_complete"
    assert any(k in final_state["sql_query"].lower() for k in ("total_spent", "total_revenue", "sum"))
    assert final_state["ast_valid"] is True
    assert final_state["chart_spec"]["type"] == "bar"
