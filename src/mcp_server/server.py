"""
MCP Server — AI Database Agent Tools
=====================================
Exposes 5 tools via FastMCP (stdio transport):
  1. get_schema       — fetch raw DB schema from information_schema
  2. execute_query    — validate + execute SQL with RLS, cost gate, PII redact
  3. generate_chart   — build Chart.js spec (bar/line/pie/scatter)
  4. generate_flowchart — build Mermaid diagram (er/process/decision)
  5. explain_data     — Gemini LLM plain-language summary
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

# Ensure src/ is on the path so we can import agent modules
_src_root = str(Path(__file__).resolve().parent.parent)
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

import uuid as _uuid
import httpx
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    try:
        from fastmcp import FastMCP
    except ImportError:
        from mcp.server import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("AIDatabaseAgent")

# ---------------------------------------------------------------------------
# In-memory schema catalog (populated by get_schema at startup)
# ---------------------------------------------------------------------------
_schema_catalog: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUERY_TIMEOUT_SECONDS = 15.0
_MAX_RESULT_ROWS = 200
_PII_COLUMN_NAMES: frozenset[str] = frozenset(
    {"email", "ssn", "social_security", "password", "phone",
     "credit_card", "tax_id", "salary"}
)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert non-JSON-serializable DB types to JSON-safe equivalents."""
    result: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            result[k] = float(v)
        elif isinstance(v, (datetime, date, UUID)):
            result[k] = str(v)
        else:
            result[k] = v
    return result


