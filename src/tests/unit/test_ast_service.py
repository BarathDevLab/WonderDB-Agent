import pytest

from services.ast_service import ASTService


@pytest.mark.parametrize(
    "query",
    [
        "INSERT INTO users(id) VALUES (1)",
        "UPDATE users SET name = 'x'",
        "DELETE FROM users",
        "SELECT * FROM users; SELECT * FROM tenants",
    ],
)
def test_ast_service_rejects_dml_and_multi_statement(query: str) -> None:
    service = ASTService()

    with pytest.raises(ValueError):
        service.validate_select_query(query)


def test_ast_service_accepts_single_select() -> None:
    service = ASTService()

    result = service.validate_select_query("SELECT id, name FROM users")

    assert result.is_valid is True
    assert result.sql == "SELECT id, name FROM users"
