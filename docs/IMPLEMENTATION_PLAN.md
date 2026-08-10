# Phased Implementation Plan

## Phase 1: Environment & Core Configuration
- [x] Initialize `pyproject.toml` with FastAPI, LangGraph, asyncpg, sqlglot, and Pydantic v2.
- [x] Create `src/app/config.py` with environment variable loader (`BaseSettings`).
- [x] Create `src/db/postgres.py` with `asyncpg` connection pool setup and teardown lifespan.

## Phase 2: Security & RAG Services
- [x] Implement `src/services/ast_service.py` using `sqlglot` to enforce strict SELECT statements.
- [x] Implement `src/services/schema_rag.py` for retrieving schema DDLs from `pgvector` / foreign-key graph.
- [x] Create `src/db/init_rls.sql` script setting up RLS policies on PostgreSQL tables.
- [x] Implement `src/core/cost_evaluator.py` and `src/core/pii_redactor.py`.

## Phase 3: LangGraph State Machine
- [x] Define `AgentState` TypedDict in `src/agent/state.py`.
- [x] Create nodes (`plan_node`, `execute_node`, `reflect_node`, `summarize_node`) in `src/agent/nodes/`.
- [x] Wire StateGraph, reflection conditional edges, and compile graph in `src/agent/graph.py`.

## Phase 4: SSE Transport & API Router
- [x] Build `run_langgraph_sse` generator in `src/agent/sse.py` consuming `graph.astream()`.
- [x] Create FastAPI endpoints `GET /api/v1/agent/stream` and `POST /api/v1/agent/stream` in `src/app/api/v1/chat.py` returning `StreamingResponse`.
- [x] Add `X-Accel-Buffering: no` headers to prevent reverse proxy buffering.

## Phase 5: Verification & Testing
- [x] Write unit tests for `ASTService` verifying DML statement rejection.
- [x] Write unit tests for `evaluate_cost`, `redact_rows`, and `LangGraph` state machine.
- [x] Run integration test streaming SSE events from `/api/v1/agent/stream` and `/api/v1/health`.