"""
MCP Server — AI Database Agent Tools
=====================================
Exposes 7 tools via FastMCP (stdio transport):
  1. get_schema       — fetch raw DB schema from information_schema
  2. execute_query    — validate + execute SQL with RLS, cost gate, PII redact
  3. generate_chart   — build Chart.js spec (bar/line/pie/scatter)
  4. generate_flowchart — build Mermaid diagram (er/process/decision)
  5. explain_data     — Gemini LLM plain-language summary
  6. analyze_data     — deterministic metrics, trends, outliers, and quality checks
  7. verify_response  — confirm all planned artifacts were delivered
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

# Ensure src/ is on the path so we can import agent modules
_src_root = str(Path(__file__).resolve().parent.parent)
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)

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
        statements = sqlglot_parse(sql, read="postgres")
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
            sql = tree.sql(dialect="postgres")
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
def generate_chart(
    raw_data: list[dict[str, Any]],
    chart_type: str = "auto",
    request: str = "",
) -> str:
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

    keys = list(dict.fromkeys(key for row in raw_data for key in row))
    numeric_keys = [
        key for key in keys
        if any(isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)
               for row in raw_data)
    ]
    text_keys = [
        key for key in keys
        if key not in numeric_keys and any(row.get(key) is not None for row in raw_data)
    ]
    time_key = next(
        (key for key in text_keys
         if any(token in key.lower() for token in ("date", "time", "month", "year", "week", "day", "quarter"))),
        None,
    )
    category_keys = [key for key in text_keys if key != time_key]
    label_key = time_key or (text_keys[0] if text_keys else keys[0])

    if not numeric_keys:
        return json.dumps({"type": "table", "columns": keys, "data": raw_data})

    # Auto-detect chart type
    if chart_type == "auto":
        if time_key:
            chart_type = "line"
        elif len(numeric_keys) >= 2 and not text_keys:
            chart_type = "scatter"
        elif len(raw_data) <= 8 and text_keys:
            chart_type = "pie"
        else:
            chart_type = "bar"

    value_key = numeric_keys[0]

    def display_label(value: Any) -> str:
        text = str(value)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.day == 1:
                return parsed.strftime("%b %Y")
            return parsed.strftime("%d %b %Y")
        except (ValueError, TypeError):
            return text

    # Color palettes per type
    _PIE_COLORS = [
        "rgba(99,102,241,0.85)", "rgba(168,85,247,0.85)", "rgba(236,72,153,0.85)",
        "rgba(20,184,166,0.85)", "rgba(245,158,11,0.85)", "rgba(239,68,68,0.85)",
        "rgba(34,197,94,0.85)", "rgba(59,130,246,0.85)",
    ]
    _SERIES_COLORS = [
        ("rgba(99,102,241,1)", "rgba(99,102,241,0.18)"),
        ("rgba(20,184,166,1)", "rgba(20,184,166,0.18)"),
        ("rgba(245,158,11,1)", "rgba(245,158,11,0.18)"),
        ("rgba(236,72,153,1)", "rgba(236,72,153,0.18)"),
        ("rgba(59,130,246,1)", "rgba(59,130,246,0.18)"),
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

    # A temporal dimension plus a category (month + product, for example)
    # becomes one line per category. Missing points remain null rather than
    # being presented as real zero values.
    if chart_type == "line" and time_key and category_keys:
        series_key = category_keys[0]
        raw_labels = list(dict.fromkeys(row.get(time_key) for row in raw_data if row.get(time_key) is not None))
        series_names = list(dict.fromkeys(
            str(row.get(series_key)) for row in raw_data if row.get(series_key) is not None
        ))
        totals: dict[tuple[str, Any], float] = {}
        for row in raw_data:
            if row.get(time_key) is None or row.get(series_key) is None:
                continue
            try:
                key = (str(row[series_key]), row[time_key])
                totals[key] = totals.get(key, 0.0) + float(row.get(value_key, 0) or 0)
            except (TypeError, ValueError):
                continue
        datasets = []
        for index, series_name in enumerate(series_names):
            border, background = _SERIES_COLORS[index % len(_SERIES_COLORS)]
            datasets.append({
                "label": series_name,
                "data": [totals.get((series_name, raw_label)) for raw_label in raw_labels],
                "backgroundColor": background,
                "borderColor": border,
                "borderWidth": 2,
                "fill": False,
                "tension": 0.3,
            })
        return json.dumps({
            "type": "line",
            "data": {"labels": [display_label(label) for label in raw_labels], "datasets": datasets},
            "options": {
                "responsive": True,
                "plugins": {
                    "legend": {"position": "top"},
                    "title": {"display": True, "text": f"{value_key.replace('_', ' ').title()} Trend"},
                },
            },
        })

    # Bar and pie charts aggregate a non-temporal category across repeated
    # rows, so a product-total comparison does not repeat every month label.
    aggregate_key = category_keys[0] if category_keys else label_key
    aggregate_totals: dict[str, float] = {}
    for index, row in enumerate(raw_data):
        label = display_label(row.get(aggregate_key, f"Row {index + 1}"))
        try:
            aggregate_totals[label] = aggregate_totals.get(label, 0.0) + float(row.get(value_key, 0) or 0)
        except (TypeError, ValueError):
            continue
    labels = list(aggregate_totals)
    data_points = list(aggregate_totals.values())

    if chart_type == "pie":
        return json.dumps({
            "type": "pie",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": value_key.replace("_", " ").title(),
                    "data": data_points,
                    "backgroundColor": [_PIE_COLORS[i % len(_PIE_COLORS)] for i in range(len(labels))],
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

    # Single-series bar / line structure.
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
                "title": {
                    "display": True,
                    "text": request[:80] if request else f"{value_key.replace('_', ' ').title()} Overview",
                },
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
      - 'process'  : Semantic state, ordered-step, or agent-execution flow
      - 'decision' : Decision tree with conditional branches (bonus)
    Returns JSON: {mermaid: str, diagram_type: str, process_mode: str | null}
    """
    raw_data = raw_data or []
    schema = schema or _schema_catalog

    if diagram_type == "er":
        mermaid = _build_er_diagram(schema)
        process_mode = None
    elif diagram_type == "process":
        process_mode = _detect_process_mode(raw_data)
        mermaid = _build_process_flow(raw_data, title, process_mode)
    elif diagram_type == "decision":
        mermaid = _build_decision_tree(raw_data, title)
        process_mode = None
    else:
        diagram_type = "process"
        process_mode = _detect_process_mode(raw_data)
        mermaid = _build_process_flow(raw_data, title, process_mode)

    return json.dumps({
        "mermaid": mermaid,
        "diagram_type": diagram_type,
        "process_mode": process_mode,
    })


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


