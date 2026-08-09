import json
from typing import Any
from agent.state import AgentState
from app.config import get_settings
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


async def _generate_sql_with_llm(
    prompt: str,
    schemas: list[dict[str, Any]],
    error_message: str | None = None,
    api_key: str | None = None,
) -> tuple[str, str] | None:
    """Generate dynamic SQL query using live OpenAI / LLM chat completion API."""
    if not api_key:
        return None

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
    except Exception:
        # Fall back to deterministic synthesis if API error occurs
        return None

    return None


def _generate_candidate_sql_fallback(
    prompt: str,
    schemas: list[dict[str, Any]],
    error_message: str | None = None,
) -> tuple[str, str]:
    """Deterministic fallback synthesis used for offline testing or when API key is unavailable."""
    p_lower = prompt.lower()
    table_names = {s["table_name"] for s in schemas}

    # If this is a self-correction retry, apply targeted repairs
    if error_message:
        if "missing" in error_message.lower() or "not found" in error_message.lower():
            if "orders" in table_names and "customers" in table_names:
                return (
                    "SELECT c.full_name, SUM(o.total_amount) AS total_spent "
                    "FROM customers c JOIN orders o ON c.id = o.customer_id "
                    "GROUP BY c.full_name ORDER BY total_spent DESC LIMIT 10",
                    "Self-corrected join between customers and orders",
                )

    if "month" in p_lower:
        strategy = "Aggregate monthly order totals"
        sql = (
            "SELECT DATE_TRUNC('month', created_at) AS order_month, SUM(total_amount) AS monthly_revenue "
            "FROM orders "
            "GROUP BY order_month "
            "ORDER BY order_month DESC LIMIT 12"
        )
        return sql, strategy

    if "revenue" in p_lower or "sales" in p_lower or "spent" in p_lower or "total" in p_lower:
        if "orders" in table_names and "customers" in table_names:
            strategy = "Aggregate orders joined with customers for tenant spending analytics"
            sql = (
                "SELECT c.full_name, SUM(o.total_amount) AS total_revenue "
                "FROM customers c "
                "JOIN orders o ON c.id = o.customer_id "
                "WHERE o.status = 'completed' "
                "GROUP BY c.full_name "
                "ORDER BY total_revenue DESC LIMIT 10"
            )
            return sql, strategy
        elif "orders" in table_names:
            strategy = "Aggregate monthly order totals"
            sql = (
                "SELECT DATE_TRUNC('month', created_at) AS order_month, SUM(total_amount) AS monthly_revenue "
                "FROM orders "
                "GROUP BY order_month "
                "ORDER BY order_month DESC LIMIT 12"
            )
            return sql, strategy

    if "count" in p_lower or "how many" in p_lower:
        if "customers" in p_lower:
            return "SELECT COUNT(*) AS total_customers FROM customers", "Scalar customer count"
        if "orders" in p_lower:
            return "SELECT status, COUNT(*) AS order_count FROM orders GROUP BY status", "Grouped order status count"

    # Default fallback safe SELECT
    if "orders" in table_names:
        return (
            "SELECT id, total_amount, status, created_at FROM orders ORDER BY created_at DESC LIMIT 20",
            "Recent orders retrieval strategy",
        )
    return (
        "SELECT id, full_name, created_at FROM customers ORDER BY created_at DESC LIMIT 20",
        "Recent customers retrieval strategy",
    )


async def plan_node(state: AgentState) -> AgentState:
    """Semantic cache lookup, schema RAG retrieval, and dynamic LLM / fallback SQL generation."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default-tenant")
    session_id = state.get("session_id", f"session-{tenant_id}")
    error_message = state.get("error_message")

    # 1. Semantic Cache Gate (Fast Return check)
    if not error_message:
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
                "plan_strategy": strategy,
                "sql_query": sql_query,
                "raw_results": cached.get("raw_results", []),
                "summary": cached.get("summary", ""),
                "chart_spec": cached.get("chart_spec", {}),
                "error_message": "",
                "current_phase": "planning_complete",
            }

    # 2. Schema RAG Retrieval (Dense vector search + FK graph traversal)
    retrieved_schemas = await retrieve_schema_context(prompt, tenant_id)

    # 3. Dynamic LLM Generation (with deterministic offline fallback)
    settings = get_settings()
    llm_result = await _generate_sql_with_llm(
        prompt=prompt,
        schemas=retrieved_schemas,
        error_message=error_message,
        api_key=settings.openai_api_key,
    )

    if llm_result:
        sql_query, strategy = llm_result
    else:
        sql_query, strategy = _generate_candidate_sql_fallback(prompt, retrieved_schemas, error_message)

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
