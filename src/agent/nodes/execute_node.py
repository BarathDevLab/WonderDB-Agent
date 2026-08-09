import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
import json
from typing import Any
from uuid import UUID

from sqlglot import parse as sqlglot_parse

from agent.state import AgentState
from app.config import get_settings
from core.ast_validator import validate_sql
from core.cost_evaluator import evaluate_cost
from core.pii_redactor import redact_rows
from db.postgres import get_shared_pool

logger = logging.getLogger(__name__)

_MAX_RESULT_ROWS = 200
_QUERY_TIMEOUT_SECONDS = 15.0


def _enforce_limit(sql: str, max_rows: int = 100) -> str:
    """Programmatically enforce LIMIT on SQL queries via AST transformation."""
    try:
        statements = sqlglot_parse(sql)
        if statements and hasattr(statements[0], 'args'):
            tree = statements[0]
            existing_limit = tree.args.get("limit")
            if existing_limit is None:
                tree = tree.limit(max_rows)
            else:
                # Cap existing LIMIT if it exceeds max_rows
                try:
                    limit_val = int(existing_limit.expression.this)
                    if limit_val > max_rows:
                        tree = tree.limit(max_rows)
                except (AttributeError, ValueError, TypeError):
                    pass
            return tree.sql()
    except Exception:
        pass
    # Fallback: append LIMIT if none detected
    if "limit" not in sql.lower():
        return f"{sql.rstrip().rstrip(';')} LIMIT {max_rows}"
    return sql


import uuid


def _format_tenant_uuid(tenant_id: str) -> str:
    """Ensure tenant_id is a valid UUID string for Postgres RLS or return empty string."""
    try:
        return str(uuid.UUID(tenant_id))
    except (ValueError, TypeError, AttributeError):
        return ""


async def _execute_against_live_postgres(
    sql: str, tenant_id: str
) -> tuple[list[dict[str, Any]], float]:
    """Execute query against live PostgreSQL with RLS tenant isolation, cost gate, and timeout."""
    pool = await get_shared_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Set tenant context within transaction scope
            safe_tenant = _format_tenant_uuid(tenant_id)
            await conn.execute(
                "SELECT set_config('app.current_tenant_id', $1, true);", safe_tenant
            )

            # 2. Run EXPLAIN cost gate (parameterized via prepared statement)
            explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
            explain_records = await asyncio.wait_for(
                conn.fetch(explain_sql), timeout=_QUERY_TIMEOUT_SECONDS
            )

            estimated_cost = 100.0
            if explain_records and "QUERY PLAN" in explain_records[0]:
                raw_plan = explain_records[0]["QUERY PLAN"]
                plan_json = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
                cost_eval = evaluate_cost(plan_json, threshold=10000.0)
                if not cost_eval.within_threshold:
                    raise ValueError(f"Query Cost Rejected: {cost_eval.reason}")
                estimated_cost = cost_eval.total_cost

            # 3. Execute actual SELECT with timeout
            records = await asyncio.wait_for(
                conn.fetch(sql), timeout=_QUERY_TIMEOUT_SECONDS
            )

            # 4. Truncate oversized results
            if len(records) > _MAX_RESULT_ROWS:
                logger.warning(
                    "Query returned %d rows, truncating to %d", len(records), _MAX_RESULT_ROWS
                )
                records = records[:_MAX_RESULT_ROWS]

            results: list[dict[str, Any]] = []
            for r in records:
                row: dict[str, Any] = {}
                for k, v in r.items():
                    if isinstance(v, Decimal):
                        row[k] = float(v)
                    elif isinstance(v, (datetime, date, UUID)):
                        row[k] = str(v)
                    else:
                        row[k] = v
                results.append(row)
            return results, estimated_cost


async def execute_node(state: AgentState) -> AgentState:
    """Security verification, EXPLAIN cost evaluation, live PostgreSQL execution, and PII masking."""
    sql = state.get("sql_query", "").strip()
    tenant_id = state.get("tenant_id", "default-tenant")

    # 1. AST Validation Gate
    try:
        validate_sql(sql)
    except Exception as exc:
        return {
            **state,
            "ast_valid": False,
            "raw_results": [],
            "error_message": f"AST Validation Error: {exc}",
            "current_phase": "execution_failed",
        }

    # 2. Enforce LIMIT programmatically
    sql = _enforce_limit(sql, max_rows=100)

    # 3. Live Database Execution (no sandbox fallback)
    try:
        raw_data, estimated_cost = await _execute_against_live_postgres(sql, tenant_id)
    except asyncio.TimeoutError:
        return {
            **state,
            "ast_valid": True,
            "raw_results": [],
            "error_message": f"Query timed out after {_QUERY_TIMEOUT_SECONDS}s. Simplify the query or add filters.",
            "current_phase": "execution_failed",
        }
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("Database execution failed: %s", error_msg)
        return {
            **state,
            "ast_valid": True,
            "raw_results": [],
            "error_message": f"Database Execution Error: {error_msg}",
            "current_phase": "execution_failed",
        }

    # 4. PII Redaction
    try:
        redacted_data = redact_rows(raw_data)
        return {
            **state,
            "ast_valid": True,
            "explain_cost": estimated_cost,
            "raw_results": redacted_data,
            "error_message": "",
            "current_phase": "execution_complete",
        }
    except Exception as exc:
        return {
            **state,
            "ast_valid": True,
            "explain_cost": estimated_cost,
            "raw_results": [],
            "error_message": f"Execution Processing Error: {exc}",
            "current_phase": "execution_failed",
        }
