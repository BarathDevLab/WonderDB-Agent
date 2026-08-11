from collections.abc import AsyncIterator
from typing import Any

from agent.state import AgentState
from core.sse_formatter import format_sse_event


async def run_langgraph_sse(
    graph: Any,
    initial_state: AgentState,
    *,
    stream_mode: str = "updates",
) -> AsyncIterator[str]:
    """Stream LangGraph transitions as typed SSE wire event frames without buffering."""
    yield format_sse_event(
        "status",
        {"phase": "planning", "message": "Analyzing prompt and retrieving schema..."},
    )

    async for chunk in graph.astream(initial_state, stream_mode=stream_mode):
        if isinstance(chunk, dict):
            for node_name, state_update in chunk.items():
                if not isinstance(state_update, dict):
                    continue

                if node_name == "plan":
                    yield format_sse_event(
                        "plan_ready",
                        {
                            "strategy": state_update.get("plan_strategy", ""),
                            "sql": state_update.get("sql_query", ""),
                        },
                    )
                    if state_update.get("cached_hit"):
                        results = state_update.get("raw_results", [])
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
                            {"phase": "summarizing", "message": "Synthesizing answer from cached execution..."},
                        )
                    elif state_update.get("needs_sql"):
                        yield format_sse_event(
                            "status",
                            {"phase": "executing", "message": "Validating AST & executing query..."},
                        )
                    elif state_update.get("intent") == "schema":
                        yield format_sse_event(
                            "status",
                            {"phase": "summarizing", "message": "Generating schema diagram..."},
                        )
                    elif state_update.get("intent") in ("chat", "contextual"):
                        yield format_sse_event(
                            "status",
                            {"phase": "summarizing", "message": "Formulating response..."},
                        )

                elif node_name == "execute":
                    if state_update.get("error_message"):
                        yield format_sse_event(
                            "status",
                            {
                                "phase": "reflection",
                                "message": f"Execution error encountered: {state_update.get('error_message')}",
                            },
                        )
                    else:
                        results = state_update.get("raw_results", [])
                        yield format_sse_event(
                            "execution_complete",
                            {
                                "rows": len(results),
                                "data": results,
                                "cost": state_update.get("explain_cost", 0.0),
                            },
                        )
                        yield format_sse_event(
                            "status",
                            {"phase": "summarizing", "message": "Synthesizing answer and visual specs..."},
                        )

                elif node_name == "reflect":
                    yield format_sse_event(
                        "reflection_retry",
                        {
                            "error": state_update.get("error_message", ""),
                            "retry": state_update.get("retry_count", 1),
                        },
                    )
                    yield format_sse_event(
                        "status",
                        {
                            "phase": "planning",
                            "message": f"Retrying query planning (Attempt #{state_update.get('retry_count', 1)})...",
                        },
                    )

                elif node_name in ("chat", "summarize"):
                    yield format_sse_event(
                        "final_response",
                        {
                            "summary": state_update.get("summary", ""),
                            "chart_spec": state_update.get("chart_spec", {}),
                            "diagram_spec": state_update.get("diagram_spec", []),
                            "tool_calls": state_update.get("tool_calls", []),
                        },
                    )

    yield format_sse_event("complete", {"ok": True})
