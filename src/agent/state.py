from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Execution state passed between LangGraph nodes during Text-to-SQL workflows."""

    # Ingress Parameters
    prompt: str
    tenant_id: str
    user_id: str
    session_id: str

    # Semantic Cache & Planning Phase
    cached_hit: bool
    plan_strategy: str
    retrieved_schemas: list[dict[str, Any]]
    sql_query: str

    # Execution & Validation Phase
    raw_results: list[dict[str, Any]]
    explain_cost: float
    ast_valid: bool

    # Visualization & Formatting Phase
    summary: str
    chart_spec: dict[str, Any]

    # Reflection & Resilience
    error_message: str
    retry_count: int
    current_phase: str
