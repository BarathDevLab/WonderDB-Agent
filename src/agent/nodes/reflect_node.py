"""
reflect_node
============
Self-correction node in the SQL retry loop.
Runs after execute_node when a db_error is detected.
Enriches the error context and increments the retry counter so
sql_gen_node can generate a corrected query on the next attempt.
"""
from agent.state import SQLSubgraphState
from utils.logger import get_logger

logger = get_logger(__name__)


async def reflect_node(state: SQLSubgraphState) -> SQLSubgraphState:
    """
    Build enriched reflection instructions for the next sql_gen attempt.
    The error_message is what sql_gen_node reads to self-correct.
    """
    retry_count = state.get("retry_count", 0) + 1
    db_error = state.get("db_error", "Unknown execution error").strip()
    generated_sql = state.get("generated_sql", "").strip()

    # Build structured reflection — gives the LLM specific, actionable guidance
    reflection_lines = [
        f"Attempt #{retry_count} failed.",
        f"Error received: {db_error}",
    ]

    if generated_sql:
        # Limit SQL echo to 500 chars to stay within token budget
        truncated = generated_sql[:500] + ("..." if len(generated_sql) > 500 else "")
        reflection_lines.append(f"Failing SQL was:\n{truncated}")

    reflection_lines.extend([
        "Correction checklist — verify each before regenerating:",
        "  1. All table names match the schema exactly (case-sensitive).",
        "  2. All column names are spelled correctly and belong to the referenced table.",
        "  3. INTERVAL literals use quoted lowercase units: INTERVAL '3 months'.",
        "  4. No DML statements (INSERT/UPDATE/DELETE/DROP/CREATE).",
        "  5. Ambiguous column references are qualified with the table alias.",
        "  6. GROUP BY includes all non-aggregated columns in SELECT.",
        "  7. NULL comparisons use IS NULL / IS NOT NULL.",
    ])

    logger.warning(f"Reflection triggered (attempt {retry_count}). Error: {db_error}")

    return {
        "retry_count": retry_count,
        "error_message": "\n".join(reflection_lines),
        # Do NOT clear db_error here — check_db_error still needs to see it
        # to decide whether to retry. It gets cleared in sql_gen_node on success.
    }
