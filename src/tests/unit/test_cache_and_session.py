import pytest

from agent.graph import get_graph
from agent.state import AgentState
from services.semantic_cache import (
    delete_semantic_cache,
    get_semantic_cache,
    set_semantic_cache,
)
from services.session_memory import session_memory_service


@pytest.mark.asyncio
async def test_semantic_cache_lifecycle() -> None:
    prompt = "What is the average order value?"
    tenant_id = "tenant-cache-test"

    await delete_semantic_cache(prompt, tenant_id)
    cached_before = await get_semantic_cache(prompt, tenant_id)
    assert cached_before is None

    test_payload = {
        "sql_query": "SELECT AVG(total_amount) FROM orders",
        "summary": "The average order value is $450.00.",
        "chart_spec": {"type": "bar"},
        "raw_results": [{"avg": 450.00}],
    }

    await set_semantic_cache(prompt, test_payload, tenant_id)

    cached_after = await get_semantic_cache(prompt, tenant_id)
    assert cached_after is not None
    assert cached_after["sql_query"] == test_payload["sql_query"]
    assert cached_after["summary"] == test_payload["summary"]


@pytest.mark.asyncio
async def test_session_memory_appends_and_retrieves() -> None:
    session_id = "session-test-uuid-1"
    event_1 = {"phase": "plan", "prompt": "Show sales"}
    event_2 = {"phase": "summary", "summary": "Sales are $10,000"}

    await session_memory_service.append_session_event(session_id, event_1)
    await session_memory_service.append_session_event(session_id, event_2)

    history = await session_memory_service.get_session_history(session_id)
    assert len(history) >= 2
    assert history[-2]["phase"] == "plan"
    assert history[-1]["phase"] == "summary"


@pytest.mark.asyncio
async def test_graph_fast_returns_on_semantic_cache_hit() -> None:
    graph = get_graph()
    prompt = "Cached Fast Return Query"
    tenant_id = "tenant-fast-return"

    # Pre-populate cache
    cached_payload = {
        "sql_query": "SELECT 100 AS cached_metric",
        "summary": "Instant cached response.",
        "chart_spec": {"type": "bar"},
        "raw_results": [{"cached_metric": 100}],
    }
    await set_semantic_cache(prompt, cached_payload, tenant_id)

    initial_state: AgentState = {
        "prompt": prompt,
        "tenant_id": tenant_id,
        "session_id": "sess-fast-1",
        "retry_count": 0,
    }

    final_state = await graph.ainvoke(initial_state)

    assert final_state["cached_hit"] is True
    assert final_state["plan_strategy"] == "Semantic cache hit (fast return)"
    assert final_state["sql_query"] == "SELECT 100 AS cached_metric"
    assert final_state["summary"] == "Instant cached response."
