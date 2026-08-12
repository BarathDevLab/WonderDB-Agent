from services.request_requirements import requested_visualizations_from_prompt


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