def _format_uuid(tenant_id: str) -> str:
    """Ensure tenant_id is a valid UUID string."""
    try:
        return str(_uuid.UUID(tenant_id))
    except (ValueError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# Tool 1: get_schema
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_schema() -> str:
    """
    Fetch all table definitions, columns, PKs, and FKs from information_schema.
    Used at startup to seed the agent's pgvector index.
    Returns JSON-encoded list of table dicts.
    """
    global _schema_catalog
    from db.postgres import get_shared_pool

    _EXCLUDED_TABLES = frozenset({"schema_catalog", "tenants"})

    pool = await get_shared_pool()
    try:
        async with pool.acquire() as conn:
            column_rows = await conn.fetch("""
                SELECT
                    c.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    CASE WHEN tc.constraint_type = 'PRIMARY KEY'
                         THEN true ELSE false END AS is_pk
                FROM information_schema.columns c
                LEFT JOIN information_schema.key_column_usage kcu
                    ON  c.table_name   = kcu.table_name
                    AND c.column_name  = kcu.column_name
                    AND c.table_schema = kcu.table_schema
                LEFT JOIN information_schema.table_constraints tc
                    ON  kcu.constraint_name = tc.constraint_name
                    AND tc.constraint_type  = 'PRIMARY KEY'
                    AND tc.table_schema     = kcu.table_schema
                WHERE c.table_schema = 'public'
                  AND c.table_name NOT IN ('schema_catalog', 'tenants')
                ORDER BY c.table_name, c.ordinal_position;
            """)

            fk_rows = await conn.fetch("""
                SELECT
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name  AS foreign_table,
                    ccu.column_name AS foreign_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON  tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema    = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON  tc.constraint_name = ccu.constraint_name
                    AND tc.table_schema    = ccu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema    = 'public';
            """)

        fk_map: dict[str, list[dict[str, str]]] = {}
        for fk in fk_rows:
            fk_map.setdefault(fk["table_name"], []).append({
                "column": fk["column_name"],
                "foreign_table": fk["foreign_table"],
                "foreign_column": fk["foreign_column"],
            })

        tables: dict[str, dict[str, Any]] = {}
        for row in column_rows:
            t_name = row["table_name"]
            if t_name in _EXCLUDED_TABLES:
                continue
            if t_name not in tables:
                tables[t_name] = {
                    "table_name": t_name,
                    "columns": [],
                    "foreign_keys": fk_map.get(t_name, []),
                    "description": f"Table {t_name} in the enterprise database",
                }
            col_name = row["column_name"]
            col_fk = next(
                (fk for fk in fk_map.get(t_name, []) if fk["column"] == col_name), None
            )
            tables[t_name]["columns"].append({
                "name": col_name,
                "type": row["data_type"].upper(),
                "is_pk": bool(row["is_pk"]),
                "is_fk": col_fk is not None,
                "foreign_table": col_fk["foreign_table"] if col_fk else None,
                "foreign_column": col_fk["foreign_column"] if col_fk else None,
                "is_pii": col_name.lower() in _PII_COLUMN_NAMES,
            })

        catalog = list(tables.values())
        _schema_catalog = catalog
        logger.info("get_schema: discovered %d tables", len(catalog))
        return json.dumps(catalog)

    except Exception as exc:
        logger.error("get_schema failed: %s", exc)
        return json.dumps([])


# ---------------------------------------------------------------------------
# Tool 2: execute_query
# ---------------------------------------------------------------------------

@mcp.tool()
async def execute_query(sql: str, tenant_id: str) -> str:
    """
    Execute a SQL query safely:
    1. AST validate (SELECT only)
    2. Enforce LIMIT cap at 100
    3. Set RLS tenant context
    4. EXPLAIN cost gate (threshold 10000)
    5. Execute query
    6. PII redact results
    Returns JSON: {raw_results, explain_cost, row_count}
    """
    from core.ast_validator import validate_sql
    from core.cost_evaluator import evaluate_cost
    from core.pii_redactor import redact_rows
    from db.postgres import get_shared_pool

    # 1. AST Validation
    try:
        validate_sql(sql)
    except Exception as exc:
        return json.dumps({"error": f"AST Validation Error: {exc}", "raw_results": [], "explain_cost": 0.0})

    # 2. Enforce LIMIT
    try:
        from sqlglot import parse as sqlglot_parse
        statements = sqlglot_parse(sql)
        if statements and hasattr(statements[0], 'args'):
            tree = statements[0]
            existing_limit = tree.args.get("limit")
            if existing_limit is None:
                tree = tree.limit(100)
            else:
                try:
                    limit_val = int(existing_limit.expression.this)
                    if limit_val > 100:
                        tree = tree.limit(100)
                except (AttributeError, ValueError, TypeError):
                    pass
            sql = tree.sql()
    except Exception:
        if "limit" not in sql.lower():
            sql = f"{sql.rstrip().rstrip(';')} LIMIT 100"

    # 3-5. Execute with RLS + cost gate
    pool = await get_shared_pool()
    safe_tenant = _format_uuid(tenant_id)

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # RLS
                await conn.execute(
                    "SELECT set_config('app.current_tenant_id', $1, true);", safe_tenant
                )
                # Cost gate
                explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
                explain_records = await asyncio.wait_for(
                    conn.fetch(explain_sql), timeout=_QUERY_TIMEOUT_SECONDS
                )
                estimated_cost = 100.0
                if explain_records and "QUERY PLAN" in explain_records[0]:
                    raw_plan = explain_records[0]["QUERY PLAN"]
                    plan_json = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
                    cost_eval = evaluate_cost(plan_json, threshold=10000.0)
                    if not cost_eval.within_threshold:
                        return json.dumps({
                            "error": f"Query Cost Rejected: {cost_eval.reason}",
                            "raw_results": [],
                            "explain_cost": cost_eval.total_cost,
                        })
                    estimated_cost = cost_eval.total_cost

                # Execute
                records = await asyncio.wait_for(
                    conn.fetch(sql), timeout=_QUERY_TIMEOUT_SECONDS
                )

        if len(records) > _MAX_RESULT_ROWS:
            records = records[:_MAX_RESULT_ROWS]

        results = [_serialize_row(dict(r)) for r in records]

        # 6. PII Redaction
        redacted = redact_rows(results)

        return json.dumps({
            "raw_results": redacted,
            "explain_cost": estimated_cost,
            "row_count": len(redacted),
        })

    except asyncio.TimeoutError:
        return json.dumps({"error": "Query timed out. Simplify or add filters.", "raw_results": [], "explain_cost": 0.0})
    except Exception as exc:
        return json.dumps({"error": f"Database Execution Error: {exc}", "raw_results": [], "explain_cost": 0.0})


# ---------------------------------------------------------------------------
# Tool 3: generate_chart
# ---------------------------------------------------------------------------

@mcp.tool()
def generate_chart(raw_data: list[dict[str, Any]], chart_type: str = "auto") -> str:
    """
    Generate a Chart.js configuration from query results.
    Supported chart_type values: auto, bar, line, pie, scatter.
    Auto-detection logic:
      - 2 numeric columns → scatter
      - date/month/year key → line
      - <= 8 rows + categorical → pie
      - default → bar
    Returns JSON Chart.js config dict.
    """
    if not raw_data:
        return json.dumps({"type": "empty", "data": {}, "options": {}})

    first_row = raw_data[0]
    keys = list(first_row.keys())
    label_key = next((k for k in keys if isinstance(first_row[k], str)), keys[0])
    numeric_keys = [k for k in keys if isinstance(first_row[k], (int, float))]

    if not numeric_keys:
        return json.dumps({"type": "table", "columns": keys, "data": raw_data})

    # Auto-detect chart type
    if chart_type == "auto":
        if len(numeric_keys) >= 2:
            chart_type = "scatter"
        elif any(w in label_key.lower() for w in ["month", "date", "year", "time", "week", "day"]):
            chart_type = "line"
        elif len(raw_data) <= 8 and isinstance(first_row.get(label_key), str):
            chart_type = "pie"
        else:
            chart_type = "bar"

    labels = [str(r.get(label_key, f"Row {i}")) for i, r in enumerate(raw_data)]
    value_key = numeric_keys[0]
    data_points = [float(r.get(value_key, 0)) for r in raw_data]

    # Color palettes per type
    _PIE_COLORS = [
        "rgba(99,102,241,0.85)", "rgba(168,85,247,0.85)", "rgba(236,72,153,0.85)",
        "rgba(20,184,166,0.85)", "rgba(245,158,11,0.85)", "rgba(239,68,68,0.85)",
        "rgba(34,197,94,0.85)", "rgba(59,130,246,0.85)",
    ]

    if chart_type == "scatter" and len(numeric_keys) >= 2:
        x_key, y_key = numeric_keys[0], numeric_keys[1]
        scatter_data = [{"x": float(r.get(x_key, 0)), "y": float(r.get(y_key, 0))} for r in raw_data]
        return json.dumps({
            "type": "scatter",
            "data": {
                "datasets": [{
                    "label": f"{x_key} vs {y_key}",
                    "data": scatter_data,
                    "backgroundColor": "rgba(20,184,166,0.7)",
                    "pointRadius": 6,
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {"legend": {"position": "top"},
                            "title": {"display": True, "text": f"{x_key} vs {y_key} Correlation"}},
                "scales": {"x": {"title": {"display": True, "text": x_key}},
                            "y": {"title": {"display": True, "text": y_key}}},
            },
        })

    if chart_type == "pie":
        return json.dumps({
            "type": "pie",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": value_key.replace("_", " ").title(),
                    "data": data_points,
                    "backgroundColor": _PIE_COLORS[:len(labels)],
                    "borderWidth": 2,
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "legend": {"position": "right"},
                    "title": {"display": True, "text": f"{value_key.replace('_', ' ').title()} Distribution"},
                },
            },
        })

    # bar / line shared structure
    bg_color = "rgba(99,102,241,0.7)" if chart_type == "bar" else "rgba(168,85,247,0.3)"
    border_color = "rgba(99,102,241,1)" if chart_type == "bar" else "rgba(168,85,247,1)"
    dataset: dict[str, Any] = {
        "label": value_key.replace("_", " ").title(),
        "data": data_points,
        "backgroundColor": bg_color,
        "borderColor": border_color,
        "borderWidth": 2,
    }
    if chart_type == "line":
        dataset["fill"] = True
        dataset["tension"] = 0.4

    return json.dumps({
        "type": chart_type,
        "data": {"labels": labels, "datasets": [dataset]},
        "options": {
            "responsive": True,
            "plugins": {
                "legend": {"position": "top"},
                "title": {"display": True, "text": f"{value_key.replace('_', ' ').title()} Overview"},
            },
        },
    })


# ---------------------------------------------------------------------------
# Tool 4: generate_flowchart
# ---------------------------------------------------------------------------

@mcp.tool()
def generate_flowchart(
    diagram_type: str,
    raw_data: list[dict[str, Any]] | None = None,
    schema: list[dict[str, Any]] | None = None,
    title: str = "",
) -> str:
    """
    Generate a Mermaid diagram string.
    diagram_type options:
      - 'er'       : Entity-Relationship diagram from schema FK relationships
      - 'process'  : Flowchart TD from result rows (sequential steps)
      - 'decision' : Decision tree with conditional branches (bonus)
    Returns JSON: {mermaid: str, diagram_type: str}
    """
    raw_data = raw_data or []
    schema = schema or _schema_catalog

    if diagram_type == "er":
        mermaid = _build_er_diagram(schema)
    elif diagram_type == "process":
        mermaid = _build_process_flow(raw_data, title)
    elif diagram_type == "decision":
        mermaid = _build_decision_tree(raw_data, title)
    else:
        mermaid = _build_process_flow(raw_data, title)

    return json.dumps({"mermaid": mermaid, "diagram_type": diagram_type})


def _build_er_diagram(schema: list[dict[str, Any]]) -> str:
    """Build Mermaid erDiagram from schema FK relationships."""
    if not schema:
        return "erDiagram\n  NO_SCHEMA_LOADED"

    lines = ["erDiagram"]
    for table in schema:
        t_name = table["table_name"].upper().replace("-", "_")
        cols = table.get("columns", [])
        lines.append(f"  {t_name} {{")
        for col in cols:
            # Clean data type for Mermaid (alphanumeric/underscore only, no parens or spaces)
            raw_type = str(col.get("type", "STRING")).upper()
            clean_type = raw_type.split("(")[0].replace(" ", "_").replace("-", "_")
            c_name = str(col.get("name", "")).replace("-", "_")
            pk_marker = " PK" if col.get("is_pk") else (" FK" if col.get("is_fk") else "")
            pii_marker = " \"PII\"" if col.get("is_pii") else ""
            lines.append(f"    {clean_type} {c_name}{pk_marker}{pii_marker}")
        lines.append("  }")

    # Relationships
    seen_rels = set()
    for table in schema:
        t_name = table["table_name"].upper().replace("-", "_")
        for fk in table.get("foreign_keys", []):
            foreign = fk["foreign_table"].upper().replace("-", "_")
            col = fk["column"].replace("-", "_")
            rel_str = f"  {t_name} ||--o{{ {foreign} : \"{col}\""
            if rel_str not in seen_rels:
                seen_rels.add(rel_str)
                lines.append(rel_str)

    return "\n".join(lines)


def _build_process_flow(raw_data: list[dict[str, Any]], title: str = "") -> str:
    """Build Mermaid flowchart TD from result rows as sequential process steps."""
    if not raw_data:
        return "flowchart TD\n  NO_DATA[No data available]"

    lines = ["flowchart TD"]
    if title:
        lines.append(f"  TITLE[\"<b>{title}</b>\"]")    

    keys = list(raw_data[0].keys())
    label_key = next((k for k in keys if isinstance(raw_data[0][k], str)), keys[0])
    value_key = next((k for k in keys if isinstance(raw_data[0][k], (int, float))), None)

    prev_id = None
    for i, row in enumerate(raw_data[:15]):  # cap at 15 nodes
        node_id = f"N{i}"
        label = str(row.get(label_key, f"Step {i+1}"))
        if value_key:
            val = row.get(value_key, "")
            node_def = f"  {node_id}[\"{label}\\n{value_key}: {val}\"]"
        else:
            node_def = f"  {node_id}[\"{label}\"]"
        lines.append(node_def)
        if prev_id:
            lines.append(f"  {prev_id} --> {node_id}")
        prev_id = node_id

    return "\n".join(lines)


def _build_decision_tree(raw_data: list[dict[str, Any]], title: str = "") -> str:
    """Build Mermaid decision tree with conditional branches (bonus)."""
    if not raw_data:
        return "flowchart TD\n  NO_DATA[No data available]"

    lines = ["flowchart TD"]
    keys = list(raw_data[0].keys())
    label_key = next((k for k in keys if isinstance(raw_data[0][k], str)), keys[0])
    value_key = next((k for k in keys if isinstance(raw_data[0][k], (int, float))), None)

    if not value_key or len(raw_data) < 2:
        return _build_process_flow(raw_data, title)

    # Find median for decision split
    values = sorted([float(r.get(value_key, 0)) for r in raw_data])
    median = values[len(values) // 2]

    lines.append(f"  ROOT{{\"Is {value_key} > {median:.1f}?\"}}")
    above = [r for r in raw_data if float(r.get(value_key, 0)) > median]
    below = [r for r in raw_data if float(r.get(value_key, 0)) <= median]

    for i, row in enumerate(above[:5]):
        node_id = f"A{i}"
        label = str(row.get(label_key, f"Item {i+1}"))
        val = row.get(value_key, "")
        lines.append(f"  {node_id}[\"{label}: {val}\"]")
        lines.append(f"  ROOT -->|Yes| {node_id}")

    for i, row in enumerate(below[:5]):
        node_id = f"B{i}"
        label = str(row.get(label_key, f"Item {i+1}"))
        val = row.get(value_key, "")
        lines.append(f"  {node_id}[\"{label}: {val}\"]")
        lines.append(f"  ROOT -->|No| {node_id}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 5: explain_data
# ---------------------------------------------------------------------------

@mcp.tool()
async def explain_data(prompt: str, raw_results: list[dict[str, Any]]) -> str:
    """
    Translate SQL query results into a plain-language executive summary.
    Calls Gemini API to generate a 2-sentence business-focused summary.
    Returns JSON: {summary: str, key_metrics: list[str]}
    """
    from app.config import get_settings

    settings = get_settings()
    if not settings.gemini_api_key or not raw_results:
        fallback = f"Query returned {len(raw_results)} rows." if raw_results else "No data returned."
        return json.dumps({"summary": fallback, "key_metrics": []})

    try:
        system_instruction = (
            "You are a senior data analyst. Given a user question and dataset, "
            "provide a concise 2-sentence executive summary highlighting key metrics and insights. "
            "Also return up to 3 key metric strings in a 'key_metrics' list."
            "Output ONLY valid JSON: {\"summary\": \"...\", \"key_metrics\": [\"...\", ...]}"
        )
        user_content = f"Question: {prompt}\nDataset (first 10 rows): {json.dumps(raw_results[:10])}"
        model_name = settings.gemini_model.strip()
        if model_name.startswith("models/"):
            model_name = model_name[len("models/"):]
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system_instruction}\n\n{user_content}"}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model_name}:generateContent?key={settings.gemini_api_key}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                parsed = json.loads(text)
                return json.dumps({
                    "summary": parsed.get("summary", ""),
                    "key_metrics": parsed.get("key_metrics", []),
                })
    except Exception as exc:
        logger.warning("explain_data Gemini call failed: %s", exc)

    fallback = f"Query returned {len(raw_results)} rows for: {prompt[:80]}"
    return json.dumps({"summary": fallback, "key_metrics": []})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
