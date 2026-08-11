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

                if node_name == "supervisor":
                    plan = state_update.get("supervisor_plan", {})
                    yield format_sse_event(
                        "plan_ready",
                        {
                            "strategy": f"Intent: {plan.get('intent', 'query')}",
                            "sql": state_update.get("sql_query", ""), # might be from cache
                        },
                    )
                    if state_update.get("cached_hit"):
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
                            {"phase": "summarizing", "message": "Synthesizing answer from cached execution..."},
                        )
                    elif plan.get("intent") == "query":
                        yield format_sse_event(
                            "status",
                            {"phase": "executing", "message": "Generating SQL and executing query..."},
                        )
                    elif plan.get("intent") == "schema":
                        yield format_sse_event(
                            "status",
                            {"phase": "summarizing", "message": "Generating schema diagram..."},
                        )
                    elif plan.get("intent") in ("chat", "contextual"):
                        yield format_sse_event(
                            "status",
                            {"phase": "summarizing", "message": "Formulating response..."},
                        )

                elif node_name == "sql_engine":
                    summary = state_update.get("summary", "")
                    if summary and (summary.startswith("MCP execution error") or summary.startswith("SQL generation failed")):
                        yield format_sse_event(
                            "status",
                            {
                                "phase": "error",
                                "message": f"Execution error encountered: {summary}",
                            },
                        )
                    else:
                        results = state_update.get("clean_dataset", [])
                        yield format_sse_event(
                            "execution_complete",
                            {
                                "rows": len(results),
                                "data": results,
                                "cost": 0.0, # explain cost is hidden in subgraph for now
                            },
                        )
                        yield format_sse_event(
                            "status",
                            {"phase": "summarizing", "message": "Synthesizing answer and visual specs..."},
                        )

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
