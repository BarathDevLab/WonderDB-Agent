🏛️ Architecture Specification: Enterprise Agentic Text-to-SQL PlatformSystem Overview: An enterprise-grade, multi-tenant Text-to-SQL platform that translates natural language prompts into dialect-specific SQL, validates execution safety via AST parsing and EXPLAIN cost gates, executes queries against isolated read-only replicas, and streams live progress, dataset tables, and declarative visualization specs to the frontend via Server-Sent Events (SSE).1. High-Level System ArchitecturePlaintext+-------------------------------------------------------------------------------------------------------------------+
| 1. PRESENTATION & CLIENT LAYER (React / Flutter)                                                                  |
|    - SSE Event Listener (EventSource) | Data Grids | Chart.js & Vega-Lite Visuals | Mermaid.js Flowcharts       |
+---------------------------------------------------------+---------------------------------------------------------+
                                                          | HTTP/2 Server-Sent Events (SSE)
                                                          | Header: X-Accel-Buffering: no
                                                          v
+-------------------------------------------------------------------------------------------------------------------+
| 2. API GATEWAY, AUTHENTICATION & MULTI-TENANCY INGRESS                                                           |
|    - FastAPI Ingress | JWT Claims Extractor (user_id, role, tenant_id) | Redis Token Bucket Rate Limiter     |
+---------------------------------------------------------+---------------------------------------------------------+
                                                          | Sets SESSION app.current_tenant_id
                                                          v
+-------------------------------------------------------------------------------------------------------------------+
| 3. LANGGRAPH SINGLE-AGENT ORCHESTRATOR (Deterministic State Machine)                                             |
|                                                                                                                   |
|  +-------------------------------------------------------------------------------------------------------------+  |
|  | Semantic Cache Gate (Redis VSS) -- Prompt Embedding Match (Cosine >= 0.96) -> Fast Return (15ms)              |  |
|  +------------------------------------------------------+------------------------------------------------------+  |
|                                                         | Cache Miss                                              |
|                                                         v                                                         |
|  +-------------------------------------------------------------------------------------------------------------+  |
|  | Node 1: Dynamic Schema RAG Node (pgvector)                                                                  |  |
|  |         - Hybrid Search (Dense Cosine + Sparse BM25) + Foreign Key Graph Traversal                          |  |
|  +------------------------------------------------------+------------------------------------------------------+  |
|                                                         |                                                         |
|                                                         v                                                         |
|  +-------------------------------------------------------------------------------------------------------------+  |
|  | Node 2: LLM Generation Node (Single-Agent Prompt | Temp: 0.0)                                                    |  |
|  |         - Emits SQL string + Chart.js configuration in structured JSON payload                             |  |
|  +------------------------------------------------------+------------------------------------------------------+  |
|                                                         |                                                         |
|                                                         v                                                         |
|  +-------------------------------------------------------------------------------------------------------------+  |
|  | Node 3: Reflection & Self-Correction Node                                                                  |  |
|  |         - Intercepts AST/DB exceptions; re-prompts LLM with error context (Max 3 Retries)                    |  |
|  +-------------------------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------+---------------------------------------------------------+
                                                          |
                                                          v
+-------------------------------------------------------------------------------------------------------------------+
| 4. SECURITY, AST & EXECUTION GATEWAY                                                                              |
|    - SQL AST Validator (sqlglot): Enforces strict SELECT root; blocks DML, COPY TO, dblink, multi-statements      |
|    - Query Cost Evaluator: Runs EXPLAIN (FORMAT JSON); rejects Cost > 10,000 & unindexed Seq Scans              |
|    - Schema-Driven PII Masking: Field-level masking based on catalog metadata flags                              |
+---------------------------------------------------------+---------------------------------------------------------+
                                                          |
                   +--------------------------------------+--------------------------------------+
                   | Async Path (Query Cost > 10,000)                                            | Sync Execution Path
                   v                                                                             v
+--------------------------------------------------+                         +--------------------------------------+
| ASYNCHRONOUS WORKER QUEUE                        |                         | DATABASE EXECUTION SANDBOX           |
| - BullMQ / Celery Background Queue               |                         | - PgBouncer Connection Pooler        |
| - Offloads heavy aggregate queries               |                         | - Read-Only Database Replica         |
| - Stream progress via Redis PubSub to Client     |                         | - Role: agent_read_only_runner       |
+------------------------+-------------------------+                         | - Limits: statement_timeout = 10s    |
                         |                                                   |           work_mem = 64MB            |
                         +--------------------------------+                  +-------------------+------------------+
                                                          |                                      |
                                                          v                                      v
