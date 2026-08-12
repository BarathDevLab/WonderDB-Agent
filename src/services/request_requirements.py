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
