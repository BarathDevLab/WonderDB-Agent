from services.ast_service import ASTService, ASTValidationResult


def validate_sql(sql: str) -> ASTValidationResult:
    """Thin wrapper around ASTService for central validation hooks."""

    return ASTService().validate_select_query(sql)
