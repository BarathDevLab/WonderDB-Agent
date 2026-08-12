"""
sql_gen_node
============
Generates a safe PostgreSQL SELECT query from a natural language prompt
and the schema DDL context retrieved by the supervisor.

Lives exclusively inside the SQL Subgraph — never called from the main graph directly.
"""
from __future__ import annotations

import json
from typing import Any

from agent.state import SQLSubgraphState
from app.config import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


def _format_schema_ddl(schemas: list[dict[str, Any]] | str) -> str:
    """
    Format structured table schemas into concise DDL for LLM context.
    Handles both the structured list format (from schema_rag) and
    a raw string (fallback).
    """
    if isinstance(schemas, str):
        return schemas

    ddl_lines: list[str] = []
    for table in schemas:
        t_name = table.get("table_name", "unknown")
        desc = table.get("description", "")
        cols = ", ".join(
            f"{c['name']} {c['type']}"
            f"{'  PRIMARY KEY' if c.get('is_pk') else ''}"
            f"{'  REFERENCES ' + c['foreign_table'] + '(' + c['foreign_column'] + ')' if c.get('is_fk') and c.get('foreign_table') else ''}"
            f"{'  -- PII' if c.get('is_pii') else ''}"
            for c in table.get("columns", [])
        )
        fks = [
            f"FOREIGN KEY ({fk['column']}) REFERENCES {fk['foreign_table']}({fk['foreign_column']})"
            for fk in table.get("foreign_keys", [])
        ]
        fk_str = f",\n  {', '.join(fks)}" if fks else ""
        header = f"-- {desc}" if desc else ""
        ddl_lines.append(f"{header}\nCREATE TABLE {t_name} (\n  {cols}{fk_str}\n);")
    return "\n\n".join(ddl_lines)


_SYSTEM_PROMPT = """\
You are a deterministic PostgreSQL SQL generator for a read-only enterprise database.

Given the database schema and a natural language request, output ONE JSON object:

{
  "sql": "SELECT ..."
}

═══════════════════════════════════════════════════
POSTGRESQL GENERATION RULES (strictly enforce ALL)
═══════════════════════════════════════════════════

SAFETY — ABSOLUTE RULES:
  1. Output ONLY a SELECT statement. Never INSERT, UPDATE, DELETE, DROP, CREATE,
     GRANT, REVOKE, TRUNCATE, COPY, SET ROLE, VACUUM, or any DDL/DML.
  2. No subqueries that modify data. No CTEs with side effects.
  3. Do not reference tables not present in the schema.

INTERVALS — must use quoted lowercase unit strings:
  ✓ INTERVAL '3 months'   ✓ INTERVAL '1 year'   ✓ INTERVAL '7 days'
  ✗ INTERVAL '3 MONTHS'   ✗ INTERVAL 3 MONTHS   ✗ 3 MONTHS

DATE / TIME:
  • Last N months: WHERE col >= NOW() - INTERVAL 'N months'
  • Monthly grouping: DATE_TRUNC('month', col)
  • Yearly grouping: DATE_TRUNC('year', col)
  • Always add ORDER BY col ASC for time-series queries.

AGGREGATIONS:
  • Use SUM(), COUNT(), AVG(), MIN(), MAX() for metrics.
  • COUNT(DISTINCT col) for unique counts.
  • Always GROUP BY all non-aggregate SELECT columns.
  • Never reference a non-aggregated column in SELECT without GROUP BY.

NULL HANDLING:
  • Use IS NULL / IS NOT NULL, never = NULL or != NULL.
  • Use COALESCE(col, 0) when aggregating nullable numeric columns.
  • Use NULLIF(denominator, 0) to guard against division by zero.

JOINS:
  • Prefer INNER JOIN unless NULLs on the right side are expected (use LEFT JOIN then).
  • Always alias tables when joining: orders o, customers c.
  • Qualify ambiguous column references: o.id, c.id — never bare "id" after a JOIN.

TYPE CASTING:
  • Use CAST(col AS type) or col::type for explicit casts.
  • Cast TEXT → NUMERIC only when the column is known numeric-like.

CTEs:
  • Use WITH cte_name AS (...) SELECT ... for complex multi-step queries.
  • CTEs must be SELECT only.

LIMIT:
  • Always include LIMIT unless the query is an aggregation returning a single row.
  • Default: LIMIT 100. The execution engine will enforce a hard cap of 100.

ALIASES:
  • Never use PostgreSQL reserved words as unquoted aliases (e.g. "order", "group", "date").
  • Quote aliases containing spaces or reserved words: AS "Order Date".

OUTPUT:
  • Output ONLY valid JSON. No markdown. No code fences. No explanation.
  • The "sql" value must be a single-line string (escape newlines as \\n if needed).
═══════════════════════════════════════════════════
"""