_FROM_STATE_ALIASES = {
    "from_state", "from_status", "previous_state", "previous_status", "source", "source_state",
}
_TO_STATE_ALIASES = {
    "to_state", "to_status", "next_state", "next_status", "new_state", "new_status", "target", "target_state",
}
_STEP_ORDER_ALIASES = {"step_order", "step_number", "sequence", "sequence_number", "position"}
_STEP_LABEL_ALIASES = {"step", "step_name", "stage", "stage_name", "activity", "action"}


def _find_key(keys: list[str], aliases: set[str]) -> str | None:
    return next((key for key in keys if key.lower().strip() in aliases), None)


def _detect_process_mode(raw_data: list[dict[str, Any]]) -> str:
    """Classify process-shaped data without fuzzy substring matches."""
    if not raw_data:
        return "not_applicable"
    keys = list(dict.fromkeys(key for row in raw_data for key in row))
    if _find_key(keys, _FROM_STATE_ALIASES) and _find_key(keys, _TO_STATE_ALIASES):
        return "state_transitions"
    if _find_key(keys, _STEP_ORDER_ALIASES) and _find_key(keys, _STEP_LABEL_ALIASES):
        return "ordered_steps"
    return "agent_pipeline"


def _mermaid_label(value: Any, max_length: int = 72) -> str:
    """Create a compact label safe for a quoted Mermaid node."""
    text = " ".join(str(value).replace('"', "'").split())
    return text if len(text) <= max_length else text[:max_length - 3].rstrip() + "..."


