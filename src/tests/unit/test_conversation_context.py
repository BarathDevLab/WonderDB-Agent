from services.conversation_context import (
    build_conversation_context,
    format_context_for_model,
)


def _summary(prompt: str, sql: str, summary: str) -> dict:
    return {
        "phase": "summary",
        "prompt": prompt,
        "sql_query": sql,
        "summary": summary,
        "rows_count": 3,
    }


def test_data_followup_resolves_previous_request_and_sql() -> None:
    context = build_conversation_context(
        [_summary(
            "Show monthly revenue for 2025",
            "SELECT month, SUM(revenue) FROM orders WHERE year = 2025 GROUP BY month",
            "Revenue peaked in December.",
        )],
        "Show the same by product for this year as a bar chart",
    )

    assert context["is_followup"] is True
    assert context["followup_kind"] == "data"
    assert "Previous user request: Show monthly revenue for 2025" in context["resolved_prompt"]
    assert "CURRENT USER REQUEST" in context["resolved_prompt"]
    assert "this year as a bar chart" in context["resolved_prompt"]


def test_explanation_followup_does_not_request_new_sql() -> None:
    context = build_conversation_context(
        [_summary("Show churn by region", "SELECT region, churn FROM customers", "West is highest.")],
        "Explain that in simpler terms",
    )

    assert context["is_followup"] is True
    assert context["followup_kind"] == "explanation"


def test_independent_question_is_not_merged_with_previous_turn() -> None:
    context = build_conversation_context(
        [_summary("Show revenue", "SELECT SUM(revenue) FROM orders", "Revenue is 100.")],
        "List customers with overdue invoices",
    )

    assert context["is_followup"] is False
    assert context["resolved_prompt"] == "List customers with overdue invoices"


def test_model_context_contains_last_three_distinct_grounded_turns() -> None:
    history = [
        _summary("Question one", "SELECT 1", "Answer one"),
        _summary("Question two", "SELECT 2", "Answer two"),
        _summary("Question three", "SELECT 3", "Answer three"),
        _summary("Question four", "SELECT 4", "Answer four"),
    ]
    context = build_conversation_context(history, "Compare that with the previous year")
    formatted = format_context_for_model(context)

    assert "Question one" not in formatted
    assert "Question two" in formatted
    assert "Question three" in formatted
    assert "Question four" in formatted
    assert formatted.index("Question two") < formatted.index("Question four")


def test_subjectless_chart_request_uses_previous_query_context() -> None:
    context = build_conversation_context(
        [_summary("Show orders by status", "SELECT status, COUNT(*) FROM orders", "Three statuses.")],
        "Make a pie chart",
    )

    assert context["is_followup"] is True
    assert context["followup_kind"] == "data"
    assert "Show orders by status" in context["resolved_prompt"]


def test_implicit_elliptical_question_uses_previous_result() -> None:
    context = build_conversation_context(
        [_summary("Compare quarterly product growth", "SELECT product, growth FROM sales", "A led growth.")],
        "Which one had the highest growth?",
    )

    assert context["is_followup"] is True
    assert context["followup_kind"] == "data"