async def _generate_sql(
    prompt: str,
    schema_ddl: str,
    error_message: str | None,
    api_key: str,
    model: str,
) -> str | None:
    """
    Call Gemini to generate a PostgreSQL SELECT query.
    On retry, includes the previous error so the model can self-correct.
    Returns the raw SQL string or None on failure.
    """
    try:
        import httpx

        # Build the user content block
        user_content = (
            f"Database Schema (DDL):\n```sql\n{schema_ddl}\n```\n\n"
            f"Natural Language Request:\n<request>\n{prompt}\n</request>"
        )
        if error_message:
            user_content += (
                f"\n\nPrevious SQL attempt FAILED with this error:\n"
                f"<error>\n{error_message}\n</error>\n"
                "Fix the error and generate corrected SQL. "
                "Double-check table names, column names, and PostgreSQL syntax."
            )

        clean_model = model.strip()
        if clean_model.startswith("models/"):
            clean_model = clean_model[len("models/"):]

        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{_SYSTEM_PROMPT}\n\n{user_content}"}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
                "maxOutputTokens": 1024,
            },
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{clean_model}:generateContent?key={api_key}"
        )

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                logger.warning("Gemini SQL gen returned %s: %s", res.status_code, res.text[:200])
                return None

            data = res.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Defensive strip of any accidental markdown fence
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1]
                raw_text = raw_text.rsplit("```", 1)[0].strip()

            sql = json.loads(raw_text).get("sql", "").strip()
            if not sql:
                logger.warning("SQL gen returned empty sql field")
                return None
            return sql

    except Exception as exc:
        logger.warning("SQL generation failed: %s", exc)
        return None


async def sql_gen_node(state: SQLSubgraphState) -> SQLSubgraphState:
    """
    Generate a PostgreSQL SELECT query from the user prompt and schema DDL.
    Clears db_error on success so the retry gate doesn't see stale state.
    """
    prompt = state.get("prompt", "")
    error_message = state.get("error_message") or None
    prisma_context = state.get("prisma_context", [])

    settings = get_settings()

    schema_ddl = _format_schema_ddl(prisma_context) if prisma_context else "(no schema available)"

    if not settings.gemini_api_key or not settings.gemini_model:
        logger.error("SQL generation failed: Gemini API key or model not configured.")
        return {
            "db_error": "SQL generation failed: Gemini API key/model not configured.",
            "generated_sql": "",
        }

    logger.info(f"Generating SQL for prompt: {prompt!r}")

    sql_query = await _generate_sql(
        prompt=prompt,
        schema_ddl=schema_ddl,
        error_message=error_message,
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )

    if not sql_query:
        logger.error("SQL generation failed: model returned no valid SQL.")
        return {
            "db_error": "SQL generation failed: model returned no valid SQL.",
            "generated_sql": "",
        }

    logger.info(f"Generated SQL: {sql_query}")

    return {
        "generated_sql": sql_query,
        "db_error": "",           # Clear any previous error — success path
        "error_message": "",      # Clear reflection notes for this attempt
    }