+-------------------------------------------------------------------------------------------------------------------+
| 5. PERSISTENCE LAYER (PostgreSQL & Redis Engine)                                                                  |
|    - PostgreSQL Operational DB: Multi-Tenant Isolation via Row-Level Security (RLS) Policies                    |
|    - Redis Engine: Hot Active Session Buffers (24h TTL), Semantic Vector Caching & PubSub Streaming               |
+-------------------------------------------------------------------------------------------------------------------+
2. Shared Execution State (AgentState)The state dictionary is the core data contract passed between LangGraph nodes during execution.Pythonfrom typing import TypedDict, List, Dict, Any, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # Ingress Parameters
    prompt: str                         # Natural language question from user
    tenant_id: str                      # Current active tenant UUID
    user_id: str                        # Authenticated user ID

    # Planning & Schema RAG Phase
    plan_strategy: str                  # High-level join strategy derived from RAG
    retrieved_schemas: List[Dict[str, Any]] # Schema DDLs retrieved from pgvector
    sql_query: str                      # Candidate SQL generated by LLM

    # Execution & Validation Phase
    raw_results: List[Dict[str, Any]]   # Query execution result set from PostgreSQL
    explain_cost: float                 # Estimated total cost from EXPLAIN engine
    ast_valid: bool                     # AST compliance flag from sqlglot

    # Visualization & Formatting Phase
    summary: str                        # Synthesized text answer
    chart_spec: Dict[str, Any]          # Declarative Chart.js / Vega configuration

    # Reflection & Resilience
    error_message: str                  # DB or AST exception error trace
    retry_count: int                    # Self-correction loop counter (Max: 3)
    current_phase: str                  # Execution milestone tracking
3. LangGraph Node Lifecycle & Data FlowNode 1: plan_node (Schema RAG + SQL Generation)Inputs: state["prompt"], state["tenant_id"], state["retry_count"]Actions:Queries schema_embeddings via pgvector hybrid search (Dense Cosine + Sparse BM25) filtered by tenant_id.Traverses foreign keys to attach connected lookup schemas.Formulates a single structured prompt to the LLM (Temperature: 0.0).If retry_count > 0, injects state["error_message"] into context to trigger self-correction.Outputs: plan_strategy, sql_query, current_phase="planning_complete"Node 2: execute_node (AST Validation + EXPLAIN Gate + DB Execution)Inputs: state["sql_query"], state["tenant_id"]Actions:AST Check (sqlglot): Validates root statement is exp.Select. Rejects multi-statement commands, DML (DROP, DELETE, UPDATE), and administrative functions (COPY TO, dblink).Cost Gate: Runs EXPLAIN (FORMAT JSON) on a read-only replica. Rejects queries with Total Cost > 10,000 or full table scans on large tables.DB Execution: Executes query via asyncpg within tenant session context (SET LOCAL app.current_tenant_id = '...').PII Masking: Redacts fields flagged is_pii = true in catalog metadata.Outputs: raw_results, explain_cost, current_phase="execution_complete" (OR error_message, retry_count += 1 on failure).Node 3: summarize_node (Data Synthesis & Chart Spec Generation)Inputs: state["raw_results"], state["prompt"]Actions:Formulates a concise textual synthesis of the result set.Constructs declarative, front-end-ready JSON specs for Chart.js / Vega-Lite.Outputs: summary, chart_spec, current_phase="summarize_complete"4. Real-Time Streaming Protocol (SSE)The application communicates with the client via a single, long-lived HTTP/2 Server-Sent Events stream (GET /api/v1/agent/stream).Event Wire SpecificationsEvent NameTrigger PhasePayload StructureFrontend ActionstatusPhase Transitions{"phase": "planning", "message": "Retrieving schema..."}Updates live spinner / thought animationplan_readyPost plan_node{"strategy": "...", "sql": "SELECT..."}Renders code syntax block & strategy badgereflection_retryException in execute_node{"error": "Column X missing", "retry": 1}Displays self-correction indicatorexecution_completePost execute_node{"rows": 5, "data": [...]}Renders paginated interactive data gridfinal_responsePost summarize_node{"summary": "...", "chart_spec": {...}}Renders text summary & Chart.js component5. Security & Isolation MatrixLayerSecurity MechanismEnforcement PointMulti-TenancyPostgreSQL Row-Level Security (RLS)Database session scope (app.current_tenant_id)Query ParsingAST Static Analysis (sqlglot)execute_node prior to database driver executionResource ProtectionEXPLAIN (FORMAT JSON) Cost EvaluationCost limits ($> 10,000$ units rejected or offloaded)DB Role LimitsLow-privilege agent_read_only_runnerstatement_timeout = 10s, work_mem = 64MBData PrivacySchema-Driven Column RedactionPost-execution filter matching is_pii catalog flagsProxy BufferingUnbuffered Headers (X-Accel-Buffering: no)API Gateway & FastAPI StreamingResponse6. Development & Coding ConventionsAsync-First: Every database query, network call, and LLM invocation MUST use async/await. Synchronous blocking calls are forbidden in the application thread.Deterministic State Graphs: No loose agent loops. Graph transitions MUST execute through defined, type-checked LangGraph state nodes.Pydantic v2 Standardization: All data transfer objects (DTOs), API parameters, and environment settings MUST use Pydantic v2 validation models.Resilient SSE Connection: The API must explicitly handle client disconnects during graph.astream() to avoid orphan database connections or wasted API tokens.