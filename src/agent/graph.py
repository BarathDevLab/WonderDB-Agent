from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.nodes.execute_node import execute_node
from agent.nodes.plan_node import plan_node
from agent.nodes.reflect_node import reflect_node
from agent.nodes.summarize_node import summarize_node
from agent.state import AgentState


def should_plan_route(state: AgentState) -> str:
    """Conditional routing edge for fast-return semantic cache hits or planning failure."""
    if state.get("cached_hit") or state.get("current_phase") == "planning_failed":
        return "summarize"
    return "execute"


def should_reflect(state: AgentState) -> str:
    """Conditional routing edge deciding whether to reflect & retry or summarize."""
    error_message = state.get("error_message")
    retry_count = state.get("retry_count", 0)

    if error_message and retry_count < 3:
        return "reflect"
    return "summarize"


def build_graph() -> StateGraph:
    """Construct deterministic StateGraph with fast semantic cache gate and reflection loop."""
    workflow = StateGraph(AgentState)

    # 1. Register lifecycle nodes
    workflow.add_node("plan", plan_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("reflect", reflect_node)
    workflow.add_node("summarize", summarize_node)

    # 2. Wire static and conditional transitions
    workflow.set_entry_point("plan")

    workflow.add_conditional_edges(
        "plan",
        should_plan_route,
        {
            "execute": "execute",
            "summarize": "summarize",
        },
    )

    workflow.add_conditional_edges(
        "execute",
        should_reflect,
        {
            "reflect": "reflect",
            "summarize": "summarize",
        },
    )

    workflow.add_edge("reflect", "plan")
    workflow.add_edge("summarize", END)

    return workflow


_compiled_graph: CompiledStateGraph | None = None


def get_graph() -> CompiledStateGraph:
    """Return the compiled LangGraph singleton instance."""
    global _compiled_graph
    if _compiled_graph is None:
        workflow = build_graph()
        _compiled_graph = workflow.compile()
    return _compiled_graph
