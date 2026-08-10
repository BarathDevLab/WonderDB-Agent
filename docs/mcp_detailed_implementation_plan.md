# Detailed MCP Implementation Plan

This document outlines the exact, file-by-file changes required to transition the AI Database Agent to a "Brain vs. Hands" architecture using the Model Context Protocol (MCP).

## User Review Required

> [!WARNING]  
> This migration introduces a major new dependency (`mcp`) and restructures the application's core execution flow. Please review the detailed file changes below. If approved, I will begin execution immediately.

## Phase 1: Build the MCP Server

We will create a standalone MCP server that encapsulates all database and execution logic.

### 1. Create `src/mcp_server/server.py`
This new file will define the MCP server and expose our three core tools.

```python
import asyncio
from mcp.server.fastmcp import FastMCP
from typing import Any

# Initialize FastMCP Server
mcp = FastMCP("AIDatabaseAgent")

@mcp.tool()
async def get_database_schema(prompt: str, tenant_id: str) -> list[dict[str, Any]]:
    """Retrieve relevant database schemas via vector search."""
    from services.schema_rag import retrieve_schema_context
    from db.postgres import get_shared_pool
    pool = await get_shared_pool()
    return await retrieve_schema_context(prompt, tenant_id, pool)

@mcp.tool()
async def execute_sql_query(sql: str, tenant_id: str) -> dict[str, Any]:
    """Execute a read-only SQL query safely with RLS and cost gating."""
    from agent.nodes.execute_node import _execute_against_live_postgres, _enforce_limit
    from core.pii_redactor import redact_rows
    from core.ast_validator import validate_sql
    
    # 1. AST Validation
    validate_sql(sql)
    # 2. Limit Enforcement
    sql = _enforce_limit(sql, max_rows=100)
    # 3. Execution
    raw_data, estimated_cost = await _execute_against_live_postgres(sql, tenant_id)
    # 4. Redaction
    redacted_data = redact_rows(raw_data)
    
    return {
        "raw_results": redacted_data,
        "explain_cost": estimated_cost
    }

@mcp.tool()
async def generate_chart_spec(raw_data: list[dict[str, Any]], chart_type: str = "bar") -> dict[str, Any]:
    """Generate a Chart.js specification from raw data."""
    from utils.chart_generator import generate_chart_spec as internal_generate
    return internal_generate(raw_data, chart_type)

if __name__ == "__main__":
    mcp.run()
```

## Phase 2: Refactor Nodes to act as MCP Clients

We will update the LangGraph nodes to connect to the MCP server instead of running the logic locally. 

### 1. Create `src/agent/mcp_client.py`
To manage the MCP connection within our FastAPI app, we will create a client manager.
* It will use `mcp.client.stdio.stdio_client` to spawn the `mcp_server/server.py` process.
* It will expose a `get_mcp_session()` function for the nodes to use.

### 2. Update `src/agent/nodes/plan_node.py`
#### [MODIFY] `plan_node.py`
Instead of calling `retrieve_schema_context` directly, it will call the MCP tool.
```python
# Old
retrieved_schemas = await retrieve_schema_context(prompt, tenant_id, pool)

# New
session = await get_mcp_session()
result = await session.call_tool("get_database_schema", arguments={"prompt": prompt, "tenant_id": tenant_id})
retrieved_schemas = result.content[0].text # (Parsed from JSON)
```

### 3. Update `src/agent/nodes/execute_node.py`
#### [MODIFY] `execute_node.py`
We will gut the internal validation and execution logic, moving it to the MCP server. The node will simply call the tool.
```python
# Inside execute_node(state)
session = await get_mcp_session()
try:
    result = await session.call_tool("execute_sql_query", arguments={"sql": sql, "tenant_id": tenant_id})
    # Parse result and update state
except Exception as exc:
    # Handle error and trigger reflection
```

### 4. Update `src/agent/nodes/summarize_node.py`
#### [MODIFY] `summarize_node.py`
Instead of calling `generate_chart_spec` directly, it will call the MCP tool.

## Phase 3: Dependency Updates

### 1. Update `pyproject.toml` or `requirements.txt`
We will need to install the official MCP python SDK.
- Run: `pip install mcp` (or equivalent package manager command).

## Verification Plan

1. **Start the FastAPI Server**: Ensure the MCP Client successfully spawns the MCP Server in the background via `stdio` upon startup.
2. **Execute a Query**: Run a standard natural language query through the API.
3. **Verify Separation**: Check the logs to confirm that database queries are being executed by the `FastMCP` server process, while the orchestration (Planning, Reflecting) remains in the main FastAPI process.
