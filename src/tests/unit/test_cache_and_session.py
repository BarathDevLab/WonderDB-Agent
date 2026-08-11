"""
test_cache_and_session.py
=========================
Unit and integration tests for semantic cache and session memory services.

Bug fixes applied:
  - AgentState → GlobalState (AgentState never existed; was a copy-paste error)
  - Removed retry_count from GlobalState init (belongs to SQLSubgraphState only)
  - Removed stale field assertions (plan_strategy, ast_valid) from old state schema
"""
import pytest

from services.semantic_cache import (
    delete_semantic_cache,
    flush_semantic_cache,
    get_semantic_cache,
    set_semantic_cache,
)
from services.session_memory import session_memory_service


@pytest.mark.asyncio
async def test_semantic_cache_lifecycle() -> None:
    """Full get/set/delete cycle for the semantic cache."""
    prompt = "What is the average order value?"
    tenant_id = "tenant-cache-test"

    await flush_semantic_cache()
    cached_before = await get_semantic_cache(prompt, tenant_id)
    assert cached_before is None

    test_payload = {
        "sql_query": "SELECT AVG(total_amount) FROM orders",
        "summary": "The average order value is $450.00.",
        "chart_spec": {"type": "bar"},
        "raw_results": [{"avg": 450.00}],
    }

    await set_semantic_cache(prompt, test_payload, tenant_id)

    # Exact-key match (O(1) path)
    cached_after = await get_semantic_cache(prompt, tenant_id)
    assert cached_after is not None
    assert cached_after["sql_query"] == test_payload["sql_query"]
    assert cached_after["summary"] == test_payload["summary"]

    await delete_semantic_cache(prompt, tenant_id)
    cached_deleted = await get_semantic_cache(prompt, tenant_id)
    assert cached_deleted is None


@pytest.mark.asyncio
async def test_session_memory_appends_and_retrieves() -> None:
    """Session events should be stored in Redis and retrievable in order."""
    session_id = "session-test-uuid-1"
    await session_memory_service.clear_session(session_id)

    event_1 = {"phase": "plan", "prompt": "Show sales"}
    event_2 = {"phase": "summary", "summary": "Sales are $10,000"}

    await session_memory_service.append_session_event(session_id, event_1)
    await session_memory_service.append_session_event(session_id, event_2)

    history = await session_memory_service.get_session_history(session_id)
    assert len(history) >= 2
    assert history[-2]["phase"] == "plan"
    assert history[-1]["phase"] == "summary"


@pytest.mark.asyncio
async def test_session_memory_clear() -> None:
    """Clearing a session should leave it empty."""
    session_id = "session-test-clear"
    await session_memory_service.append_session_event(session_id, {"phase": "plan"})
    await session_memory_service.clear_session(session_id)
    history = await session_memory_service.get_session_history(session_id)
    assert history == []


@pytest.mark.asyncio
async def test_graph_fast_returns_on_semantic_cache_hit() -> None:
    """Pre-populating the cache should cause the graph to return a cached_hit response."""
    from agent.graph import get_graph
    from agent.state import GlobalState

    graph = get_graph()
    prompt = "Cached Fast Return Query"
    tenant_id = "tenant-fast-return"

    # Pre-populate the cache
    cached_payload = {
        "sql_query": "SELECT 100 AS cached_metric",
        "summary": "Instant cached response.",
        "chart_spec": {"type": "bar"},
        "raw_results": [{"cached_metric": 100}],
    }
    await set_semantic_cache(prompt, cached_payload, tenant_id)

    # Bug fix: removed retry_count (not a GlobalState field) and stale
    # plan_strategy/ast_valid assertions from the original test.
    initial_state: GlobalState = {
        "prompt": prompt,
        "tenant_id": tenant_id,
        "session_id": "sess-fast-1",
        "enable_cache": True,
    }

    final_state = await graph.ainvoke(initial_state)

    assert final_state.get("cached_hit") is True
    assert final_state.get("sql_query") == "SELECT 100 AS cached_metric"
    assert final_state.get("summary") == "Instant cached response."

    # Cleanup
    await delete_semantic_cache(prompt, tenant_id)
