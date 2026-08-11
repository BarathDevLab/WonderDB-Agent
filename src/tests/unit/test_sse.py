"""
test_sse.py
===========
Unit tests for the SSE streaming formatter.

Uses a FakeGraph whose node names and state shape match
the current production architecture (supervisor, sql_engine, synthesize).
"""
from collections.abc import AsyncIterator
from typing import Any

import pytest

from agent.sse import run_langgraph_sse


class FakeGraph:
    async def astream(
        self, state: dict[str, Any], stream_mode: str = "updates"
    ) -> AsyncIterator[dict[str, Any]]:
        del state, stream_mode
        # Simulate the three production node transitions
        yield {
            "supervisor": {
                "supervisor_plan": {"intent": "query", "visualizations": ["bar_chart"], "needs_explanation": True},
                "sql_query": "",
                "cached_hit": False,
                "has_fatal_error": False,
            }
        }
        yield {
            "sql_engine": {
                "clean_dataset": [{"month": "Jan", "revenue": 1000}],
                "has_fatal_error": False,
                "error_detail": "",
                "sql_query": "SELECT month, SUM(revenue) FROM orders GROUP BY month",
            }
        }
        yield {
            "synthesize": {
                "summary": "Revenue totals have been generated successfully.",
                "visualizations": [{"type": "bar", "title": "Monthly Revenue", "x_axis": "month", "y_axis": "revenue", "data": []}],
                "tool_calls": [{"tool": "explain_data", "status": "done", "duration_ms": 120.0}],
            }
        }


@pytest.mark.asyncio
async def test_run_langgraph_sse_emits_valid_frames_per_transition() -> None:
    graph = FakeGraph()
    state = {"prompt": "Show monthly revenue", "tenant_id": "t-1", "user_id": "u-1"}

    frames = [frame async for frame in run_langgraph_sse(graph, state)]

    # Must have an initial status event before any nodes run
    assert any("event: status" in frame for frame in frames)
    # Supervisor emits plan_ready
    assert any("event: plan_ready" in frame for frame in frames)
    # sql_engine emits execution_complete (no error)
    assert any("event: execution_complete" in frame for frame in frames)
    # synthesize (terminal) emits final_response
    assert any("event: final_response" in frame for frame in frames)
    # Final frame is always the complete event
    assert frames[-1] == 'event: complete\ndata: {"ok":true}\n\n'


@pytest.mark.asyncio
async def test_run_langgraph_sse_surfaces_fatal_error() -> None:
    """When sql_engine reports has_fatal_error, no execution_complete should fire."""

    class ErrorGraph:
        async def astream(self, state, stream_mode="updates") -> AsyncIterator[dict]:
            yield {
                "supervisor": {
                    "supervisor_plan": {"intent": "query", "visualizations": [], "needs_explanation": True},
                    "sql_query": "",
                    "cached_hit": False,
                    "has_fatal_error": False,
                }
            }
            yield {
                "sql_engine": {
                    "has_fatal_error": True,
                    "error_detail": "column 'rev' does not exist",
                    "clean_dataset": [],
                    "sql_query": "",
                }
            }

    frames = [f async for f in run_langgraph_sse(ErrorGraph(), {})]
    assert any('"phase": "error"' in f or "'phase': 'error'" in f or "error" in f for f in frames)
    assert not any("event: execution_complete" in f for f in frames)
