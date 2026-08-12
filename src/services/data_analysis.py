"""Deterministic analytics over tabular query results.

This module deliberately contains no LLM calls.  It computes the facts that
the narrative layer is allowed to describe, so totals, trends, outliers, and
data-quality observations remain grounded in the returned dataset.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from statistics import mean
from typing import Any


_TIME_HINTS = ("date", "time", "month", "year", "week", "day", "quarter")
_ID_HINTS = ("id", "uuid", "code", "number")
_ALLOWED_ANALYSES = {"summary", "trend", "outliers", "quality", "contributors"}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _finite_float(value: Any) -> float | None:
    if not _is_number(value):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _percent_change(first: float, last: float) -> float | None:
    if first == 0:
        return None
    return round(((last - first) / abs(first)) * 100, 2)


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def analyze_rows(
    raw_data: list[dict[str, Any]],
    analysis_types: list[str] | None = None,
) -> dict[str, Any]:
    """Return deterministic metrics, trends, outliers, and quality findings."""
    requested = set(analysis_types or _ALLOWED_ANALYSES) & _ALLOWED_ANALYSES
    if not raw_data:
        return {
            "row_count": 0,
            "column_count": 0,
            "numeric_summary": {},
            "trend": None,
            "top_contributors": [],
            "outliers": [],
            "data_quality": {"null_cells": 0, "duplicate_rows": 0, "notes": ["No rows returned."]},
            "recommended_chart": "table",
        }

    columns = list(dict.fromkeys(key for row in raw_data for key in row))
    numeric_columns = [
        column for column in columns
        if any(_finite_float(row.get(column)) is not None for row in raw_data)
    ]
    category_columns = [
        column for column in columns
        if column not in numeric_columns
        and any(row.get(column) is not None for row in raw_data)
    ]
    time_column = next(
        (column for column in columns if any(hint in column.lower() for hint in _TIME_HINTS)),
        None,
    )
    measure_columns = [
        column for column in numeric_columns
        if not any(hint == column.lower() or column.lower().endswith(f"_{hint}") for hint in _ID_HINTS)
    ] or numeric_columns

    numeric_summary: dict[str, dict[str, float | int]] = {}
    if "summary" in requested:
        for column in measure_columns:
            values = [value for row in raw_data if (value := _finite_float(row.get(column))) is not None]
            if values:
                numeric_summary[column] = {
                    "count": len(values),
                    "sum": round(sum(values), 4),
                    "average": round(mean(values), 4),
                    "minimum": round(min(values), 4),
                    "maximum": round(max(values), 4),
                }

    trend: dict[str, Any] | None = None
    if "trend" in requested and time_column and measure_columns:
        measure = measure_columns[0]
        points = [
            {"period": _jsonable(row.get(time_column)), "value": value}
            for row in raw_data
            if row.get(time_column) is not None
            and (value := _finite_float(row.get(measure))) is not None
        ]
        if len(points) >= 2:
            first_value = points[0]["value"]
            last_value = points[-1]["value"]
            change = round(last_value - first_value, 4)
            trend = {
                "dimension": time_column,
                "measure": measure,
                "first": points[0],
                "last": points[-1],
                "absolute_change": change,
                "percent_change": _percent_change(first_value, last_value),
                "direction": "up" if change > 0 else "down" if change < 0 else "flat",
            }

    outliers: list[dict[str, Any]] = []
    if "outliers" in requested:
        for column in measure_columns:
            indexed_values = [
                (index, value)
                for index, row in enumerate(raw_data)
                if (value := _finite_float(row.get(column))) is not None
            ]
            if len(indexed_values) < 4:
                continue
            sorted_values = sorted(value for _, value in indexed_values)
            q1 = _percentile(sorted_values, 0.25)
            q3 = _percentile(sorted_values, 0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            for index, value in indexed_values:
                if value < lower or value > upper:
                    label_column = time_column or (category_columns[0] if category_columns else None)
                    outliers.append({
                        "column": column,
                        "value": value,
                        "row": index,
                        "label": _jsonable(raw_data[index].get(label_column)) if label_column else index + 1,
                        "direction": "low" if value < lower else "high",
                    })
        outliers = outliers[:20]

    top_contributors: list[dict[str, Any]] = []
    if "contributors" in requested and category_columns and measure_columns:
        category, measure = category_columns[0], measure_columns[0]
        candidates = [
            {"label": _jsonable(row.get(category)), "value": value}
            for row in raw_data
            if row.get(category) is not None
            and (value := _finite_float(row.get(measure))) is not None
        ]
        candidates.sort(key=lambda item: item["value"], reverse=True)
        top_contributors = candidates[:5]

    null_by_column = {
        column: sum(1 for row in raw_data if row.get(column) is None)
        for column in columns
    }
    null_by_column = {column: count for column, count in null_by_column.items() if count}
    fingerprints = [tuple((column, repr(row.get(column))) for column in columns) for row in raw_data]
    duplicate_rows = sum(count - 1 for count in Counter(fingerprints).values() if count > 1)
    notes: list[str] = []
    if null_by_column:
        notes.append(f"Missing values found in {len(null_by_column)} column(s).")
    if duplicate_rows:
        notes.append(f"Found {duplicate_rows} duplicate row(s).")
    if not notes:
        notes.append("No missing values or duplicate rows detected in the returned data.")

    if time_column and measure_columns:
        recommended_chart = "line"
    elif len(measure_columns) >= 2:
        recommended_chart = "scatter"
    elif category_columns and measure_columns and len(raw_data) <= 8:
        recommended_chart = "pie"
    elif category_columns and measure_columns:
        recommended_chart = "bar"
    else:
        recommended_chart = "table"

    return {
        "row_count": len(raw_data),
        "column_count": len(columns),
        "numeric_summary": numeric_summary,
        "trend": trend,
        "top_contributors": top_contributors,
        "outliers": outliers,
        "data_quality": {
            "null_cells": sum(null_by_column.values()),
            "nulls_by_column": null_by_column,
            "duplicate_rows": duplicate_rows,
            "notes": notes,
        },
        "recommended_chart": recommended_chart,
    }
