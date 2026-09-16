"""
sql_subgraph.py
===============
Isolated subgraph for SQL generation, execution, and reflexive error correction.
Handles up to MAX_RETRIES retry cycles independently of the main graph.

State isolation: inputs/outputs are bridged via sql_engine_wrapper only.
"""
import re

from langgraph.graph import StateGraph, START, END

from agent.state import SQLSubgraphState, GlobalState
from agent.nodes.sql_gen_node import sql_gen_node
from agent.nodes.execute_node import execute_node
from agent.nodes.reflect_node import reflect_node
from services.decision_tree_contract import (
    assess_decision_tree_rows,
    decision_repair_feedback,
    normalize_decision_tree_rows,
)
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 3
MAX_DECISION_DATA_REPAIRS = 2


def _assess_decision_result(
    result: dict,
    compiled_request: dict,
) -> dict:
    assessment = assess_decision_tree_rows(result.get("dataset", []))
    unavailable = compiled_request.get("unavailable_dimensions", [])
    sql = result.get("generated_sql", "")
    synthetic_source = re.search(
        r"\bCASE\b[\s\S]*?\bEND\s+AS\s+(?:\"?source_state\"?|\"?segment\"?|\"?tier\"?)",
        sql,
        re.IGNORECASE,
    )
    if assessment.get("ready") and unavailable and synthetic_source:
        return {
            "ready": False,
            "mode": "not_applicable",
            "reason": (
                f"requested dimension(s) {unavailable} do not exist in the schema, and the SQL "
                "created a synthetic replacement segment with CASE"
            ),
        }
    return assessment


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
    if state.get("supervisor_plan", {}).get("intent") == "schema":
        logger.info("sql_engine_wrapper: schema-only request; skipping SQL generation")
        return {
            "clean_dataset": [],
            "sql_query": "",
            "tool_calls": [],
            "has_fatal_error": False,
            "error_detail": "",
            "summary": "",
            "current_phase": "schema_ready",
        }

    sub_state: SQLSubgraphState = {
        "tenant_id": state.get("tenant_id", "default-tenant"),
        "prompt": state.get("resolved_prompt") or state.get("prompt", ""),
        "resolved_prompt": state.get("resolved_prompt") or state.get("prompt", ""),
        "prisma_context": state.get("retrieved_schemas", []),
        "retry_count": 0,
        "error_message": "",
        "tool_calls": [],
        "compiled_request": state.get("compiled_request", {}),
    }

    logger.info("sql_engine_wrapper: Invoking SQL subgraph")
    result = await compiled_sql_subgraph.ainvoke(sub_state)
    combined_tool_calls = list(result.get("tool_calls", []))
    semantic_repairs = 0
    decision_dataset_adapted = False
    needs_decision_tree = "decision_tree" in state.get("supervisor_plan", {}).get("visualizations", [])
    assessment: dict = {"ready": True, "mode": "not_requested", "reason": ""}
    while needs_decision_tree and semantic_repairs < MAX_DECISION_DATA_REPAIRS:
        if result.get("db_error"):
            break
        normalized_rows, adapted = normalize_decision_tree_rows(
            result.get("dataset", []), result.get("generated_sql", ""),
        )
        if adapted:
            result = {**result, "dataset": normalized_rows}
            decision_dataset_adapted = True
        assessment = _assess_decision_result(result, state.get("compiled_request", {}))
        if assessment["ready"]:
            break
        semantic_repairs += 1
        feedback = decision_repair_feedback(
            assessment,
            state.get("retrieved_schemas", []),
            state.get("compiled_request", {}),
            result.get("generated_sql", ""),
        )
        logger.warning(
            "Decision-tree dataset repair %d/%d: %s",
            semantic_repairs,
            MAX_DECISION_DATA_REPAIRS,
            assessment["reason"],
        )
        repair_state = {
            **sub_state,
            "error_message": feedback,
            "retry_count": 0,
            "tool_calls": [],
        }
        result = await compiled_sql_subgraph.ainvoke(repair_state)
        combined_tool_calls.extend(result.get("tool_calls", []))
    if needs_decision_tree and not result.get("db_error"):
        normalized_rows, adapted = normalize_decision_tree_rows(
            result.get("dataset", []), result.get("generated_sql", ""),
        )
        if adapted:
            result = {**result, "dataset": normalized_rows}
            decision_dataset_adapted = True
        assessment = _assess_decision_result(result, state.get("compiled_request", {}))
    logger.info("sql_engine_wrapper: SQL subgraph completed")

    db_error = result.get("db_error", "").strip()
    has_fatal = bool(db_error) and not result.get("dataset")

    return {
        "clean_dataset": result.get("dataset", []),
        "sql_query": result.get("generated_sql", ""),
        "tool_calls": combined_tool_calls,
        # Use the structured sentinel instead of embedding error text in summary
        "has_fatal_error": has_fatal,
        "error_detail": db_error if has_fatal else "",
        # Keep summary empty here; synthesize_node is responsible for final text
        "summary": "",
        "current_phase": "sql_engine_complete",
        "execution_trace": [{
            "phase": "query_execution",
            "status": "failed" if has_fatal else "completed",
            "retry_count": result.get("retry_count", 0),
            "semantic_repair_count": semantic_repairs,
            "decision_dataset_mode": assessment.get("mode", "not_requested"),
            "decision_dataset_adapted": decision_dataset_adapted,
        }],
    }
