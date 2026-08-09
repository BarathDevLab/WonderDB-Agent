from collections.abc import AsyncIterator
from typing import Any

import pytest

from agent.sse import run_langgraph_sse


class FakeGraph:
    async def astream(
        self, state: dict[str, Any], stream_mode: str = "updates"
    ) -> AsyncIterator[dict[str, Any]]:
        del state, stream_mode
        yield {"plan": {"plan_strategy": "Direct aggregate", "sql_query": "SELECT 1"}}
        yield {"execute": {"raw_results": [{"id": 1}], "explain_cost": 10.0}}
        yield {"summarize": {"summary": "Completed successfully.", "chart_spec": {}}}


@pytest.mark.asyncio
async def test_run_langgraph_sse_emits_valid_frames_per_transition() -> None:
    graph = FakeGraph()
    state = {"prompt": "hello", "tenant_id": "t-1", "user_id": "u-1"}

    frames = [frame async for frame in run_langgraph_sse(graph, state)]

    assert any("event: status" in frame for frame in frames)
    assert any("event: plan_ready" in frame for frame in frames)
    assert any("event: execution_complete" in frame for frame in frames)
    assert any("event: final_response" in frame for frame in frames)
    assert frames[-1] == 'event: complete\ndata: {"ok":true}\n\n'
