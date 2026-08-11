"""
sql_gen_node
============
Generates SQL based on the user's prompt and schema context.
Lives inside the SQL Subgraph.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from agent.state import SQLSubgraphState
from app.config import get_settings

logger = logging.getLogger(__name__)


def _format_schema_ddl(schemas: list[dict[str, Any]] | str) -> str:
    """Format structured table schemas into concise DDL definitions for LLM context."""
    if isinstance(schemas, str):
        return schemas
        
    ddl_lines: list[str] = []
    for table in schemas:
        t_name = table.get("table_name", "unknown")
        desc = table.get("description", "")
        cols = ", ".join(
            f"{c['name']} {c['type']}{' PRIMARY KEY' if c.get('is_pk') else ''}{' (PII)' if c.get('is_pii') else ''}"
            for c in table.get("columns", [])
        )
        fks = [
            f"FOREIGN KEY ({fk['column']}) REFERENCES {fk['foreign_table']}({fk['foreign_column']})"
            for fk in table.get("foreign_keys", [])
        ]
        fk_str = f", {', '.join(fks)}" if fks else ""
        ddl_lines.append(f"-- {desc}\nCREATE TABLE {t_name} ({cols}{fk_str});")
    return "\n\n".join(ddl_lines)


_SYSTEM_PROMPT = """
You are an AI database assistant SQL generator.
Analyze the user's message and the provided database schema, and return a JSON object with this exact field:

{
  "sql": "SELECT ..."
}

SQL GENERATION RULES (strictly follow for PostgreSQL):
- Date intervals MUST use quoted lowercase strings: INTERVAL '3 months' NOT INTERVAL '3 MONTHS' or 3 MONTHS
- Last N months: WHERE created_at >= NOW() - INTERVAL '3 months'
- Always quote interval values: INTERVAL '1 year', INTERVAL '7 days', INTERVAL '6 months'
- Use DATE_TRUNC('month', col) for monthly grouping
- Use SUM(), COUNT(), AVG() for aggregations
- Always include ORDER BY for time-series queries
- Never use reserved words as column aliases without quoting
- Must be a valid PostgreSQL SELECT only (no DML).

IMPORTANT:
- Output ONLY valid JSON, no markdown, no explanation.
"""


async def _generate_sql(
    prompt: str,
    schema_ddl: str,
    error_message: str | None,
    api_key: str,
    model: str,
) -> str | None:
    """Call Gemini to generate SQL."""
    try:
        import httpx
        user_content = f"Database Schema:\n{schema_ddl}\n\nUser Message: {prompt}"
        if error_message:
            user_content += (
                f"\n\nPrevious SQL attempt FAILED with: {error_message}\n"
                "Generate corrected SQL."
            )

        clean_model = model.strip()
        if clean_model.startswith("models/"):
            clean_model = clean_model[len("models/"):]

        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{_SYSTEM_PROMPT}\n\n{user_content}"}]}],
            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
        }
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{clean_model}:generateContent?key={api_key}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                logger.warning("Gemini SQL gen returned %s: %s", res.status_code, res.text)
                return None

            data = res.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1]
                raw_text = raw_text.rsplit("```", 1)[0].strip()
            return json.loads(raw_text).get("sql")

    except Exception as exc:
        logger.warning("SQL generation failed: %s", exc)
        return None


async def sql_gen_node(state: SQLSubgraphState) -> SQLSubgraphState:
    """
    Generates SQL based on the prompt and prisma_context.
    """
    prompt = state.get("prompt", "")
    error_message = state.get("error_message")
    prisma_context = state.get("prisma_context", [])
    
    settings = get_settings()

    schema_ddl = _format_schema_ddl(prisma_context) if prisma_context else "(no schema available)"

    if not settings.gemini_api_key or not settings.gemini_model:
        return {
            **state,
            "db_error": "Gemini API key/model not configured.",
        }

    sql_query = await _generate_sql(
        prompt=prompt,
        schema_ddl=schema_ddl,
        error_message=error_message,
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )

    if not sql_query:
        return {
            **state,
            "db_error": "SQL generation failed.",
        }

    return {
        **state,
        "generated_sql": sql_query,
        "db_error": "", # Clear previous errors
    }
