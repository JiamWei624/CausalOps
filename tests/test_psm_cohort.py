from pathlib import Path

import duckdb
import pandas as pd

from causalops.cohorts import build_common_date_psm_cohort


def test_common_date_cohort_is_one_row_per_user_and_uses_only_pre_features(tmp_path: Path) -> None:
    database = tmp_path / "source.duckdb"
    output = tmp_path / "cohort.parquet"
    dates = pd.date_range("2025-01-01", periods=20, freq="D")
    treatment_date = dates[10]
    rows = []
    for user in range(12):
        treated = user < 4
        for day, date in enumerate(dates):
            rows.append(
                {
                    "user_id": f"u{user:03d}",
                    "event_date": date,
                    "registration_date": dates[0] - pd.Timedelta(days=30 + user),
                    "baseline_activity": 0.5 + user / 20,
                    "ai_eligible": int(user < 8),
                    "first_ai_reply_date": treatment_date if treated else pd.NaT,
                    "post_count": int(day % 4 == 0),
                    "comment_count": int(day % 3 == 0),
                    "like_count": int(day % 2 == 0),
                    "repost_count": 0,
                    "total_interactions": int(day % 4 == 0) + int(day % 3 == 0) + int(day % 2 == 0),
                    "is_active": 1,
                }
            )
    with duckdb.connect(str(database)) as connection:
        connection.register("source_frame", pd.DataFrame(rows))
        connection.execute("CREATE TABLE raw_daily_activity AS SELECT * FROM source_frame")
    cohort, summary, sql = build_common_date_psm_cohort(
        database, "raw_daily_activity", output, pre_period_days=7, followup_days=7
    )
    assert len(cohort) == 12
    assert cohort["user_id"].is_unique
    assert summary.treated_count == 4
    assert summary.control_count == 8
    assert (cohort["observed_pre_days"] == 7).all()
    assert (cohort["observed_followup_days"] == 7).all()
    assert "SELECT" in sql
    assert output.is_file()
