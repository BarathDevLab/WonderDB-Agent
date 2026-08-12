"""
sql_subgraph.py
===============
Isolated subgraph for SQL generation, execution, and reflexive error correction.
Handles up to MAX_RETRIES retry cycles independently of the main graph.

State isolation: inputs/outputs are bridged via sql_engine_wrapper only.
"""
from langgraph.graph import StateGraph, START, END

from agent.state import SQLSubgraphState, GlobalState
from agent.nodes.sql_gen_node import sql_gen_node
from agent.nodes.execute_node import execute_node
from agent.nodes.reflect_node import reflect_node
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3


def build_sql_subgraph():
    sg = StateGraph(SQLSubgraphState)

    sg.add_node("sql_gen", sql_gen_node)
    sg.add_node("execute_db", execute_node)
    sg.add_node("reflect", reflect_node)

    sg.add_edge(START, "sql_gen")
    sg.add_edge("sql_gen", "execute_db")

    def check_db_error(state: SQLSubgraphState) -> str:
        """
        Retry only when BOTH conditions hold:
          1. db_error is non-empty (actual failure occurred)
          2. dataset is empty (no partial results to use)
          3. retry budget not exhausted

        Bug fixed: previously only checked db_error, which could be stale
        from a prior failed attempt even after a successful re-try, causing
        spurious retries.
        """
        has_error = bool(state.get("db_error", "").strip())
        has_data = bool(state.get("dataset"))
        retry_count = state.get("retry_count", 0)

        if has_error and not has_data and retry_count < MAX_RETRIES:
            logger.info(f"check_db_error: Error detected ({retry_count}/{MAX_RETRIES} retries) -> routing to reflect")
            return "reflect"
        if has_error and not has_data:
            logger.info("check_db_error: Max retries exceeded -> routing to END")
        else:
            logger.info("check_db_error: Success -> routing to END")
        return END

    sg.add_conditional_edges("execute_db", check_db_error)
    sg.add_edge("reflect", "sql_gen")

    return sg.compile()


compiled_sql_subgraph = build_sql_subgraph()


async def sql_engine_wrapper(state: GlobalState) -> dict:
    """
    Main-graph node that invokes the isolated SQL subgraph.
    Translates GlobalState fields into SQLSubgraphState, runs the loop,
    then maps results back — exposing only the fields the main graph needs.
    """
    sub_state: SQLSubgraphState = {
        "tenant_id": state.get("tenant_id", "default-tenant"),
        "prompt": state.get("prompt", ""),
        "prisma_context": state.get("retrieved_schemas", []),
        "retry_count": 0,
        "error_message": "",
        "tool_calls": [],
    }

    logger.info("sql_engine_wrapper: Invoking SQL subgraph")
    result = await compiled_sql_subgraph.ainvoke(sub_state)
    logger.info("sql_engine_wrapper: SQL subgraph completed")

    db_error = result.get("db_error", "").strip()
    has_fatal = bool(db_error) and not result.get("dataset")

    return {
        "clean_dataset": result.get("dataset", []),
        "sql_query": result.get("generated_sql", ""),
        "tool_calls": result.get("tool_calls", []),
        # Use the structured sentinel instead of embedding error text in summary
        "has_fatal_error": has_fatal,
        "error_detail": db_error if has_fatal else "",
        # Keep summary empty here; synthesize_node is responsible for final text
        "summary": "",
        "current_phase": "sql_engine_complete",
    }