def _build_process_flow(
    raw_data: list[dict[str, Any]],
    title: str = "",
    mode: str | None = None,
) -> str:
    """Build a semantic state, ordered-stage, or agent-execution flow."""
    if not raw_data:
        return "flowchart TD\n  NOT_APPLICABLE[No process or query data available]"

    keys = list(dict.fromkeys(key for row in raw_data for key in row))
    mode = mode or _detect_process_mode(raw_data)

    if mode == "state_transitions":
        from_key = _find_key(keys, _FROM_STATE_ALIASES)
        to_key = _find_key(keys, _TO_STATE_ALIASES)
        count_key = next((key for key in keys if key.lower() in {"count", "transition_count", "total"}), None)
        assert from_key and to_key
        transitions: dict[tuple[str, str], float] = {}
        for row in raw_data:
            source = _mermaid_label(row.get(from_key) or "Start")
            target = _mermaid_label(row.get(to_key) or "End")
            try:
                weight = float(row.get(count_key, 1) or 1) if count_key else 1.0
            except (TypeError, ValueError):
                weight = 1.0
            transitions[(source, target)] = transitions.get((source, target), 0.0) + weight

        lines = ["flowchart LR"]
        node_ids: dict[str, str] = {}

        def get_id(label: str) -> str:
            if label not in node_ids:
                node_ids[label] = f"S{len(node_ids)}"
                lines.append(f'  {node_ids[label]}["{label}"]')
            return node_ids[label]

        for (source, target), count in transitions.items():
            count_label = int(count) if count.is_integer() else round(count, 2)
            lines.append(f"  {get_id(source)} -->|{count_label}| {get_id(target)}")
        lines.append("  classDef state fill:#172554,stroke:#6366f1,color:#f4f4f5")
        lines.append(f"  class {','.join(node_ids.values())} state")
        return "\n".join(lines)

    if mode == "ordered_steps":
        order_key = _find_key(keys, _STEP_ORDER_ALIASES)
        label_key = _find_key(keys, _STEP_LABEL_ALIASES)
        assert order_key and label_key
        owner_key = next((key for key in keys if key.lower() in {"owner", "assignee", "actor", "team"}), None)
        duration_key = next((key for key in keys if "duration" in key.lower()), None)
        def order_value(row: dict[str, Any]) -> tuple[bool, float, str]:
            value = row.get(order_key)
            try:
                return value is None, float(value), ""
            except (TypeError, ValueError):
                return value is None, float("inf"), str(value or "")

        ordered = sorted(raw_data, key=order_value)[:20]
        lines = ["flowchart LR", "  START([Start])"]
        previous = "START"
        for index, row in enumerate(ordered):
            details = [_mermaid_label(row.get(label_key) or f"Step {index + 1}")]
            if owner_key and row.get(owner_key):
                details.append(f"Owner: {_mermaid_label(row[owner_key], 32)}")
            if duration_key and row.get(duration_key):
                details.append(f"Duration: {_mermaid_label(row[duration_key], 24)}")
            node_id = f"STEP{index}"
            label = "<br/>".join(details)
            lines.append(f'  {node_id}["{label}"]')
            lines.append(f"  {previous} --> {node_id}")
            previous = node_id
        lines.extend([f"  {previous} --> DONE([Complete])", "  classDef terminal fill:#064e3b,stroke:#10b981,color:#f4f4f5"])
        lines.append("  class START,DONE terminal")
        return "\n".join(lines)

    # Analytical rows are not business-process stages. Show the actual agent
    # workflow used to produce the requested analysis instead of chaining rows.
    request_label = _mermaid_label(title or "Analyze database request", 64)
    row_count = len(raw_data)
    return "\n".join([
        "flowchart LR",
        f'  START(["Request: {request_label}"])',
        '  SCHEMA["Discover relevant schema"]',
        '  SQL["Generate read-only SQL"]',
        '  SAFETY{"AST and cost checks pass?"}',
        '  EXEC[("Execute tenant-scoped query")]',
        f'  ANALYZE["Analyze {row_count} returned rows"]',
        '  VIS["Generate requested visualizations"]',
        '  EXPLAIN["Explain grounded findings"]',
        '  VERIFY{"All requested outputs delivered?"}',
        '  REPAIR["Repair failed task"]',
        '  DONE(["Return verified response"])',
        "  START --> SCHEMA --> SQL --> SAFETY",
        "  SAFETY -->|Yes| EXEC --> ANALYZE --> VIS --> EXPLAIN --> VERIFY",
        "  SAFETY -->|No| REPAIR --> SQL",
        "  VERIFY -->|No| REPAIR",
        "  VERIFY -->|Yes| DONE",
        "  classDef terminal fill:#064e3b,stroke:#10b981,color:#f4f4f5",
        "  classDef decision fill:#422006,stroke:#f59e0b,color:#f4f4f5",
        "  class START,DONE terminal",
        "  class SAFETY,VERIFY decision",
    ])


