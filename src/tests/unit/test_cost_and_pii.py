from core.cost_evaluator import evaluate_cost
from core.pii_redactor import is_sensitive_column, redact_rows


def test_cost_evaluator_numerical_threshold() -> None:
    eval_ok = evaluate_cost(500.0, threshold=10000.0)
    assert eval_ok.within_threshold is True
    assert eval_ok.total_cost == 500.0

    eval_high = evaluate_cost(15000.0, threshold=10000.0)
    assert eval_high.within_threshold is False
    assert "exceeds threshold" in eval_high.reason


def test_cost_evaluator_explain_plan_inspection() -> None:
    plan_json = [
        {
            "Plan": {
                "Node Type": "Seq Scan",
                "Total Cost": 1200.0,
                "Plan Rows": 50000,
                "Relation Name": "orders",
            }
        }
    ]

    eval_result = evaluate_cost(plan_json, threshold=10000.0, scan_threshold_rows=1000)
    assert eval_result.has_unindexed_seq_scan is True
    assert eval_result.within_threshold is False
    assert "Unindexed sequential scan" in eval_result.reason


def test_pii_redactor_masks_sensitive_fields() -> None:
    data = [
        {"id": "1", "full_name": "John Doe", "email": "john@example.com", "ssn": "000-11-2222"},
        {"id": "2", "full_name": "Jane Smith", "email": "jane@example.com", "ssn": "333-44-5555"},
    ]

    redacted = redact_rows(data)

    assert redacted[0]["id"] == "1"
    assert redacted[0]["full_name"] == "John Doe"
    assert redacted[0]["email"] == "***"
    assert redacted[0]["ssn"] == "***"


def test_is_sensitive_column_matching() -> None:
    assert is_sensitive_column("customer_email") is True
    assert is_sensitive_column("user_password_hash") is True
    assert is_sensitive_column("order_total") is False
    assert is_sensitive_column("custom_secret_field", explicit_pii_columns={"custom_secret_field"}) is True
