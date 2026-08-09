import json
import logging
from typing import Any
from agent.state import AgentState
from app.config import get_settings
from db.postgres import get_shared_pool

logger = logging.getLogger(__name__)
from services.schema_rag import retrieve_schema_context
from services.semantic_cache import get_semantic_cache
from services.session_memory import append_session_event


def _format_schema_ddl(schemas: list[dict[str, Any]]) -> str:
    """Format structured table schemas and FKs into concise DDL definitions for LLM context."""
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


async def _generate_sql_with_gemini(
    prompt: str,
    schemas: list[dict[str, Any]],
    error_message: str | None = None,
    api_key: str | None = None,
    model: str = "gemini-flash-latest",
) -> tuple[str, str] | None:
    """Generate dynamic SQL query using Google Gemini API."""
    if not api_key:
        return None

    try:
        import httpx
        ddl_context = _format_schema_ddl(schemas)
        system_instruction = (
            "You are an enterprise Text-to-SQL AI assistant. "
            "Translate the natural language user question into a single valid, safe PostgreSQL SELECT statement. "
            "Output ONLY a valid JSON object with keys 'strategy' and 'sql'. "
            "The SQL must be a strict SELECT query with appropriate JOINs and LIMIT <= 100."
        )

        user_content = f"Database Schemas:\n{ddl_context}\n\nUser Question: {prompt}"
        if error_message:
            user_content += f"\n\nPrevious Attempt Failed With: {error_message}\nPlease fix and adjust the SQL accordingly."

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_instruction}\n\n{user_content}\n\nOutput JSON strictly formatted as: {{\"strategy\": \"...\", \"sql\": \"...\"}}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            }
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                return None
            data = res.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            parsed = json.loads(raw_text.strip())
            sql = parsed.get("sql", "").strip()
            strategy = parsed.get("strategy", "Gemini synthesized SQL query")
            if sql:
                return sql, strategy
    except Exception as exc:
        logger.warning("Gemini SQL generation failed: %s", exc)
        return None
    return None


async def _generate_sql_with_llm(
    prompt: str,
    schemas: list[dict[str, Any]],
    error_message: str | None = None,
    api_key: str | None = None,
    gemini_key: str | None = None,
    gemini_model: str = "gemini-flash-latest",
) -> tuple[str, str] | None:
    """Generate dynamic SQL query using Gemini, OpenAI, or LLM chat completion API."""
    # 1. Try Gemini if configured
    if gemini_key:
        res = await _generate_sql_with_gemini(
            prompt, schemas, error_message, gemini_key, gemini_model
        )
        if res:
            return res

    # 2. Try OpenAI if configured
    if api_key:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key)
            ddl_context = _format_schema_ddl(schemas)

            system_instruction = (
                "You are an enterprise Text-to-SQL AI assistant. "
                "Your task is to translate natural language user questions into a single valid, safe PostgreSQL SELECT statement. "
                "Rules:\n"
                "1. Output ONLY a valid JSON object with keys 'strategy' and 'sql'.\n"
                "2. The SQL must be a strict SELECT statement. Disallow any DML or data modifications.\n"
                "3. Use appropriate JOINs adhering to foreign key relationships.\n"
                "4. Limit unbounded results to at most 100 rows."
            )

            user_content = f"Database Schemas:\n{ddl_context}\n\nUser Question: {prompt}"
            if error_message:
                user_content += f"\n\nPrevious Attempt Failed With: {error_message}\nPlease fix and adjust the SQL accordingly."

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content},
                ],
            )

            raw_content = response.choices[0].message.content or "{}"
            parsed = json.loads(raw_content)
            sql = parsed.get("sql", "").strip()
            strategy = parsed.get("strategy", "LLM synthesized SQL query")
            if sql:
                return sql, strategy
        except Exception as exc:
            logger.warning("Gemini SQL generation failed: %s", exc)
            return None

    return None





async def plan_node(state: AgentState) -> AgentState:
    """Semantic cache lookup, schema RAG retrieval, and dynamic LLM / fallback SQL generation."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default-tenant")
    session_id = state.get("session_id", f"session-{tenant_id}")
    error_message = state.get("error_message")

    settings = get_settings()
    cache_enabled = state.get("enable_cache", settings.enable_semantic_cache)

    # 1. Semantic Cache Gate (Fast Return check)
    if cache_enabled and not error_message:
        cached = await get_semantic_cache(prompt, tenant_id)
        if cached:
            sql_query = cached.get("sql_query", "")
            strategy = "Semantic cache hit (fast return)"
            await append_session_event(
                session_id,
                {"phase": "plan", "prompt": prompt, "sql_query": sql_query, "cache_hit": True},
            )
            return {
                **state,
                "cached_hit": True,
                "ast_valid": True,
                "plan_strategy": strategy,
                "sql_query": sql_query,
                "raw_results": cached.get("raw_results", []),
                "summary": cached.get("summary", ""),
                "chart_spec": cached.get("chart_spec", {}),
                "error_message": "",
                "current_phase": "planning_complete",
            }

    # 2. Schema RAG Retrieval (Live PostgreSQL pgvector + FK graph traversal)
    pool = await get_shared_pool()
    retrieved_schemas = await retrieve_schema_context(prompt, tenant_id, pool)

    # 3. Dynamic LLM Generation (Gemini / OpenAI / deterministic fallback)
    llm_result = await _generate_sql_with_llm(
        prompt=prompt,
        schemas=retrieved_schemas,
        error_message=error_message,
        api_key=settings.openai_api_key,
        gemini_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
    )

    if not llm_result:
        # Fail loudly if LLM fails or no API keys are provided
        error_msg = "Failed to generate SQL. Please ensure valid API keys (Gemini/OpenAI) are configured."
        return {
            **state,
            "cached_hit": False,
            "retrieved_schemas": retrieved_schemas,
            "error_message": error_msg,
            "current_phase": "planning_failed",
        }

    sql_query, strategy = llm_result

    # 4. Append to Session Memory
    await append_session_event(
        session_id,
        {"phase": "plan", "prompt": prompt, "sql_query": sql_query, "strategy": strategy, "cache_hit": False},
    )

    return {
        **state,
        "cached_hit": False,
        "retrieved_schemas": retrieved_schemas,
        "plan_strategy": strategy,
        "sql_query": sql_query,
        "error_message": "",
        "current_phase": "planning_complete",
    }
