"""
worker_nodes.py
===============
Parallel map-reduce workers for visual artifact generation.
Spawned concurrently via the Send API.
Each worker calls a specific MCP tool and appends its result to GlobalState.visualizations.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from agent.mcp_client import call_mcp_tool, get_mcp_session
from utils.logger import get_logger

logger = get_logger(__name__)

async def _call_tool(session: Any, tool_name: str, arguments: dict) -> Any:
    """Call an MCP tool and return parsed JSON response."""
    try:
        result = await session.call_tool(tool_name, arguments=arguments)
    except Exception:
        result = await call_mcp_tool(tool_name, arguments)
    raw_text = result.content[0].text if result.content else "{}"
    return json.loads(raw_text)


async def _call_tool_with_retry(
    session: Any,
    tool_name: str,
    arguments: dict,
    max_attempts: int = 3,
) -> tuple[Any, int]:
    """Retry a deterministic visualization call once on transport/tool failure."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await _call_tool(session, tool_name, arguments), attempt
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                await asyncio.sleep(0.1 * attempt)
    assert last_error is not None
    raise last_error


async def _load_schema_fallback(
    session: Any,
    schema: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Use the MCP schema tool when planner-side schema retrieval is empty."""
    if schema:
        return schema, []
    t0 = time.monotonic()
    discovered, attempts = await _call_tool_with_retry(session, "get_schema", {})
    duration_ms = round((time.monotonic() - t0) * 1000, 1)
    if not isinstance(discovered, list) or not discovered:
        raise ValueError("get_schema returned no table metadata")
    return discovered, [{
        "tool": "get_schema",
        "status": "done",
        "duration_ms": duration_ms,
        "attempts": attempts,
    }]

async def chart_worker_node(state: dict[str, Any]) -> dict[str, Any]:
    """Worker to generate a chart. Input is state fragment with 'dataset' and 'chart_type'."""
    raw_data = state.get("dataset", [])
    chart_type = state.get("chart_type", "auto")
    request = state.get("request", "")
    
    logger.info(f"Chart worker starting for chart_type: {chart_type}")
    
    if not raw_data:
        return {"visualizations": [], "tool_calls": []}
        
    try:
        session = await get_mcp_session()
        t0 = time.monotonic()
        chart_spec, attempts = await _call_tool_with_retry(session, "generate_chart", {
            "raw_data": raw_data,
            "chart_type": chart_type,
            "request": request,
        })
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(f"Chart worker succeeded in {duration_ms}ms")
        
        return {
            "visualizations": [chart_spec],
            "tool_calls": [{
                "tool": "generate_chart", "status": "done",
                "duration_ms": duration_ms, "attempts": attempts,
                "artifact": f"{chart_type}_chart",
            }]
        }
    except Exception as exc:
        logger.warning("generate_chart worker failed: %s", exc)
        return {"visualizations": [], "tool_calls": [{
            "tool": "generate_chart", "status": "error", "duration_ms": 0,
            "artifact": f"{chart_type}_chart",
        }]}


async def er_worker_node(state: dict[str, Any]) -> dict[str, Any]:
    """Worker to generate ER diagram."""
    schema = state.get("schema", [])
    logger.info("ER diagram worker starting")
    try:
        session = await get_mcp_session()
        schema, schema_calls = await _load_schema_fallback(session, schema)
        t0 = time.monotonic()
        er_spec, attempts = await _call_tool_with_retry(session, "generate_flowchart", {
            "diagram_type": "er",
            "schema": schema,
        })
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(f"ER diagram worker succeeded in {duration_ms}ms")
        
        return {
            "visualizations": [er_spec],
            "tool_calls": schema_calls + [{
                "tool": "generate_flowchart[er]", "status": "done",
                "duration_ms": duration_ms, "attempts": attempts, "artifact": "er_diagram",
            }]
        }
    except Exception as exc:
        logger.warning("generate_flowchart(er) worker failed: %s", exc)
        return {"visualizations": [], "tool_calls": [{
            "tool": "generate_flowchart[er]", "status": "error", "duration_ms": 0,
            "artifact": "er_diagram",
        }]}


async def process_worker_node(state: dict[str, Any]) -> dict[str, Any]:
    """Worker to generate Process flow diagram."""
    raw_data = state.get("dataset", [])
    schema = state.get("schema", [])
    title = state.get("title", "")
    logger.info("Process flow worker starting")

    try:
        session = await get_mcp_session()
        schema_calls: list[dict[str, Any]] = []
        if not schema:
            try:
                schema, schema_calls = await _load_schema_fallback(session, schema)
            except Exception as schema_exc:
                if not raw_data:
                    raise
                logger.warning(
                    "Process worker schema fallback failed; checking query-shaped process data: %s",
                    schema_exc,
                )
                schema_calls.append({
                    "tool": "get_schema", "status": "error", "duration_ms": 0,
                })
        t0 = time.monotonic()
        process_spec, attempts = await _call_tool_with_retry(session, "generate_flowchart", {
            "diagram_type": "process",
            "raw_data": raw_data,
            "schema": schema,
            "title": title[:60],
        })
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(f"Process flow worker succeeded in {duration_ms}ms")
        
        return {
            "visualizations": [process_spec],
            "tool_calls": schema_calls + [{
                "tool": "generate_flowchart[process]", "status": "done",
                "duration_ms": duration_ms, "attempts": attempts, "artifact": "process_flow",
            }]
        }
    except Exception as exc:
        logger.warning("generate_flowchart(process) worker failed: %s", exc)
        return {"visualizations": [], "tool_calls": [{
            "tool": "generate_flowchart[process]", "status": "error", "duration_ms": 0,
            "artifact": "process_flow",
        }]}


async def decision_worker_node(state: dict[str, Any]) -> dict[str, Any]:
    """Worker to generate Decision tree diagram."""
    raw_data = state.get("dataset", [])
    title = state.get("title", "")
    logger.info("Decision tree worker starting")
    if not raw_data:
        return {"visualizations": [], "tool_calls": []}
        
    try:
        session = await get_mcp_session()
        t0 = time.monotonic()
        decision_spec, attempts = await _call_tool_with_retry(session, "generate_flowchart", {
            "diagram_type": "decision",
            "raw_data": raw_data,
            "title": title[:60],
        })
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(f"Decision tree worker succeeded in {duration_ms}ms")
        
        return {
            "visualizations": [decision_spec],
            "tool_calls": [{
                "tool": "generate_flowchart[decision]", "status": "done",
                "duration_ms": duration_ms, "attempts": attempts, "artifact": "decision_tree",
            }]
        }
    except Exception as exc:
        logger.warning("generate_flowchart(decision) worker failed: %s", exc)
        return {"visualizations": [], "tool_calls": [{
            "tool": "generate_flowchart[decision]", "status": "error", "duration_ms": 0,
            "artifact": "decision_tree",
        }]}
