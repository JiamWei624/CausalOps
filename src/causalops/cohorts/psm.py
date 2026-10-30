from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb
import pandas as pd

from causalops.sql import validate_read_only_sql


@dataclass(frozen=True)
class PSMCohortSummary:
    index_date: str
    row_count: int
    treated_count: int
    control_count: int
    pre_period_days: int
    followup_days: int
    output_path: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def build_common_date_psm_cohort(
    database_path: Path,
    source_table: str,
    output_path: Path,
    *,
    pre_period_days: int = 28,
    followup_days: int = 28,
) -> tuple[pd.DataFrame, PSMCohortSummary, str]:
    """Build one pre-treatment row per user for a common treatment-date design.

    The source database is always opened read-only. Staggered adoption is rejected
    because assigning a single index date to never-treated controls would otherwise
    create an invalid risk set.
    """

    table = _identifier(source_table)
    if pre_period_days < 1 or followup_days < 1:
        raise ValueError("PSM pre and follow-up windows must be positive")
    database_path = database_path.resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"DuckDB database does not exist: {database_path}")

    timing_sql = f"""
        SELECT
            COUNT(DISTINCT first_ai_reply_date) FILTER (WHERE first_ai_reply_date IS NOT NULL)
                AS treatment_date_count,
            MIN(first_ai_reply_date) FILTER (WHERE first_ai_reply_date IS NOT NULL)
                AS index_date
        FROM "{table}"
    """
    validated_timing = validate_read_only_sql(timing_sql, {table})
    with duckdb.connect(str(database_path), read_only=True) as connection:
        treatment_date_count, index_date = connection.execute(
            validated_timing.normalized_sql
        ).fetchone()
        if not treatment_date_count:
            raise ValueError("No treated users with an observed treatment date")
        if treatment_date_count != 1:
            raise ValueError(
                "Common-date PSM requires exactly one treatment date; "
                "use risk-set matching for staggered adoption"
            )

        cohort_sql = f"""
            WITH user_level AS (
                SELECT
                    user_id,
                    MIN(registration_date) AS registration_date,
                    MAX(baseline_activity) AS baseline_activity,
                    MAX(ai_eligible) AS ai_eligible,
                    MAX(first_ai_reply_date) AS first_ai_reply_date
                FROM "{table}"
                GROUP BY user_id
            ),
            cohort AS (
                SELECT
                    u.user_id,
                    CAST(u.first_ai_reply_date IS NOT NULL AS UTINYINT) AS treated,
                    DATE '{index_date}' AS index_date,
                    DATE_DIFF('day', u.registration_date, DATE '{index_date}')
                        AS registration_age_days,
                    u.baseline_activity,
                    u.ai_eligible,
                    COUNT(DISTINCT r.event_date) FILTER (
                        WHERE r.event_date BETWEEN DATE '{index_date}' - INTERVAL '{pre_period_days} days'
                                               AND DATE '{index_date}' - INTERVAL '1 day'
                    ) AS observed_pre_days,
                    COUNT(DISTINCT r.event_date) FILTER (
                        WHERE r.event_date BETWEEN DATE '{index_date}'
                                               AND DATE '{index_date}' + INTERVAL '{followup_days - 1} days'
                    ) AS observed_followup_days,
                    SUM(r.is_active) FILTER (
                        WHERE r.event_date BETWEEN DATE '{index_date}' - INTERVAL '{pre_period_days} days'
                                               AND DATE '{index_date}' - INTERVAL '1 day'
                    ) AS pre_active_days,
                    SUM(r.post_count) FILTER (
                        WHERE r.event_date BETWEEN DATE '{index_date}' - INTERVAL '{pre_period_days} days'
                                               AND DATE '{index_date}' - INTERVAL '1 day'
                    ) AS pre_post_count,
                    SUM(r.comment_count) FILTER (
                        WHERE r.event_date BETWEEN DATE '{index_date}' - INTERVAL '{pre_period_days} days'
                                               AND DATE '{index_date}' - INTERVAL '1 day'
                    ) AS pre_comment_count,
                    SUM(r.like_count) FILTER (
                        WHERE r.event_date BETWEEN DATE '{index_date}' - INTERVAL '{pre_period_days} days'
                                               AND DATE '{index_date}' - INTERVAL '1 day'
                    ) AS pre_like_count,
                    SUM(r.repost_count) FILTER (
                        WHERE r.event_date BETWEEN DATE '{index_date}' - INTERVAL '{pre_period_days} days'
                                               AND DATE '{index_date}' - INTERVAL '1 day'
                    ) AS pre_repost_count,
                    SUM(r.total_interactions) FILTER (
                        WHERE r.event_date BETWEEN DATE '{index_date}' - INTERVAL '{pre_period_days} days'
                                               AND DATE '{index_date}' - INTERVAL '1 day'
                    ) AS pre_total_interactions,
                    SUM(r.total_interactions) FILTER (
                        WHERE r.event_date BETWEEN DATE '{index_date}'
                                               AND DATE '{index_date}' + INTERVAL '{followup_days - 1} days'
                    ) AS post_total_interactions
                FROM user_level u
                JOIN "{table}" r USING (user_id)
                GROUP BY
                    u.user_id, u.first_ai_reply_date, u.registration_date,
                    u.baseline_activity, u.ai_eligible
            )
            SELECT *
            FROM cohort
            WHERE observed_pre_days = {pre_period_days}
              AND observed_followup_days = {followup_days}
            ORDER BY user_id
        """
        validated_cohort = validate_read_only_sql(cohort_sql, {table})
        cohort = connection.execute(validated_cohort.normalized_sql).df()

    if cohort.empty:
        raise ValueError("No users have complete pre-treatment and follow-up windows")
    if cohort["treated"].nunique() != 2:
        raise ValueError("PSM cohort must contain treated and control users")
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cohort.to_parquet(output_path, index=False, compression="zstd")
    summary = PSMCohortSummary(
        index_date=str(index_date),
        row_count=len(cohort),
        treated_count=int(cohort["treated"].sum()),
        control_count=int((cohort["treated"] == 0).sum()),
        pre_period_days=pre_period_days,
        followup_days=followup_days,
        output_path=str(output_path),
    )
    return cohort, summary, validated_cohort.normalized_sql
