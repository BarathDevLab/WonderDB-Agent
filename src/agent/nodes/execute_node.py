"""
execute_node
============
Calls the MCP execute_query tool which handles:
  RLS SET → EXPLAIN cost gate → conn.fetch → PII redact

This node is now a thin MCP client wrapper.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from agent.mcp_client import get_mcp_session
from agent.state import AgentState

logger = logging.getLogger(__name__)


async def execute_node(state: AgentState) -> AgentState:
    """Delegate SQL execution to the MCP execute_query tool."""
    sql = state.get("sql_query", "").strip()
    tenant_id = state.get("tenant_id", "default-tenant")
    tool_calls: list[dict[str, Any]] = list(state.get("tool_calls") or [])

    if not sql:
        return {
            **state,
            "ast_valid": False,
            "raw_results": [],
            "error_message": "No SQL query to execute.",
            "current_phase": "execution_failed",
        }

    t0 = time.monotonic()
    try:
        session = await get_mcp_session()
        result = await session.call_tool(
            "execute_query",
            arguments={"sql": sql, "tenant_id": tenant_id},
        )
        duration_ms = round((time.monotonic() - t0) * 1000, 1)

        # Parse MCP tool response
        raw_text = result.content[0].text if result.content else "{}"
        payload: dict[str, Any] = json.loads(raw_text)

        tool_calls.append({"tool": "execute_query", "status": "done", "duration_ms": duration_ms})

        if "error" in payload:
            logger.warning("execute_query tool error: %s", payload["error"])
            return {
                **state,
                "ast_valid": False,
                "raw_results": [],
                "explain_cost": payload.get("explain_cost", 0.0),
                "error_message": payload["error"],
                "tool_calls": tool_calls,
                "current_phase": "execution_failed",
            }

        return {
            **state,
            "ast_valid": True,
            "raw_results": payload.get("raw_results", []),
            "explain_cost": payload.get("explain_cost", 0.0),
            "error_message": "",
            "tool_calls": tool_calls,
            "current_phase": "execution_complete",
        }

    except Exception as exc:
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.error("execute_node MCP call failed: %s", exc)
        tool_calls.append({"tool": "execute_query", "status": "error", "duration_ms": duration_ms})
        return {
            **state,
            "ast_valid": False,
            "raw_results": [],
            "error_message": f"MCP execution error: {exc}",
            "tool_calls": tool_calls,
            "current_phase": "execution_failed",
        }