def _build_decision_tree(raw_data: list[dict[str, Any]], title: str = "") -> str:
    """Build Mermaid decision tree with conditional branches."""
    if not raw_data:
        return "flowchart TD\n  NO_DATA[No data available]"

    lines = ["flowchart TD"]
    keys = list(raw_data[0].keys())
    
    # Try to find a decision outcome column
    decision_key = next((k for k in keys if "decision" in k.lower() or "status" in k.lower() or "outcome" in k.lower()), None)
    numeric_keys = [k for k in keys if isinstance(raw_data[0][k], (int, float))]
    
    if decision_key and numeric_keys:
        feature_key = numeric_keys[0]
        values = sorted([float(r.get(feature_key, 0)) for r in raw_data])
        median = values[len(values) // 2] if values else 0
        
        lines.append(f"  ROOT{{\"Is {feature_key} > {median:.1f}?\"}}")
        
        above = [r for r in raw_data if float(r.get(feature_key, 0)) > median]
        below = [r for r in raw_data if float(r.get(feature_key, 0)) <= median]
        
        # Aggregate decisions
        def agg_decision(subset):
            if not subset:
                return "Unknown"
            counts = {}
            for r in subset:
                d = str(r.get(decision_key, "Unknown"))
                counts[d] = counts.get(d, 0) + 1
            return max(counts.items(), key=lambda x: x[1])[0]
            
        above_dec = agg_decision(above)
        below_dec = agg_decision(below)
        
        lines.append(f"  A[\"{decision_key}: {above_dec}\\n({len(above)} cases)\"]")
        lines.append("  ROOT -->|Yes| A")
        
        lines.append(f"  B[\"{decision_key}: {below_dec}\\n({len(below)} cases)\"]")
        lines.append("  ROOT -->|No| B")
        
        return "\n".join(lines)

    # Fallback to simple split
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
    Translate SQL query results + diagram context into a rich, structured explanation.
    Calls Gemini API to generate a business-focused narrative covering every artifact.
    Returns JSON: {summary: str, key_metrics: list[str]}
    """
    from app.config import get_settings

    settings = get_settings()
    if not settings.gemini_api_key or not raw_results:
        fallback = f"Query returned {len(raw_results)} rows." if raw_results else "No data returned."
        return json.dumps({"summary": fallback, "key_metrics": []})

    try:
        system_instruction = (
            "You are a senior data analyst writing a business intelligence report. "
            "The user's request and context is given below. Follow the instructions in the prompt carefully.\n\n"
            "Output ONLY valid JSON in the following format. The 'summary' field must be a single string containing the markdown-formatted text:\n"
            "{\n"
            '  "summary": "Your formatted markdown response here",\n'
            '  "key_metrics": ["metric 1", "metric 2"]\n'
            "}\n\n"
            "Rules:\n"
            "1. Be specific with numbers from the data. Cite actual values.\n"
            "2. Do NOT repeat the same paragraph multiple times. Write concisely and move to the next point.\n"
            "3. Do NOT wrap the JSON in markdown blocks (e.g. ```json)."
        )
        user_content = f"Context & Request:\n{prompt}\n\nData (first 10 rows): {json.dumps(raw_results[:10])}"
        model_name = settings.gemini_model.strip()
        if model_name.startswith("models/"):
            model_name = model_name[len("models/"):]
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{system_instruction}\n\n{user_content}"}]}],
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
        }
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model_name}:generateContent?key={settings.gemini_api_key}")

        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
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
# Tool 6: analyze_data
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_data(
    raw_data: list[dict[str, Any]],
    analysis_types: list[str] | None = None,
) -> str:
    """
    Compute grounded analytics without an LLM.

    Supported analysis_types: summary, trend, outliers, quality, contributors.
    If omitted, all analyses run. Returns JSON containing numeric summaries,
    period change, top contributors, IQR outliers, data-quality observations,
    and a recommended chart type.
    """
    from services import analyze_rows

    return json.dumps(analyze_rows(raw_data, analysis_types), default=str)


# ---------------------------------------------------------------------------
# Tool 7: verify_response
# ---------------------------------------------------------------------------

@mcp.tool()
def verify_response(
    supervisor_plan: dict[str, Any],
    sql_query: str = "",
    raw_data: list[dict[str, Any]] | None = None,
    visualizations: list[dict[str, Any]] | None = None,
    summary: str = "",
    data_analysis: dict[str, Any] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    schema_available: bool = False,
    fatal_error: str = "",
    original_prompt: str = "",
) -> str:
    """
    Verify response completeness against the supervisor's execution plan.

    Returns requested, delivered, and missing artifacts; failed tool and
    data-quality warnings; a completion ratio; and complete/partial/failed
    status. This tool is deterministic and performs no LLM calls.
    """
    from services import verify_agent_response

    result = verify_agent_response(
        supervisor_plan=supervisor_plan,
        sql_query=sql_query,
        raw_data=raw_data,
        visualizations=visualizations,
        summary=summary,
        data_analysis=data_analysis,
        tool_calls=tool_calls,
        schema_available=schema_available,
        fatal_error=fatal_error,
        original_prompt=original_prompt,
    )
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
