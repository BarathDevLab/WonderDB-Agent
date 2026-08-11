import operator
from typing import Annotated, Any, TypedDict


class GlobalState(TypedDict, total=False):
    """Global execution state for the orchestration layer."""
    prompt: str
    tenant_id: str
    session_id: str
    user_id: str
    
    # Set by supervisor_node
    supervisor_plan: dict[str, Any]
    retrieved_schemas: list[dict[str, Any]]
    enable_cache: bool
    cached_hit: bool
    
    # Data from SQL Subgraph
    clean_dataset: list[dict[str, Any]]
    sql_query: str  # Kept for caching/history
    
    # Parallel visualizations map-reduce (chart, er, etc.)
    visualizations: Annotated[list[dict[str, Any]], operator.add]
    
    # Output and tracking
    summary: str
    current_phase: str
    tool_calls: Annotated[list[dict[str, Any]], operator.add]


class SQLSubgraphState(TypedDict, total=False):
    """Private execution state for the SQL execution subgraph."""
    tenant_id: str
    prompt: str
    error_message: str # To pass previous errors to SQL Gen
    prisma_context: str
    generated_sql: str
    dataset: list[dict[str, Any]]
    db_error: str
    retry_count: int
    explain_cost: float
    tool_calls: Annotated[list[dict[str, Any]], operator.add]
