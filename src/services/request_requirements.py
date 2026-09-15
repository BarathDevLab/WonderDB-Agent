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
        (
            r"\b(?:(?:er|entity[- ]relationship)\s+(?:diagram|model)|"
            r"er(?=\s*(?:and|plus|with)\b)|"
            r"(?:database\s+)?schema\s+(?:diagram|map|visuali[sz]ation)|"
            r"schema\s+(?:and|plus|with)\s+(?:the\s+)?(?:process|workflow|data)\s+flow|"
            r"(?:show|draw|generate|create|display|give)\s+(?:me\s+)?(?:the\s+)?"
            r"(?:database\s+)?schema)\b",
            "er_diagram",
        ),
        (
            r"\b(?:(?:process|workflow)\s+(?:flow|diagram|chart)|"
            r"(?:schema|database|data)\s+flow(?:chart|\s+diagram)?|flow\s+diagram)\b",
            "process_flow",
        ),
        (r"\bdecision\s+(?:tree|diagram)\b", "decision_tree"),
    )
    return [artifact for pattern, artifact in patterns if re.search(pattern, text)]


def is_schema_visualization_request(prompt: str) -> bool:
    """Recognize schema-only diagram requests without relying on the LLM planner."""
    text = prompt.lower()
    requested = set(requested_visualizations_from_prompt(prompt))
    if not requested:
        return False
    if not requested.issubset({"er_diagram", "process_flow"}):
        return False
    if "schema" not in text and "er_diagram" not in requested:
        return False
    data_analysis_terms = re.search(
        r"\b(?:revenue|sales|trend|average|total|count|top|bottom|growth|decline|"
        r"compare|distribution|forecast|outlier|performance|metric)\b",
        text,
    )
    return data_analysis_terms is None


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
    temporal_regroup = bool(re.search(
        r"\b(?:group|grouped|aggregate|aggregated|summari[sz]e|summari[sz]ed)\s+"
        r"(?:it|this|that|the\s+(?:same\s+)?data)?\s*by\s+"
        r"(?:date|time|day|week|month|quarter|year)\b",
        prompt.lower(),
    ))
    if temporal_regroup:
        non_charts = [artifact for artifact in previous if not artifact.endswith("_chart")]
        return ["line_chart", *non_charts]
    if previous:
        return previous
    return list(dict.fromkeys(planned_visualizations))
