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
from utils.logger import get_logger
from services.artifact_validation import deduplicate_visualizations
from services.execution_control import load_execution_checkpoint, save_execution_checkpoint

logger = get_logger(__name__)


async def run_langgraph_sse(
    graph: Any,
    initial_state: GlobalState,
    *,
    stream_mode: str = "updates",
) -> AsyncIterator[str]:
    """Stream LangGraph state transitions as typed SSE frames without buffering."""
    logger.info("SSE Stream starting")
    request_id = initial_state.get("request_id", "")
    request_hash = initial_state.get("request_fingerprint", "")
    if request_id:
        try:
            checkpoint = await load_execution_checkpoint(request_id)
            if (
                checkpoint
                and checkpoint.get("status") == "complete"
                and checkpoint.get("request_fingerprint") == request_hash
                and checkpoint.get("final_response")
            ):
                yield format_sse_event("status", {
                    "phase": "resumed", "message": "Returning completed idempotent request.",
                })
                yield format_sse_event("final_response", checkpoint["final_response"])
                yield format_sse_event("complete", {"ok": True, "request_id": request_id})
                return
        except Exception as exc:
            logger.warning("Checkpoint lookup failed; starting normal execution: %s", exc)
    yield format_sse_event(
        "status",
        {"phase": "planning", "message": "Analyzing prompt and retrieving schema..."},
    )

    local_visualizations = []
    local_trace: list[dict[str, Any]] = []
    latest_task_ledger: list[dict[str, Any]] = []
    compiled_request: dict[str, Any] = {}
    local_tool_calls: list[dict[str, Any]] = []

    async for chunk in graph.astream(initial_state, stream_mode=stream_mode):
        if not isinstance(chunk, dict):
            continue

        for node_name, state_update in chunk.items():
            logger.info(f"SSE generating events for node: {node_name}")
            if not isinstance(state_update, dict):
                continue

            if "visualizations" in state_update:
                local_visualizations.extend(state_update["visualizations"])
            if "execution_trace" in state_update:
                local_trace.extend(state_update["execution_trace"])
            if state_update.get("task_ledger"):
                latest_task_ledger = state_update["task_ledger"]
            if state_update.get("compiled_request"):
                compiled_request = state_update["compiled_request"]
            if state_update.get("tool_calls"):
                local_tool_calls.extend(state_update["tool_calls"])

            if request_id:
                try:
                    await save_execution_checkpoint(request_id, {
                        "status": "running",
                        "request_fingerprint": request_hash,
                        "last_node": node_name,
                        "execution_trace": local_trace,
                    })
                except Exception as exc:
                    logger.warning("Checkpoint write failed at %s: %s", node_name, exc)

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
                local_visualizations = deduplicate_visualizations(local_visualizations)
                chart_specs = [v for v in local_visualizations if "type" in v]
                chart_spec = chart_specs[0] if chart_specs else {}
                diagram_specs = [v for v in local_visualizations if "diagram_type" in v]

                final_payload = {
                        "summary": state_update.get("summary", ""),
                        "data_analysis": state_update.get("data_analysis", {}),
                        "response_verification": state_update.get("response_verification", {}),
                        "chart_spec": chart_spec,
                        "chart_specs": chart_specs,
                        "diagram_spec": diagram_specs,
                        "visualizations": local_visualizations,
                        "tool_calls": local_tool_calls,
                        "task_ledger": state_update.get("task_ledger", latest_task_ledger),
                        "execution_status": state_update.get("execution_status", "complete"),
                        "execution_trace": local_trace,
                        "compiled_request": compiled_request,
                        "request_id": request_id,
                    }
                if request_id:
                    try:
                        await save_execution_checkpoint(request_id, {
                            "status": "complete",
                            "request_fingerprint": request_hash,
                            "final_response": final_payload,
                            "execution_trace": local_trace,
                        })
                    except Exception as exc:
                        logger.warning("Final checkpoint write failed: %s", exc)
                yield format_sse_event("final_response", final_payload)

    logger.info("SSE Stream complete")
    complete_payload: dict[str, Any] = {"ok": True}
    if request_id:
        complete_payload["request_id"] = request_id
    yield format_sse_event("complete", complete_payload)
