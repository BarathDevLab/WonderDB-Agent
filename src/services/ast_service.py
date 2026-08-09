from pydantic import BaseModel
from sqlglot import exp, parse
from sqlglot.errors import ParseError


class ASTValidationResult(BaseModel):
    sql: str
    is_valid: bool


class ASTService:
    """Validate SQL is a single safe SELECT statement."""

    _DISALLOWED_NODES: tuple[type[exp.Expression], ...] = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.TruncateTable,
        exp.Merge,
        exp.Command,
        exp.Copy,
    )

    def __init__(self, dialect: str | None = None) -> None:
        self._dialect = dialect

    def validate_select_query(self, raw_sql: str) -> ASTValidationResult:
        sql = raw_sql.strip()
        if not sql:
            raise ValueError("SQL query cannot be empty.")

        try:
            statements = parse(sql, read=self._dialect)
        except ParseError as exc:
            raise ValueError(f"Invalid SQL syntax: {exc}") from exc

        if len(statements) != 1:
            raise ValueError("Multi-statement SQL is not allowed.")

        root = statements[0]
        if not isinstance(root, exp.Select):
            raise ValueError("Only SELECT statements are allowed.")

        for node_type in self._DISALLOWED_NODES:
            if root.find(node_type) is not None:
                raise ValueError(f"Disallowed SQL operation detected: {node_type.__name__}.")

        # Additional safety checks for PostgreSQL-specific constructs
        sql_upper = sql.upper()
        if any(keyword in sql_upper for keyword in ('INTO ', 'GRANT ', 'REVOKE ', 'SET ROLE', 'VACUUM', 'COPY ')):
            raise ValueError("Disallowed SQL construct detected.")

        return ASTValidationResult(sql=sql, is_valid=True)
