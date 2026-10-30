import pytest

from causalops.sql import SQLValidationError, validate_read_only_sql


def test_allows_select_from_approved_table() -> None:
    result = validate_read_only_sql(
        "SELECT user_id, SUM(total_interactions) AS interactions FROM user_daily_activity GROUP BY user_id",
        {"user_daily_activity"},
    )
    assert result.referenced_tables == ("user_daily_activity",)
    assert "SELECT" in result.normalized_sql


def test_allows_cte_but_checks_base_table() -> None:
    result = validate_read_only_sql(
        "WITH base AS (SELECT * FROM user_daily_activity) SELECT COUNT(*) FROM base",
        {"user_daily_activity"},
    )
    assert result.referenced_tables == ("user_daily_activity",)


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM user_daily_activity",
        "UPDATE user_daily_activity SET is_active = 0",
        "DROP TABLE user_daily_activity",
        "SELECT * FROM user_daily_activity; SELECT 1",
        "SELECT * FROM read_csv_auto('private.csv')",
        "SELECT * FROM secret_table",
    ],
)
def test_blocks_unsafe_or_unapproved_sql(query: str) -> None:
    with pytest.raises(SQLValidationError):
        validate_read_only_sql(query, {"user_daily_activity"})

