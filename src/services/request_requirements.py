"""Deterministic extraction of explicitly requested visual artifacts."""
from __future__ import annotations

import re


def requested_visualizations_from_prompt(prompt: str) -> list[str]:
    """Return every visualization type explicitly named by the user."""
    text = prompt.lower()
    patterns = (
        (r"\bline\s+(?:chart|graph|plot)\b", "line_chart"),
        (r"\bbar\s+(?:chart|graph|plot)\b", "bar_chart"),
        (r"\bpie\s+(?:chart|graph|plot)\b", "pie_chart"),
        (r"\bscatter(?:\s*plot|\s*chart)?\b", "scatter_chart"),
        (r"\b(?:er|entity[- ]relationship)\s+(?:diagram|model)\b", "er_diagram"),
        (r"\b(?:process|workflow)\s+(?:flow|diagram|chart)\b", "process_flow"),
        (r"\bdecision\s+(?:tree|diagram)\b", "decision_tree"),
    )
    return [artifact for pattern, artifact in patterns if re.search(pattern, text)]


def previous_visualizations_from_context(context: dict) -> list[str]:
    """Translate delivered chart/diagram metadata back into planner artifact names."""
    chart_types = context.get("previous_chart_types") or (
        [context["previous_chart_type"]] if context.get("previous_chart_type") else []
    )
    diagram_map = {
        "er": "er_diagram",
        "process": "process_flow",
        "decision": "decision_tree",
    }
    artifacts = [
        f"{chart_type}_chart" for chart_type in chart_types
        if chart_type in {"bar", "line", "pie", "scatter"}
    ]
    artifacts.extend(
        diagram_map[diagram_type]
        for diagram_type in context.get("previous_diagram_types", [])
        if diagram_type in diagram_map
    )
    return list(dict.fromkeys(artifacts))


def resolve_followup_visualizations(
    prompt: str,
    conversation_context: dict,
    planned_visualizations: list[str],
) -> list[str]:
    """Keep delivered artifacts stable until the user explicitly changes them."""
    explicit = requested_visualizations_from_prompt(prompt)
    if conversation_context.get("followup_kind") != "data":
        return list(dict.fromkeys(planned_visualizations + explicit))

    previous = previous_visualizations_from_context(conversation_context)
    preserve_all = bool(re.search(
        r"\b(?:keep|retain|preserve)\s+(?:all|every|the same|previous)\s+"
        r"(?:previous\s+)?"
        r"(?:output|outputs|chart|charts|visualization|visualizations|diagram|diagrams)\b",
        prompt.lower(),
    ))
    if explicit:
        return list(dict.fromkeys((previous if preserve_all else []) + explicit))
    if previous:
        return previous
    return list(dict.fromkeys(planned_visualizations))
