from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.nodes.chat_node import chat_node
from agent.nodes.execute_node import execute_node
from agent.nodes.plan_node import plan_node
from agent.nodes.reflect_node import reflect_node
from agent.nodes.summarize_node import summarize_node
from agent.state import AgentState


def route_after_plan(state: AgentState) -> str:
    """
    4-branch routing after plan_node:
      - cached_hit          → summarize (fast return)
      - intent=chat|contextual → chat (conversational response)
      - planning_failed     → summarize (error path)
      - needs_sql=true      → execute (DB query needed)
      - else                → summarize (schema/ER only)
    """
    if state.get("cached_hit"):
        return "summarize"
    intent = state.get("intent", "query")
    if intent in ("chat", "contextual"):
        return "chat"
    if state.get("current_phase") == "planning_failed":
        return "summarize"
    if state.get("needs_sql"):
        return "execute"
    return "summarize"


def should_reflect(state: AgentState) -> str:
    """After execute: reflect on errors (up to 3 retries) or proceed to summarize."""
    error_message = state.get("error_message")
    retry_count = state.get("retry_count", 0)
    if error_message and retry_count < 3:
        return "reflect"
    return "summarize"


def build_graph() -> StateGraph:
    """Construct intent-aware StateGraph with chat, schema, query, and reflection paths."""
    workflow = StateGraph(AgentState)

    # Register all nodes
    workflow.add_node("plan", plan_node)
    workflow.add_node("chat", chat_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("reflect", reflect_node)
    workflow.add_node("summarize", summarize_node)

    # Entry point
    workflow.set_entry_point("plan")

    # plan → 4 branches
    workflow.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "chat": "chat",
            "execute": "execute",
            "summarize": "summarize",
        },
    )

    # chat → END (no further processing)
    workflow.add_edge("chat", END)

    # execute → reflect or summarize
    workflow.add_conditional_edges(
        "execute",
        should_reflect,
        {"reflect": "reflect", "summarize": "summarize"},
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
