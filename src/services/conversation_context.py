"""Deterministic, token-bounded conversation context for follow-up requests."""
from __future__ import annotations

import re
from typing import Any


_REFERENCE_PATTERNS = (
    r"\b(?:same|previous|above|earlier|again|instead)\b",
    r"\b(?:show|explain|change|make|filter|compare|use|redo|repeat|visualize)\s+(?:it|that|those|these)\b",
    r"\b(?:it|that|those|these)\s+(?:as|by|for|with|without|in)\b",
    r"^(?:and|also|now|then)\b",
    r"^(?:what|how)\s+about\b",
    r"^(?:for|during)\s+(?:last|this|previous|next)\b",
    r"^(?:only|exclude|include|filter)\b",
    r"^(?:show|make|render|visualize)\s+(?:a|an|the)\s+(?:bar|line|pie|scatter)\b",
    r"^(?:which (?:one|ones|had|has|was|were)|who (?:was|were)|why (?:did|was|were)|where (?:did|was|were)|when (?:did|was|were))\b",
    r"\b(?:the|that)\s+(?:increase|decrease|spike|drop|trend|result|number|total|value|chart)\b",
)
_EXPLANATION_PATTERNS = (
    r"\b(?:explain|elaborate|clarify|simpler|plain english|break it down)\b",
    r"\bwhat does (?:it|that|this) mean\b",
    r"^(?:tell me more|continue|go on)\b",
)
_DATA_MODIFIER_PATTERNS = (
    r"\b(?:chart|graph|plot|diagram|table)\b",
    r"\b(?:filter|only|exclude|include|compare|versus|instead)\b",
    r"\b(?:trend|breakdown|comparison|totals?|average|count)\b",
    r"\b(?:last|this|previous|next)\s+(?:day|week|month|quarter|year)\b",
    r"\b(?:top|bottom)\s+\d+\b",
    r"\bby\s+[a-z_]+\b",
    r"^(?:what|how)\s+about\b",
    r"^(?:and|also|now|then)\s+(?:show|filter|compare|break|group|sort)\b",
)


def _compact(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _latest_grounded_turn(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Prefer completed turns, but preserve actual recency across query and chat.
    for event in reversed(history):
        if event.get("phase") in {"summary", "chat"} and event.get("prompt"):
            return event
    for event in reversed(history):
        if event.get("phase") == "plan" and event.get("prompt"):
            return event
    return None


def _recent_grounded_turns(
    history: list[dict[str, Any]], limit: int = 3,
) -> list[dict[str, Any]]:
    """Return distinct recent turns in chronological order, preferring summaries."""
    selected: list[dict[str, Any]] = []
    seen_prompts: set[str] = set()
    for event in reversed(history):
        if event.get("phase") not in {"summary", "chat", "plan"}:
            continue
        normalized = _compact(event.get("prompt"), 600).lower()
        if not normalized or normalized in seen_prompts:
            continue
        seen_prompts.add(normalized)
        selected.append({
            "prompt": _compact(event.get("prompt"), 600),
            "sql_query": _compact(event.get("sql_query"), 900),
            "summary": _compact(event.get("summary"), 900),
            "rows_count": event.get("rows_count"),
            "chart_type": event.get("chart_type"),
            "chart_types": event.get("chart_types", []),
            "diagram_types": event.get("diagram_types", []),
            "result_sample": event.get("result_sample", []),
        })
        if len(selected) >= limit:
            break
    return list(reversed(selected))


def build_conversation_context(
    history: list[dict[str, Any]], current_prompt: str,
) -> dict[str, Any]:
    """Resolve whether the current prompt depends on the latest grounded turn."""
    previous = _latest_grounded_turn(history)
    recent_turns = _recent_grounded_turns(history)
    prompt = _compact(current_prompt, 2000)
    if not previous:
        return {
            "is_followup": False,
            "followup_kind": "none",
            "resolved_prompt": prompt,
            "schema_prompt": prompt,
            "recent_turns": [],
        }

    lowered = prompt.lower()
    is_reference = any(re.search(pattern, lowered) for pattern in _REFERENCE_PATTERNS)
    explanation = any(re.search(pattern, lowered) for pattern in _EXPLANATION_PATTERNS)
    data_modifier = any(re.search(pattern, lowered) for pattern in _DATA_MODIFIER_PATTERNS)
    if not is_reference and not explanation:
        return {
            "is_followup": False,
            "followup_kind": "none",
            "resolved_prompt": prompt,
            "schema_prompt": prompt,
            "recent_turns": recent_turns,
        }

    previous_prompt = _compact(previous.get("prompt"), 600)
    previous_sql = _compact(previous.get("sql_query"), 900)
    previous_summary = _compact(previous.get("summary"), 900)
    followup_kind = "explanation" if explanation and not data_modifier else "data"
    context = {
        "is_followup": True,
        "followup_kind": followup_kind,
        "previous_prompt": previous_prompt,
        "previous_sql": previous_sql,
        "previous_summary": previous_summary,
        "previous_rows_count": previous.get("rows_count"),
        "previous_chart_type": previous.get("chart_type"),
        "previous_chart_types": previous.get("chart_types", []),
        "previous_diagram_types": previous.get("diagram_types", []),
        "previous_result_sample": previous.get("result_sample", []),
        "recent_turns": recent_turns,
    }
    context["schema_prompt"] = (
        f"Previous request: {previous_prompt}. Current follow-up: {prompt}"
    )
    context["resolved_prompt"] = "\n".join(filter(None, [
        "[CONVERSATION CONTEXT - use only to resolve the current follow-up]",
        f"Previous user request: {previous_prompt}",
        f"Previous SQL: {previous_sql}" if previous_sql else "",
        "[CURRENT USER REQUEST - this overrides previous constraints]",
        prompt,
        "Produce the result for the combined intent. Do not repeat the previous result unchanged.",
    ]))
    return context


def format_context_for_model(context: dict[str, Any]) -> str:
    """Format a small explicit context block suitable for less capable models."""
    lines = [
        f"Deterministic follow-up detected: {bool(context.get('is_followup'))}",
        f"Follow-up type: {context.get('followup_kind', 'none')}",
    ]
    recent_turns = context.get("recent_turns", [])
    if recent_turns:
        for index, turn in enumerate(recent_turns, start=1):
            lines.append(f"Turn {index} user request: {turn.get('prompt', '')}")
            if turn.get("sql_query"):
                lines.append(f"Turn {index} SQL: {turn['sql_query']}")
            if turn.get("summary"):
                lines.append(f"Turn {index} answer: {turn['summary']}")
            if turn.get("result_sample"):
                lines.append(f"Turn {index} result sample: {_compact(turn['result_sample'], 1200)}")
    elif context.get("is_followup"):
        lines.append(f"Previous request: {context.get('previous_prompt', '')}")
        if context.get("previous_sql"):
            lines.append(f"Previous SQL: {context['previous_sql']}")
        if context.get("previous_summary"):
            lines.append(f"Previous answer: {context['previous_summary']}")
    if not recent_turns and not context.get("is_followup"):
        lines.append("No prior grounded turns are available.")
    return "\n".join(lines)
