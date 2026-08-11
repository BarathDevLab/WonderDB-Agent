"""
execute_node
============
Calls the MCP execute_query tool which handles:
  RLS SET → EXPLAIN cost gate → conn.fetch → PII redact

This node is now a thin MCP client wrapper for the SQL Subgraph.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from agent.mcp_client import get_mcp_session
from agent.state import SQLSubgraphState

logger = logging.getLogger(__name__)

def _sanitize_sql(sql: str) -> str:
    """
    Normalize Gemini-generated SQL before sending to PostgreSQL.
    Fixes:
      - INTERVAL '3 MONTHS' → INTERVAL '3 months'
      - INTERVAL 3 MONTHS   → INTERVAL '3 months'
      - INTERVAL '3' MONTHS → INTERVAL '3 months'
    """
    # 1. Lowercase inside full quotes: INTERVAL '3 MONTHS' -> INTERVAL '3 months'
    def _lower_quoted(m: re.Match) -> str:
        return f"INTERVAL '{m.group(1).lower()}'"
    sql = re.sub(r"INTERVAL\s+'([^']+)'", _lower_quoted, sql, flags=re.IGNORECASE)

    def _fix_unquoted(m: re.Match) -> str:
        return f"INTERVAL '{m.group(1)} {m.group(2).lower()}'"
        
    _UNITS = r"(years?|months?|weeks?|days?|hours?|minutes?|seconds?)"
        
    # 2. Fix completely unquoted: INTERVAL 3 MONTHS -> INTERVAL '3 months'
    sql = re.sub(r"(?:INTERVAL\s+)?(?<!')\b(\d+)\s+" + _UNITS + r"\b(?!')", _fix_unquoted, sql, flags=re.IGNORECASE)
    
    # 3. Fix partially quoted: INTERVAL '3' MONTHS -> INTERVAL '3 months'
    sql = re.sub(r"(?:INTERVAL\s+)?'(\d+)'\s+" + _UNITS + r"\b(?!')", _fix_unquoted, sql, flags=re.IGNORECASE)

    return sql


async def execute_node(state: SQLSubgraphState) -> SQLSubgraphState:
    """Delegate SQL execution to the MCP execute_query tool."""
    raw_sql = state.get("generated_sql", "").strip()
    sql = _sanitize_sql(raw_sql)
    logger.info(f"[_sanitize_sql] in: {raw_sql!r} out: {sql!r}")
    tenant_id = state.get("tenant_id", "default-tenant")

    if not sql:
        return {
            "dataset": [],
            "db_error": "No SQL query to execute.",
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

        tool_call = [{"tool": "execute_query", "status": "done", "duration_ms": duration_ms}]

        if "error" in payload:
            logger.warning("execute_query tool error: %s", payload["error"])
            return {
                "dataset": [],
                "explain_cost": payload.get("explain_cost", 0.0),
                "db_error": payload["error"],
                "error_message": payload["error"], # copy to error_message for SQL gen to see
                "tool_calls": tool_call,
            }

        return {
            "dataset": payload.get("raw_results", []),
            "explain_cost": payload.get("explain_cost", 0.0),
            "db_error": "",
            "error_message": "",
            "tool_calls": tool_call,
        }

    except Exception as exc:
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.error("execute_node MCP call failed: %s", exc)
        tool_call = [{"tool": "execute_query", "status": "error", "duration_ms": duration_ms}]
        return {
            "dataset": [],
            "db_error": f"MCP execution error: {exc}",
            "error_message": f"MCP execution error: {exc}",
            "tool_calls": tool_call,
        }
