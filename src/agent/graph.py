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
    Routing decision immediately after the supervisor node:

      cached_hit          → synthesize  (fast-path: skip all work)
      intent = chat       → chat
      intent = contextual → chat
      intent = schema     → sql_engine  (schema-only: sql_gen skipped by prompt; workers do ER diagram)
      intent = error      → synthesize  (supervisor itself failed to plan; surface error)
      intent = query      → sql_engine  (normal data path)
      default             → sql_engine  (safe fallback)
    """
    if state.get("cached_hit"):
        return "synthesize"

    plan = state.get("supervisor_plan", {})
    intent = plan.get("intent", "query")

    if intent in ("chat", "contextual"):
        return "chat"
    if intent == "error":
        return "synthesize"

    # "query" and "schema" both use sql_engine;
    # for "schema" the supervisor sets only er_diagram in visualizations
    # so sql_gen receives no data request and workers handle diagrams only.
    return "sql_engine"


def dynamic_viz_routing(state: GlobalState):
    """
    Fan-out visualization tasks after sql_engine completes.
    Reads supervisor_plan.visualizations and dispatches parallel Send() calls.

    Changed from string-prefix error detection to has_fatal_error sentinel.
    Falls through to synthesize when:
      - A fatal SQL error occurred (has_fatal_error)
      - No visualization was requested or data is unavailable
    """
    # Use the structured sentinel — no more fragile string prefix matching
    if state.get("has_fatal_error"):
        return "synthesize"

    plan = state.get("supervisor_plan", {})
    viz_required = plan.get("visualizations", [])

    if not viz_required:
        return "synthesize"

    sends = []
    dataset = state.get("clean_dataset", [])
    schemas = state.get("retrieved_schemas", [])
    prompt = state.get("prompt", "")

    for viz in viz_required:
        if viz.endswith("_chart") and dataset:
            chart_type = viz.replace("_chart", "")
            sends.append(Send("chart_worker", {"dataset": dataset, "chart_type": chart_type}))

        elif viz == "er_diagram" and schemas:
            sends.append(Send("er_worker", {"schema": schemas}))

        elif viz == "process_flow" and dataset:
            sends.append(Send("process_worker", {"dataset": dataset, "title": prompt}))

        elif viz == "decision_tree" and dataset:
            sends.append(Send("decision_worker", {"dataset": dataset, "title": prompt}))

    # No qualifying sends (e.g. schema viz requested but no schema retrieved)
    if not sends:
        return "synthesize"

    return sends


def build_production_graph() -> StateGraph:
    """Construct the Map-Reduce production graph."""
    workflow = StateGraph(GlobalState)

    # 1. Core nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("chat", chat_node)
    workflow.add_node("sql_engine", sql_engine_wrapper)
    workflow.add_node("synthesize", synthesize_node)

    # 2. Parallel visualization worker nodes
    workflow.add_node("chart_worker", chart_worker_node)
    workflow.add_node("er_worker", er_worker_node)
    workflow.add_node("process_worker", process_worker_node)
    workflow.add_node("decision_worker", decision_worker_node)

    workflow.set_entry_point("supervisor")

    # 3. Supervisor routing
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        ["chat", "sql_engine", "synthesize"],
    )
    workflow.add_edge("chat", END)

    # 4. Map-Reduce fan-out from sql_engine
    workflow.add_conditional_edges(
        "sql_engine",
        dynamic_viz_routing,
        ["chart_worker", "er_worker", "process_worker", "decision_worker", "synthesize"],
    )

    # 5. Fan-in: all parallel workers converge on synthesize
    workflow.add_edge("chart_worker", "synthesize")
    workflow.add_edge("er_worker", "synthesize")
    workflow.add_edge("process_worker", "synthesize")
    workflow.add_edge("decision_worker", "synthesize")

    workflow.add_edge("synthesize", END)

    return workflow


_compiled_graph: CompiledStateGraph | None = None


def get_graph() -> CompiledStateGraph:
    """Return the compiled LangGraph singleton (lazy init, compiled once)."""
    global _compiled_graph
    if _compiled_graph is None:
        workflow = build_production_graph()
        _compiled_graph = workflow.compile()
    return _compiled_graph
