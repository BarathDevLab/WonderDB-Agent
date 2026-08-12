import operator
from typing import Annotated, Any, TypedDict


class GlobalState(TypedDict, total=False):
    """
    Global execution state for the LangGraph orchestration layer.

    Lifecycle:
      supervisor → (chat | sql_engine | synthesize)
      sql_engine → (chart_worker | er_worker | process_worker | decision_worker) → synthesize
      synthesize → END
    """
    # ── Input fields (set by caller) ──────────────────────────────────────
    prompt: str
    tenant_id: str
    session_id: str
    user_id: str
    resolved_prompt: str
    cache_prompt: str
    conversation_context: dict[str, Any]

    # ── Set by supervisor_node ────────────────────────────────────────────
    supervisor_plan: dict[str, Any]
    retrieved_schemas: list[dict[str, Any]]
    enable_cache: bool
    cached_hit: bool

    # ── Set by sql_engine wrapper ─────────────────────────────────────────
    clean_dataset: list[dict[str, Any]]
    sql_query: str          # Kept for caching / history / explain context
    data_analysis: dict[str, Any]  # Deterministic metrics produced by analyze_data
    response_verification: dict[str, Any]  # Final requested-vs-delivered artifact check

    # ── Error sentinel (replaces fragile string-prefix matching) ─────────
    has_fatal_error: bool   # True when sql_engine encountered unrecoverable failure
    error_detail: str       # Human-readable error forwarded to synthesize fallback

    # ── Parallel visualizations (map-reduce fan-out/fan-in) ───────────────
    # operator.add means each parallel worker *appends* its list to the shared one
    visualizations: Annotated[list[dict[str, Any]], operator.add]

    # ── Output & telemetry ───────────────────────────────────────────────
    summary: str
    current_phase: str
    tool_calls: Annotated[list[dict[str, Any]], operator.add]


class SQLSubgraphState(TypedDict, total=False):
    """
    Private execution state for the SQL execution subgraph.
    Isolated from GlobalState — bridged only through sql_engine_wrapper.
    """
    tenant_id: str
    prompt: str
    resolved_prompt: str
    error_message: str      # Passed to SQL gen on retry so it can self-correct
    prisma_context: str     # Formatted DDL from retrieved_schemas
    generated_sql: str
    dataset: list[dict[str, Any]]
    db_error: str           # Set by execute_node on failure; cleared on success
    retry_count: int
    explain_cost: float
    tool_calls: Annotated[list[dict[str, Any]], operator.add]
