from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp


class SQLValidationError(ValueError):
    """Raised when an SQL statement violates the read-only contract."""


@dataclass(frozen=True)
class ValidatedSQL:
    normalized_sql: str
    referenced_tables: tuple[str, ...]


BLOCKED_NODE_KEYS = {
    "alter",
    "attach",
    "command",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "grant",
    "insert",
    "load_data",
    "merge",
    "pragma",
    "revoke",
    "set",
    "transaction",
    "truncate",
    "update",
    "use",
}

BLOCKED_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_json",
    "read_json_auto",
    "read_parquet",
    "sqlite_scan",
    "postgres_scan",
    "mysql_scan",
    "httpfs",
}


def validate_read_only_sql(sql: str, allowed_tables: set[str]) -> ValidatedSQL:
    if not sql or not sql.strip():
        raise SQLValidationError("SQL must not be empty.")

    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as exc:
        raise SQLValidationError(f"SQL parse failed: {exc}") from exc

    if len(statements) != 1:
        raise SQLValidationError("Exactly one SQL statement is allowed.")

    tree = statements[0]
    if tree.find(exp.Select) is None:
        raise SQLValidationError("Only SELECT queries are allowed.")

    for node in tree.walk():
        if node.key.lower() in BLOCKED_NODE_KEYS:
            raise SQLValidationError(f"Blocked SQL operation: {node.key}.")

    for function in tree.find_all(exp.Func):
        # SQLGlot represents DuckDB table functions such as read_csv_auto()
        # as Anonymous functions. sql_name() then returns "ANONYMOUS", so the
        # actual parsed function name must be read from .name.
        if isinstance(function, exp.Anonymous):
            function_name = function.name.lower()
        else:
            function_name = function.sql_name().lower()
        if function_name in BLOCKED_FUNCTIONS:
            raise SQLValidationError(f"External data function is blocked: {function_name}.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    referenced = {
        table.name.lower()
        for table in tree.find_all(exp.Table)
        if table.name and table.name.lower() not in cte_names
    }
    allowed = {table.lower() for table in allowed_tables}
    unapproved = referenced - allowed
    if unapproved:
        raise SQLValidationError(f"Unapproved tables: {sorted(unapproved)}.")

    return ValidatedSQL(
        normalized_sql=tree.sql(dialect="duckdb", pretty=True),
        referenced_tables=tuple(sorted(referenced)),
    )

