from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from agent.state import GlobalState
from agent.nodes.chat_node import chat_node
from agent.nodes.supervisor_node import supervisor_node
from agent.nodes.synthesize_node import synthesize_node
from agent.sql_subgraph import sql_engine_wrapper
from agent.nodes.worker_nodes import chart_worker_node, er_worker_node, process_worker_node, decision_worker_node


def route_after_supervisor(state: GlobalState) -> str:
    """
    Route after supervisor:
      - cached_hit -> synthesize (fast return)
      - intent=chat|contextual -> chat
      - intent=error -> synthesize
      - else -> sql_engine (data required)
    """
    if state.get("cached_hit"):
        return "synthesize"
    
    plan = state.get("supervisor_plan", {})
    intent = plan.get("intent", "query")
    
    if intent in ("chat", "contextual"):
        return "chat"
    if intent == "error":
        return "synthesize"
        
    return "sql_engine"


def dynamic_viz_routing(state: GlobalState):
    """
    Reads the supervisor plan and fans out visualization tasks concurrently using Send API.
    All workers append to state["visualizations"] via operator.add.
    """
    plan = state.get("supervisor_plan", {})
    viz_required = plan.get("visualizations", [])
    
    # If there was a fatal SQL error, skip viz and go to synthesize for fallback summary
    summary = state.get("summary", "")
    if summary and (summary.startswith("MCP execution error") or summary.startswith("SQL generation failed")):
        return "synthesize"
    
    sends = []
    dataset = state.get("clean_dataset", [])
    schemas = state.get("retrieved_schemas", [])
    prompt = state.get("prompt", "")
    
    # Map workers to requested visualizations concurrently
    for viz in viz_required:
        if viz.endswith("_chart") and dataset:
            # strip "_chart" e.g. "bar_chart" -> "bar"
            chart_type = viz.replace("_chart", "")
            sends.append(Send("chart_worker", {"dataset": dataset, "chart_type": chart_type}))
            
        elif viz == "er_diagram" and schemas:
            sends.append(Send("er_worker", {"schema": schemas}))
            
        elif viz == "process_flow" and dataset:
            sends.append(Send("process_worker", {"dataset": dataset, "title": prompt}))
            
        elif viz == "decision_tree" and dataset:
            sends.append(Send("decision_worker", {"dataset": dataset, "title": prompt}))
            
    # If no visuals are needed or possible, skip straight to the final text synthesizer
    if not sends:
        return "synthesize"
        
    return sends


def build_production_graph() -> StateGraph:
    """Construct the Map-Reduce production graph."""
    workflow = StateGraph(GlobalState)

    # 1. Add Core Nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("chat", chat_node)
    workflow.add_node("sql_engine", sql_engine_wrapper)
    workflow.add_node("synthesize", synthesize_node)
    
    # 2. Add Parallel Worker Nodes
    workflow.add_node("chart_worker", chart_worker_node)
    workflow.add_node("er_worker", er_worker_node)
    workflow.add_node("process_worker", process_worker_node)
    workflow.add_node("decision_worker", decision_worker_node)

    workflow.set_entry_point("supervisor")

    # 3. Routing from Supervisor
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        ["chat", "sql_engine", "synthesize"]
    )
    workflow.add_edge("chat", END)

    # 4. Map-Reduce Fan-Out 
    workflow.add_conditional_edges(
        "sql_engine",
        dynamic_viz_routing,
        ["chart_worker", "er_worker", "process_worker", "decision_worker", "synthesize"]
    )
    
    # 5. Fan-In Synchronization
    # All parallel workers flow into synthesize
    workflow.add_edge("chart_worker", "synthesize")
    workflow.add_edge("er_worker", "synthesize")
    workflow.add_edge("process_worker", "synthesize")
    workflow.add_edge("decision_worker", "synthesize")
    
    workflow.add_edge("synthesize", END)

    return workflow


_compiled_graph: CompiledStateGraph | None = None


def get_graph() -> CompiledStateGraph:
    """Return the compiled LangGraph singleton instance."""
    global _compiled_graph
    if _compiled_graph is None:
        workflow = build_production_graph()
        _compiled_graph = workflow.compile()
    return _compiled_graph
