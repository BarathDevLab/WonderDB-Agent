from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Execution state passed between LangGraph nodes during AI Database Agent workflows."""

    # ── Ingress ───────────────────────────────────────────────────────────
    prompt: str
    tenant_id: str
    user_id: str
    session_id: str

    # ── Intent (set by plan_node, drives all downstream routing) ─────────
    intent: str               # "query" | "schema" | "chat" | "contextual"
    needs_sql: bool           # True → execute_node runs SQL via MCP
    needs_chart: bool         # True → summarize_node calls generate_chart tool
    chart_type: str           # "auto" | "bar" | "line" | "pie" | "scatter"
    needs_er_diagram: bool    # True → summarize_node calls generate_flowchart(er)
    needs_process_flow: bool  # True → summarize_node calls generate_flowchart(process)
    needs_explanation: bool   # True → summarize_node / chat_node calls explain_data

    # ── Semantic Cache & Planning ─────────────────────────────────────────
    cached_hit: bool
    enable_cache: bool
    plan_strategy: str
    retrieved_schemas: list[dict[str, Any]]
    sql_query: str

    # ── Execution ─────────────────────────────────────────────────────────
    raw_results: list[dict[str, Any]]
    explain_cost: float
    ast_valid: bool

    # ── Output ────────────────────────────────────────────────────────────
    summary: str
    chart_spec: dict[str, Any]
    diagram_spec: dict[str, Any]   # {"mermaid": "...", "diagram_type": "er|process|decision"}
    tool_calls: list[dict]         # MCP tool call log [{"tool": str, "status": str, "duration_ms": float}]

    # ── Reflection & Resilience ───────────────────────────────────────────
    error_message: str
    retry_count: int
    current_phase: str
