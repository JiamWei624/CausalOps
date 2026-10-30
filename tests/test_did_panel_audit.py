from __future__ import annotations

import pandas as pd

from causalops.audits import AuditStatus, audit_did_panel
from causalops.demo_data import get_demo_scenarios


def _did_scenario():
    return get_demo_scenarios()["DID：AI回复与后续互动"]


def test_complete_demo_panel_is_audited_without_estimating_or_mutating() -> None:
    scenario = _did_scenario()
    frame = scenario.frame.copy(deep=True)
    original = frame.copy(deep=True)
    original_spec = scenario.spec.model_copy(deep=True)

    report = audit_did_panel(frame, scenario.spec)

    assert report.overall_status == AuditStatus.REVIEW
    assert report.user_count == 160
    assert report.treated_user_count == 80
    assert report.never_treated_user_count == 80
    assert report.complete_pre_window_users == 80
    assert report.complete_post_window_users == 80
    assert report.pre_outcome_complete_users == 80
    assert report.duplicate_user_time_rows == 0
    assert [item["relative_day"] for item in report.relative_day_coverage] == list(range(-7, 6))
    pd.testing.assert_frame_equal(frame, original)
    assert scenario.spec == original_spec


def test_duplicate_user_day_blocks_audit() -> None:
    scenario = _did_scenario()
    duplicated = pd.concat([scenario.frame, scenario.frame.iloc[[0]]], ignore_index=True)

    report = audit_did_panel(duplicated, scenario.spec)

    assert report.overall_status == AuditStatus.BLOCK
    uniqueness = next(item for item in report.checks if item.code == "user_time_uniqueness")
    assert uniqueness.status == AuditStatus.BLOCK
    assert uniqueness.evidence["duplicate_rows"] == 2


def test_missing_pre_window_blocks_pretrend_diagnostics() -> None:
    scenario = _did_scenario()
    frame = scenario.frame.copy()
    treated = frame["first_ai_reply_date"].notna()
    relative_day = (
        pd.to_datetime(frame["event_date"])
        - pd.to_datetime(frame["first_ai_reply_date"])
    ).dt.days
    frame = frame.loc[~(treated & (relative_day < 0))].copy()

    report = audit_did_panel(frame, scenario.spec)

    assert report.overall_status == AuditStatus.BLOCK
    assert report.pre_outcome_complete_users == 0
    window = next(item for item in report.checks if item.code == "relative_window_coverage")
    assert window.status == AuditStatus.BLOCK


def test_no_never_treated_group_blocks_comparison_structure() -> None:
    scenario = _did_scenario()
    frame = scenario.frame.copy()
    treatment_date = pd.Timestamp("2025-01-08")
    frame["first_ai_reply_date"] = treatment_date
    frame["ai_reply_received"] = (pd.to_datetime(frame["event_date"]) >= treatment_date).astype(int)

    report = audit_did_panel(frame, scenario.spec)

    assert report.overall_status == AuditStatus.BLOCK
    groups = next(item for item in report.checks if item.code == "comparison_groups")
    assert groups.status == AuditStatus.BLOCK
    assert report.never_treated_user_count == 0


def test_missing_required_column_returns_auditable_block() -> None:
    scenario = _did_scenario()
    frame = scenario.frame.drop(columns=["first_ai_reply_date"])

    report = audit_did_panel(frame, scenario.spec)

    assert report.overall_status == AuditStatus.BLOCK
    assert report.checks[0].code == "required_columns"
    assert report.checks[0].evidence["missing_columns"] == ["first_ai_reply_date"]
