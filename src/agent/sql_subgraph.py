"""
sql_subgraph.py
===============
Isolated subgraph for executing SQL. Handles SQL generation, execution, and 
reflexive error handling (up to 3 retries) independently of the main graph.
"""
from langgraph.graph import StateGraph, START, END

from agent.state import SQLSubgraphState, GlobalState
from agent.nodes.sql_gen_node import sql_gen_node
from agent.nodes.execute_node import execute_node
from agent.nodes.reflect_node import reflect_node

def build_sql_subgraph():
    sg = StateGraph(SQLSubgraphState)
    
    sg.add_node("sql_gen", sql_gen_node)
    sg.add_node("execute_db", execute_node)
    sg.add_node("reflect", reflect_node)
    
    sg.add_edge(START, "sql_gen")
    sg.add_edge("sql_gen", "execute_db")
    
    def check_db_error(state: SQLSubgraphState) -> str:
        if state.get("db_error") and state.get("retry_count", 0) < 3:
            return "reflect"
        return END
        
    sg.add_conditional_edges("execute_db", check_db_error)
    sg.add_edge("reflect", "sql_gen")
    
    return sg.compile()

compiled_sql_subgraph = build_sql_subgraph()

async def sql_engine_wrapper(state: GlobalState) -> dict:
    """Invoked as a node in the main graph. Translates state and hides subgraph messiness."""
    # 1. Translate parent state -> subgraph state
    sub_state: SQLSubgraphState = {
        "tenant_id": state.get("tenant_id", "default-tenant"),
        "prompt": state.get("prompt", ""),
        "prisma_context": state.get("retrieved_schemas", []),
        "retry_count": 0,
        "error_message": "",
        "tool_calls": [],
    }
    
    # 2. Run the isolated loop
    result = await compiled_sql_subgraph.ainvoke(sub_state)
    
    # 3. Map only the clean data and necessary tracking info back to the parent GlobalState
    return {
        "clean_dataset": result.get("dataset", []),
        "sql_query": result.get("generated_sql", ""), # Useful for explain context and caching
        "tool_calls": result.get("tool_calls", []),
        "summary": result.get("db_error", "") if result.get("db_error") else "", # Pass severe error to fallback
        "current_phase": "sql_engine_complete",
    }
