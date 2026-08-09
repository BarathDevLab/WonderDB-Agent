from typing import Any

DEFAULT_PII_PATTERNS = {
    "email",
    "ssn",
    "social_security",
    "password",
    "credit_card",
    "card_number",
    "phone",
    "phone_number",
    "secret",
    "token",
    "tax_id",
    "salary",
}


def is_sensitive_column(column_name: str, explicit_pii_columns: set[str] | None = None) -> bool:
    """Check whether a column name matches explicit or default PII rules."""
    normalized = column_name.strip().lower()
    if explicit_pii_columns and (column_name in explicit_pii_columns or normalized in explicit_pii_columns):
        return True
    return any(pattern in normalized for pattern in DEFAULT_PII_PATTERNS)


def redact_rows(
    rows: list[dict[str, Any]],
    pii_columns: set[str] | None = None,
    mask: str = "***",
) -> list[dict[str, Any]]:
    """Mask configured or detected PII columns in result rows."""
    if not rows:
        return []

    redacted: list[dict[str, Any]] = []
    for row in rows:
        redacted_row: dict[str, Any] = {}
        for k, v in row.items():
            if is_sensitive_column(k, pii_columns):
                redacted_row[k] = mask
            else:
                redacted_row[k] = v
        redacted.append(redacted_row)
    return redacted
