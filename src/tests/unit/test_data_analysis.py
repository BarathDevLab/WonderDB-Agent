from services.data_analysis import analyze_rows


def test_analyze_rows_computes_summary_trend_and_recommendation() -> None:
    result = analyze_rows([
        {"month": "2026-01", "revenue": 100.0},
        {"month": "2026-02", "revenue": 125.0},
        {"month": "2026-03", "revenue": 150.0},
    ])

    assert result["numeric_summary"]["revenue"]["sum"] == 375.0
    assert result["numeric_summary"]["revenue"]["average"] == 125.0
    assert result["trend"]["percent_change"] == 50.0
    assert result["trend"]["direction"] == "up"
    assert result["recommended_chart"] == "line"


def test_analyze_rows_detects_quality_issues_and_outlier() -> None:
    result = analyze_rows([
        {"category": "A", "amount": 10},
        {"category": "B", "amount": 10},
        {"category": "C", "amount": 11},
        {"category": "D", "amount": 1000},
        {"category": None, "amount": 10},
        {"category": "A", "amount": 10},
    ])

    assert result["data_quality"]["null_cells"] == 1
    assert result["data_quality"]["duplicate_rows"] == 1
    assert any(item["value"] == 1000 for item in result["outliers"])
    assert result["top_contributors"][0] == {"label": "D", "value": 1000.0}


def test_analyze_rows_handles_empty_data() -> None:
    result = analyze_rows([])

    assert result["row_count"] == 0
    assert result["recommended_chart"] == "table"
    assert result["data_quality"]["notes"] == ["No rows returned."]
