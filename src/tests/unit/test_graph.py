"""
test_graph.py
=============
Integration-style tests for the LangGraph compilation and graph structure.
These tests verify the graph compiles and routes correctly — they do NOT
require a live database or Gemini API (nodes are not invoked here).

Bug fixes applied:
  - AgentState → GlobalState (AgentState never existed in the codebase)
  - Removed retry_count from GlobalState init (belongs to SQLSubgraphState)
  - Removed stale field assertions (ast_valid, raw_results, chart_spec, plan_strategy)
    that referenced old pre-refactor state schema
"""
from agent.graph import get_graph, route_after_supervisor, dynamic_viz_routing
from agent.nodes.chat_node import _looks_like_identity_question
from agent.state import GlobalState

SAMPLE_TENANT_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


def test_langgraph_compiles() -> None:
    """Graph should compile without errors."""
    graph = get_graph()
    assert graph is not None


def test_identity_questions_are_detected() -> None:
    assert _looks_like_identity_question("who are you")
    assert _looks_like_identity_question("who developed you")
    assert _looks_like_identity_question("who is your owner")
    assert _looks_like_identity_question("who owns WonderDB Agent")
    assert not _looks_like_identity_question("what is the average order value")


def test_route_after_supervisor_cached_hit() -> None:
    """cached_hit should always route to synthesize."""
    state: GlobalState = {
        "cached_hit": True,
        "supervisor_plan": {"intent": "query", "visualizations": [], "needs_explanation": False},
    }
    assert route_after_supervisor(state) == "synthesize"


def test_route_after_supervisor_chat() -> None:
    state: GlobalState = {
        "cached_hit": False,
        "supervisor_plan": {"intent": "chat", "visualizations": [], "needs_explanation": False},
    }
    assert route_after_supervisor(state) == "chat"


def test_route_after_supervisor_contextual() -> None:
    state: GlobalState = {
        "cached_hit": False,
        "supervisor_plan": {"intent": "contextual", "visualizations": [], "needs_explanation": True},
    }
    assert route_after_supervisor(state) == "chat"


def test_route_after_supervisor_query() -> None:
    state: GlobalState = {
        "cached_hit": False,
        "supervisor_plan": {"intent": "query", "visualizations": ["bar_chart"], "needs_explanation": True},
    }
    assert route_after_supervisor(state) == "sql_engine"


def test_route_after_supervisor_schema() -> None:
    state: GlobalState = {
        "cached_hit": False,
        "supervisor_plan": {"intent": "schema", "visualizations": ["er_diagram"], "needs_explanation": True},
    }
    assert route_after_supervisor(state) == "sql_engine"


def test_route_after_supervisor_error() -> None:
    state: GlobalState = {
        "cached_hit": False,
        "supervisor_plan": {"intent": "error", "visualizations": [], "needs_explanation": False},
    }
    assert route_after_supervisor(state) == "synthesize"


def test_dynamic_viz_routing_fatal_error() -> None:
    """A fatal query error with only data-backed output goes to synthesize."""
    state: GlobalState = {
        "has_fatal_error": True,
        "supervisor_plan": {"intent": "query", "visualizations": ["bar_chart"], "needs_explanation": True},
        "clean_dataset": [{"revenue": 100}],
    }
    result = dynamic_viz_routing(state)
    assert result == "synthesize"


def test_fatal_query_error_still_dispatches_independent_schema_diagrams() -> None:
    schema = [{
        "table_name": "orders",
        "columns": [],
        "foreign_keys": [{
            "column": "customer_id",
            "foreign_table": "customers",
            "foreign_column": "customer_id",
        }],
    }]
    state: GlobalState = {
        "has_fatal_error": True,
        "supervisor_plan": {
            "intent": "query",
            "visualizations": ["line_chart", "er_diagram", "process_flow"],
            "needs_explanation": True,
        },
        "clean_dataset": [],
        "retrieved_schemas": schema,
        "prompt": "Show revenue plus the ER diagram and schema flow",
    }

    result = dynamic_viz_routing(state)

    assert isinstance(result, list)
    assert [send.node for send in result] == ["er_worker", "process_worker"]


def test_dynamic_viz_routing_no_viz() -> None:
    """Empty visualizations list should go directly to synthesize."""
    state: GlobalState = {
        "has_fatal_error": False,
        "supervisor_plan": {"intent": "query", "visualizations": [], "needs_explanation": True},
        "clean_dataset": [{"revenue": 100}],
    }
    result = dynamic_viz_routing(state)
    assert result == "synthesize"


def test_dynamic_viz_routing_sends_chart() -> None:
    """bar_chart with data should produce a Send to chart_worker."""
    from langgraph.types import Send
    state: GlobalState = {
        "has_fatal_error": False,
        "supervisor_plan": {"intent": "query", "visualizations": ["bar_chart"], "needs_explanation": True},
        "clean_dataset": [{"month": "Jan", "revenue": 1000}],
        "retrieved_schemas": [],
        "prompt": "Show monthly revenue",
    }
    result = dynamic_viz_routing(state)
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], Send)
    assert result[0].node == "chart_worker"


def test_dynamic_viz_routing_dispatches_every_requested_visualization() -> None:
    state: GlobalState = {
        "has_fatal_error": False,
        "supervisor_plan": {
            "intent": "query",
            "visualizations": ["line_chart", "bar_chart", "pie_chart", "er_diagram"],
            "needs_explanation": True,
        },
        "clean_dataset": [{"month": "Jan", "product": "Keyboard", "revenue": 100}],
        "retrieved_schemas": [],
        "prompt": "Create three charts and an ER diagram",
    }

    result = dynamic_viz_routing(state)

    assert isinstance(result, list)
    assert [send.node for send in result] == [
        "chart_worker", "chart_worker", "chart_worker", "er_worker",
    ]


def test_process_flow_receives_schema_even_without_query_rows() -> None:
    schema = [{
        "table_name": "orders",
        "columns": [],
        "foreign_keys": [{
            "column": "customer_id",
            "foreign_table": "customers",
            "foreign_column": "customer_id",
        }],
    }]
    state: GlobalState = {
        "has_fatal_error": False,
        "supervisor_plan": {
            "intent": "schema",
            "visualizations": ["process_flow"],
            "needs_explanation": False,
        },
        "clean_dataset": [],
        "retrieved_schemas": schema,
        "prompt": "Show the schema flow",
    }

    result = dynamic_viz_routing(state)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].node == "process_worker"
    assert result[0].arg["schema"] == schema


def test_schema_workers_dispatch_even_when_rag_returns_empty() -> None:
    state: GlobalState = {
        "has_fatal_error": False,
        "supervisor_plan": {
            "intent": "schema",
            "visualizations": ["er_diagram", "process_flow"],
            "needs_explanation": True,
        },
        "clean_dataset": [],
        "retrieved_schemas": [],
        "prompt": "Show the schema and process flow",
    }

    result = dynamic_viz_routing(state)

    assert isinstance(result, list)
    assert [send.node for send in result] == ["er_worker", "process_worker"]
