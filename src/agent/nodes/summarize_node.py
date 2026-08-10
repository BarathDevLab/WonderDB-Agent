import logging
from typing import Any
from agent.state import AgentState
from app.config import get_settings

logger = logging.getLogger(__name__)
from services.semantic_cache import set_semantic_cache
from services.session_memory import append_session_event


def _build_chart_spec(raw_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate declarative Chart.js configuration from query result dataset."""
    if not raw_results:
        return {"type": "empty", "data": {}, "options": {}}

    first_row = raw_results[0]
    keys = list(first_row.keys())

    # Detect categorical label keys vs numeric value keys
    label_key = next((k for k in keys if isinstance(first_row[k], str)), keys[0])
    numeric_keys = [k for k in keys if isinstance(first_row[k], (int, float))]

    if not numeric_keys:
        return {
            "type": "table",
            "columns": keys,
            "data": raw_results,
        }

    value_key = numeric_keys[0]
    labels = [str(r.get(label_key, f"Row {i}")) for i, r in enumerate(raw_results)]
    data_points = [float(r.get(value_key, 0)) for r in raw_results]

    # Handle degenerate cases
    if len(data_points) == 1:
        chart_type = "bar"  # Single point always bar
    elif all(v == 0 for v in data_points):
        chart_type = "bar"  # All zeros — bar is clearest
    elif "month" in label_key.lower() or "date" in label_key.lower():
        chart_type = "line"
    else:
        chart_type = "bar"

    return {
        "type": chart_type,
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": value_key.replace("_", " ").title(),
                    "data": data_points,
                    "backgroundColor": "rgba(59, 130, 246, 0.6)",
                    "borderColor": "rgba(59, 130, 246, 1)",
                    "borderWidth": 1.5,
                }
            ],
        },
        "options": {
            "responsive": True,
            "plugins": {
                "legend": {"position": "top"},
                "title": {"display": True, "text": f"{value_key.replace('_', ' ').title()} Overview"},
            },
        },
    }


async def _synthesize_with_gemini(
    prompt: str,
    raw_results: list[dict[str, Any]],
    api_key: str | None = None,
    model: str = "",
) -> str | None:
    """Use Gemini API to formulate natural language summary of query results."""
    if not api_key or not raw_results:
        return None

    try:
        import httpx
        system_instruction = (
            "You are a senior data analyst. Given a user question and dataset, provide a concise 2-sentence executive summary highlighting key metrics."
        )
        user_content = f"Question: {prompt}\nDataset: {raw_results[:10]}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_instruction}\n\n{user_content}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
            }
        }

        if not model:
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text:
                    return text
    except Exception as exc:
        logger.warning("LLM synthesis failed: %s", exc)
        return None
    return None


async def _synthesize_with_llm(
    prompt: str,
    raw_results: list[dict[str, Any]],
    gemini_key: str | None = None,
    gemini_model: str = "",
) -> str | None:
    """Use Gemini to formulate clear, natural language synthesis of data results."""
    if not raw_results:
        return None

    if gemini_key:
        return await _synthesize_with_gemini(prompt, raw_results, gemini_key, gemini_model)

    return None


def _synthesize_summary_fallback(
    prompt: str, raw_results: list[dict[str, Any]], error_message: str | None
) -> str:
    if error_message:
        return f"Execution failed: {error_message}"
    
    return "LLM summary generation failed. Please check API keys and model availability."


async def summarize_node(state: AgentState) -> AgentState:
    """Synthesize final textual answer, generate chart specs, update semantic cache & session memory."""
    prompt = state.get("prompt", "")
    tenant_id = state.get("tenant_id", "default-tenant")
    session_id = state.get("session_id", f"session-{tenant_id}")
    raw_results = state.get("raw_results", [])
    sql_query = state.get("sql_query", "")
    error_message = state.get("error_message")
    settings = get_settings()

    if state.get("cached_hit") and state.get("summary"):
        summary = state["summary"]
        chart_spec = state.get("chart_spec") or _build_chart_spec(raw_results)
    else:
        llm_summary = await _synthesize_with_llm(
            prompt,
            raw_results,
            gemini_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
        )
        summary = llm_summary or _synthesize_summary_fallback(prompt, raw_results, error_message)
        chart_spec = _build_chart_spec(raw_results)

    # 1. Update Semantic Cache for future instant lookups (if enabled & query succeeded)
    cache_enabled = state.get("enable_cache", settings.enable_semantic_cache)
    if cache_enabled and not error_message and raw_results:
        await set_semantic_cache(
            prompt,
            {
                "sql_query": sql_query,
                "summary": summary,
                "chart_spec": chart_spec,
                "raw_results": raw_results,
            },
            tenant_id,
        )

    # 2. Append final synthesis to Session Memory
    await append_session_event(
        session_id,
        {
            "phase": "summary",
            "summary": summary,
            "chart_type": chart_spec.get("type"),
            "rows_count": len(raw_results),
        },
    )

    return {
        **state,
        "summary": summary,
        "chart_spec": chart_spec,
        "current_phase": "summarize_complete",
    }
