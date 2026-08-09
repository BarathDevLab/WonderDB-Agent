import re
from typing import Any

DEFAULT_PII_PATTERNS = {
    "email", "ssn", "social_security", "social_security_number",
    "password", "passwd", "secret", "token", "api_key",
    "credit_card", "card_number", "cc_number", "cvv", "cvc",
    "phone", "phone_number", "mobile", "cell", "telephone",
    "tax_id", "tin", "ein", "salary", "wage", "compensation",
    "date_of_birth", "dob", "birth_date",
    "address", "street_address", "home_address", "mailing_address",
    "passport", "passport_number",
    "national_id", "national_insurance", "nino",
    "iban", "swift", "swift_code", "bank_account", "account_number", "routing_number",
    "license", "license_number", "drivers_license",
    "zipcode", "zip_code", "postal_code",
}

# Content-level regex patterns for data value inspection
_CONTENT_PII_PATTERNS = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("phone", re.compile(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b")),
]


def is_sensitive_column(column_name: str, explicit_pii_columns: set[str] | None = None) -> bool:
    """Check whether a column name matches explicit or default PII rules."""
    normalized = column_name.strip().lower()
    if explicit_pii_columns and (column_name in explicit_pii_columns or normalized in explicit_pii_columns):
        return True
    return any(pattern in normalized for pattern in DEFAULT_PII_PATTERNS)


def _contains_pii_content(value: Any) -> bool:
    """Inspect actual data value for PII patterns using regex."""
    if not isinstance(value, str) or len(value) < 5:
        return False
    for _, pattern in _CONTENT_PII_PATTERNS:
        if pattern.search(value):
            return True
    return False


def redact_rows(
    rows: list[dict[str, Any]],
    pii_columns: set[str] | None = None,
    mask: str = "***",
) -> list[dict[str, Any]]:
    """Mask configured or detected PII columns and content-level PII in result rows."""
    if not rows:
        return []

    redacted: list[dict[str, Any]] = []
    for row in rows:
        redacted_row: dict[str, Any] = {}
        for k, v in row.items():
            if is_sensitive_column(k, pii_columns):
                redacted_row[k] = mask
            elif _contains_pii_content(v):
                redacted_row[k] = mask
            else:
                redacted_row[k] = v
        redacted.append(redacted_row)
    return redacted
