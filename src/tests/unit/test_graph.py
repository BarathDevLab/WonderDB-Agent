import pytest

from agent.graph import get_graph
from agent.state import AgentState


@pytest.mark.asyncio
async def test_langgraph_compilation_and_execution() -> None:
    graph = get_graph()
    assert graph is not None

    initial_state: AgentState = {
        "prompt": "Show monthly revenue",
        "tenant_id": "tenant-100",
        "user_id": "user-abc",
        "retry_count": 0,
    }

    final_state = await graph.ainvoke(initial_state)

    assert final_state["current_phase"] == "summarize_complete"
    assert "monthly_revenue" in final_state["sql_query"]
    assert final_state["ast_valid"] is True
    assert len(final_state["raw_results"]) > 0
    assert final_state["summary"] != ""
    assert final_state["chart_spec"]["type"] == "line"


@pytest.mark.asyncio
async def test_langgraph_reflection_on_customer_spending() -> None:
    graph = get_graph()
    initial_state: AgentState = {
        "prompt": "Who are top customers by total spent?",
        "tenant_id": "tenant-200",
        "user_id": "user-xyz",
        "retry_count": 0,
    }

    final_state = await graph.ainvoke(initial_state)

    assert final_state["current_phase"] == "summarize_complete"
    assert "total_spent" in final_state["sql_query"] or "total_revenue" in final_state["sql_query"]
    assert final_state["ast_valid"] is True
    assert final_state["chart_spec"]["type"] == "bar"
