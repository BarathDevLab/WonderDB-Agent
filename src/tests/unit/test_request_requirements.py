from services.request_requirements import (
    requested_visualizations_from_prompt,
    resolve_followup_visualizations,
)


def test_extracts_all_explicit_visualizations_without_a_cap() -> None:
    prompt = (
        "Create a line chart, bar chart, pie chart, scatter plot, "
        "ER diagram, process flow, and decision tree."
    )

    assert requested_visualizations_from_prompt(prompt) == [
        "line_chart",
        "bar_chart",
        "pie_chart",
        "scatter_chart",
        "er_diagram",
        "process_flow",
        "decision_tree",
    ]


def test_data_followup_inherits_previous_line_chart() -> None:
    result = resolve_followup_visualizations(
        "Show the same data grouped by product",
        {
            "followup_kind": "data",
            "previous_chart_type": "line",
            "previous_diagram_types": [],
        },
        ["bar_chart"],
    )

    assert result == ["line_chart"]


def test_explicit_chart_change_replaces_previous_chart() -> None:
    result = resolve_followup_visualizations(
        "Change it to a bar chart",
        {
            "followup_kind": "data",
            "previous_chart_types": ["line"],
            "previous_diagram_types": [],
        },
        ["line_chart", "bar_chart"],
    )

    assert result == ["bar_chart"]


def test_keep_all_outputs_preserves_previous_and_adds_explicit() -> None:
    result = resolve_followup_visualizations(
        "Keep all previous outputs and add a scatter plot",
        {
            "followup_kind": "data",
            "previous_chart_types": ["line", "pie"],
            "previous_diagram_types": ["er"],
        },
        ["scatter_chart"],
    )

    assert result == ["line_chart", "pie_chart", "er_diagram", "scatter_chart"]
