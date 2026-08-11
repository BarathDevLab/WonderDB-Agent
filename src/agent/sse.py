"""
sse.py
======
Streams LangGraph state transitions as typed SSE wire-frame events.

Event types emitted (in order):
  status            → phase progress updates
  plan_ready        → supervisor decision available
  execution_complete → SQL results returned
  final_response    → summary, charts, diagrams (terminal event)
  error             → unrecoverable error during streaming
  complete          → graph finished successfully
"""
from collections.abc import AsyncIterator
from typing import Any

from agent.state import GlobalState
from core.sse_formatter import format_sse_event


async def run_langgraph_sse(
    graph: Any,
    initial_state: GlobalState,
    *,
    stream_mode: str = "updates",
) -> AsyncIterator[str]:
    """Stream LangGraph state transitions as typed SSE frames without buffering."""
    yield format_sse_event(
        "status",
        {"phase": "planning", "message": "Analyzing prompt and retrieving schema..."},
    )

    async for chunk in graph.astream(initial_state, stream_mode=stream_mode):
        if not isinstance(chunk, dict):
            continue

        for node_name, state_update in chunk.items():
            if not isinstance(state_update, dict):
                continue

            # ── supervisor ────────────────────────────────────────────────
            if node_name == "supervisor":
                plan = state_update.get("supervisor_plan", {})
                intent = plan.get("intent", "query")

                yield format_sse_event(
                    "plan_ready",
                    {
                        "strategy": f"Intent: {intent}",
                        "sql": state_update.get("sql_query", ""),
                    },
                )

                if state_update.get("cached_hit"):
                    results = state_update.get("clean_dataset", [])
                    yield format_sse_event(
                        "execution_complete",
                        {"rows": len(results), "data": results, "cost": 0.0},
                    )
                    yield format_sse_event(
                        "status",
                        {"phase": "summarizing", "message": "Synthesizing answer from cache..."},
                    )
                elif intent == "query":
                    yield format_sse_event(
                        "status",
                        {"phase": "executing", "message": "Generating SQL and executing query..."},
                    )
                elif intent == "schema":
                    yield format_sse_event(
                        "status",
                        {"phase": "summarizing", "message": "Generating schema diagram..."},
                    )
                elif intent in ("chat", "contextual"):
                    yield format_sse_event(
                        "status",
                        {"phase": "responding", "message": "Formulating response..."},
                    )
                elif intent == "error":
                    yield format_sse_event(
                        "status",
                        {"phase": "error", "message": "Unable to process this request."},
                    )

            # ── sql_engine ────────────────────────────────────────────────
            elif node_name == "sql_engine":
                # Use structured sentinel — no more fragile string prefix matching
                if state_update.get("has_fatal_error"):
                    yield format_sse_event(
                        "status",
                        {
                            "phase": "error",
                            "message": f"Query error: {state_update.get('error_detail', 'unknown error')}",
                        },
                    )
                else:
                    results = state_update.get("clean_dataset", [])
                    yield format_sse_event(
                        "execution_complete",
                        {
                            "rows": len(results),
                            "data": results,
                            "cost": 0.0,
                        },
                    )
                    yield format_sse_event(
                        "status",
                        {"phase": "summarizing", "message": "Synthesizing answer and visual specs..."},
                    )

            # ── chat / synthesize (terminal nodes) ────────────────────────
            elif node_name in ("chat", "synthesize"):
                visualizations = state_update.get("visualizations", [])
                chart_spec = next((v for v in visualizations if "type" in v), {})
                diagram_specs = [v for v in visualizations if "diagram_type" in v]

                yield format_sse_event(
                    "final_response",
                    {
                        "summary": state_update.get("summary", ""),
                        "chart_spec": chart_spec,
                        "diagram_spec": diagram_specs,
                        "tool_calls": state_update.get("tool_calls", []),
                    },
                )

    yield format_sse_event("complete", {"ok": True})
