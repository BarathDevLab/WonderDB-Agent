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

from agent.mcp_client import get_mcp_session
from utils.logger import get_logger

logger = get_logger(__name__)

async def _call_tool(session: Any, tool_name: str, arguments: dict) -> dict[str, Any]:
    """Call an MCP tool and return parsed JSON response."""
    result = await session.call_tool(tool_name, arguments=arguments)
    raw_text = result.content[0].text if result.content else "{}"
    return json.loads(raw_text)


async def _call_tool_with_retry(
    session: Any,
    tool_name: str,
    arguments: dict,
    max_attempts: int = 2,
) -> tuple[dict[str, Any], int]:
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
            }]
        }
    except Exception as exc:
        logger.warning("generate_chart worker failed: %s", exc)
        return {"visualizations": [], "tool_calls": [{"tool": "generate_chart", "status": "error", "duration_ms": 0}]}


async def er_worker_node(state: dict[str, Any]) -> dict[str, Any]:
    """Worker to generate ER diagram."""
    schema = state.get("schema", [])
    logger.info("ER diagram worker starting")
    try:
        session = await get_mcp_session()
        t0 = time.monotonic()
        er_spec, attempts = await _call_tool_with_retry(session, "generate_flowchart", {
            "diagram_type": "er",
            "schema": schema,
        })
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(f"ER diagram worker succeeded in {duration_ms}ms")
        
        return {
            "visualizations": [er_spec],
            "tool_calls": [{
                "tool": "generate_flowchart[er]", "status": "done",
                "duration_ms": duration_ms, "attempts": attempts,
            }]
        }
    except Exception as exc:
        logger.warning("generate_flowchart(er) worker failed: %s", exc)
        return {"visualizations": [], "tool_calls": [{"tool": "generate_flowchart[er]", "status": "error", "duration_ms": 0}]}


async def process_worker_node(state: dict[str, Any]) -> dict[str, Any]:
    """Worker to generate Process flow diagram."""
    raw_data = state.get("dataset", [])
    title = state.get("title", "")
    logger.info("Process flow worker starting")
    if not raw_data:
        return {"visualizations": [], "tool_calls": []}
        
    try:
        session = await get_mcp_session()
        t0 = time.monotonic()
        process_spec, attempts = await _call_tool_with_retry(session, "generate_flowchart", {
            "diagram_type": "process",
            "raw_data": raw_data,
            "title": title[:60],
        })
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.info(f"Process flow worker succeeded in {duration_ms}ms")
        
        return {
            "visualizations": [process_spec],
            "tool_calls": [{
                "tool": "generate_flowchart[process]", "status": "done",
                "duration_ms": duration_ms, "attempts": attempts,
            }]
        }
    except Exception as exc:
        logger.warning("generate_flowchart(process) worker failed: %s", exc)
        return {"visualizations": [], "tool_calls": [{"tool": "generate_flowchart[process]", "status": "error", "duration_ms": 0}]}


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
                "duration_ms": duration_ms, "attempts": attempts,
            }]
        }
    except Exception as exc:
        logger.warning("generate_flowchart(decision) worker failed: %s", exc)
        return {"visualizations": [], "tool_calls": [{"tool": "generate_flowchart[decision]", "status": "error", "duration_ms": 0}]}
