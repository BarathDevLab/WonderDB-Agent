from services.request_requirements import (
    is_schema_visualization_request,
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


def test_temporal_regroup_uses_line_chart_even_after_previous_bar() -> None:
    result = resolve_followup_visualizations(
        "Show the same data grouped by date",
        {
            "followup_kind": "data",
            "previous_chart_types": ["bar"],
            "previous_diagram_types": ["er"],
        },
        ["bar_chart"],
    )

    assert result == ["line_chart", "er_diagram"]


def test_schema_flow_language_is_detected_without_the_word_process() -> None:
    assert requested_visualizations_from_prompt(
        "Show a flow diagram of the actual schema",
    ) == ["process_flow"]


def test_schema_and_process_flow_requests_both_diagrams_deterministically() -> None:
    prompt = "Show the actual schema and process flow"

    assert requested_visualizations_from_prompt(prompt) == [
        "er_diagram",
        "process_flow",
    ]
    assert is_schema_visualization_request(prompt) is True


def test_schema_diagram_with_data_analysis_remains_a_query() -> None:
    prompt = "Show revenue trends and include the database schema diagram"

    assert is_schema_visualization_request(prompt) is False


def test_er_and_process_flow_without_schema_word_is_schema_only() -> None:
    prompt = "Generate an ER diagram and process flow"

    assert requested_visualizations_from_prompt(prompt) == [
        "er_diagram",
        "process_flow",
    ]
    assert is_schema_visualization_request(prompt) is True


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
