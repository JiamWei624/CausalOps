from __future__ import annotations

import json

import pandas as pd
import pytest
from scipy.stats import t

from causalops.agent import CausalOpsAgent
from causalops.demo_data import get_demo_scenarios
from causalops.estimators import estimate_twfe_did
from causalops.execution import execute_analysis
from causalops.reporting import render_html_report
from causalops.schemas import ClaimLevel
from causalops.visualization import build_did_diagnostic_figures


def _scenario():
    return get_demo_scenarios()["DID：AI回复与后续互动"]


def test_event_intervals_match_clustered_standard_error_and_library_df():
    scenario = _scenario()
    output = estimate_twfe_did(scenario.frame, scenario.spec)
    rows = output.evidence["event_study_table"]
    assert len(rows) == 13
    reference = next(row for row in rows if row["is_reference"])
    assert reference["relative_day"] == -1
    assert reference["ci_lower"] is None and reference["standard_error"] is None
    for row in rows:
        if row["is_reference"]:
            continue
        half_width = t.ppf(0.975, row["degrees_of_freedom"]) * row["standard_error"]
        assert row["ci_lower"] == pytest.approx(row["estimate"] - half_width)
        assert row["ci_upper"] == pytest.approx(row["estimate"] + half_width)


def test_raw_trajectories_match_grouped_input_means():
    scenario = _scenario()
    output = estimate_twfe_did(scenario.frame, scenario.spec)
    for row in output.evidence["group_trajectories"]:
        dates = pd.to_datetime(scenario.frame["event_date"])
        treated = scenario.frame["first_ai_reply_date"].notna()
        subset = scenario.frame.loc[(dates == pd.Timestamp(row["calendar_date"])) &
                                    (treated == (row["group"] == "treated"))]
        assert row["mean_outcome"] == pytest.approx(subset[scenario.spec.outcome].mean())
        assert row["users"] == 80 and row["observations"] == 80


def test_predeclared_windows_preserve_primary_design_and_record_every_comparison(tmp_path):
    scenario = _scenario()
    original = scenario.spec.model_dump_json()
    bundle = execute_analysis(scenario.frame, scenario.spec, tmp_path)
    comparison = bundle.evidence["window_sensitivity"]
    rows = comparison["rows"]
    assert [(r["pre_days"], r["post_days"]) for r in rows] == [(7, 6), (5, 6), (7, 4), (5, 4)]
    assert scenario.spec.model_dump_json() == original
    assert not comparison["changes_approved_spec"]
    assert not comparison["adjusts_for_multiple_testing"]
    assert len({r["variant_spec_sha256"] for r in rows}) == 4
    assert rows[0]["estimate"] == bundle.estimate.estimate
    assert all(r["sample_size"] == 160 * (r["pre_days"] + r["post_days"]) for r in rows)
    assert all(r["treated_users"] == 80 and r["control_users"] == 80 for r in rows)


def test_sensitivity_does_not_upgrade_failed_primary_pretrend(tmp_path):
    scenario = _scenario()
    frame = scenario.frame.copy()
    relative = (frame["event_date"] - frame["first_ai_reply_date"]).dt.days
    frame.loc[relative == -7, "total_interactions"] += 3
    bundle = execute_analysis(frame, scenario.spec, tmp_path)
    assert not bundle.diagnostics[0].passed
    assert bundle.claim_level == ClaimLevel.ASSOCIATIONAL
    rows = bundle.evidence["window_sensitivity"]["rows"]
    assert any(row.get("pretrend_passed") for row in rows if row["pre_days"] == 5)
    assert bundle.spec.pre_period_days == 7


def test_staggered_timing_suppresses_simple_group_plots_and_causal_claim(tmp_path):
    scenario = _scenario()
    frame = scenario.frame.copy()
    users = sorted(frame.loc[frame["first_ai_reply_date"].notna(), "user_id"].unique())
    mask = frame["user_id"].isin(users[40:])
    frame.loc[mask, "first_ai_reply_date"] += pd.Timedelta(days=1)
    frame["ai_reply_received"] = (
        frame["first_ai_reply_date"].notna() & (frame["event_date"] >= frame["first_ai_reply_date"])
    ).astype(int)
    bundle = execute_analysis(frame, scenario.spec, tmp_path)
    assert bundle.claim_level == ClaimLevel.ASSOCIATIONAL
    assert bundle.evidence["window_sensitivity"]["status"] == "not_applicable"
    assert not build_did_diagnostic_figures(bundle)


def test_charts_are_drawn_from_exact_saved_numeric_evidence(tmp_path):
    scenario = _scenario()
    bundle = execute_analysis(scenario.frame, scenario.spec, tmp_path)
    charts = build_did_diagnostic_figures(bundle)
    assert len(charts) == 3
    coefficients = bundle.evidence["estimator"]["event_study_table"]
    expected_pre = [r["estimate"] for r in coefficients if r["relative_day"] < -1]
    assert list(charts["动态效应与逐点置信区间"].data[0].y) == expected_pre
    assert len(charts["预设窗口敏感性分析"].data[0].y) == 4


def test_agent_writes_self_contained_html_and_final_evidence_consistently(tmp_path):
    scenario = _scenario()
    result = CausalOpsAgent().run(scenario.frame, scenario.spec, tmp_path)
    assert result.html_report_path.is_file()
    html = result.html_report_path.read_text(encoding="utf-8")
    assert "动态效应与逐点置信区间" in html
    assert "预设窗口敏感性分析" in html
    assert '<script src="' not in html  # Plotly is embedded for offline viewing.
    saved = json.loads((tmp_path / "evidence" / f"run-{result.bundle.run_id}.json").read_text(encoding="utf-8"))
    assert saved["evidence"]["window_sensitivity"] == result.bundle.evidence["window_sensitivity"]
    trace = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert any(step["tool"] == "write_html_report" and step["status"] == "success" for step in trace["steps"])
    assert "## 预设窗口敏感性分析" in result.report_path.read_text(encoding="utf-8")


def test_html_escapes_research_question(tmp_path):
    scenario = _scenario()
    spec = scenario.spec.model_copy(update={"question": "研究问题 <script>alert('x')</script> 是否有变化？"})
    bundle = execute_analysis(scenario.frame, spec, tmp_path)
    html = render_html_report(bundle)
    assert "<script>alert('x')</script>" not in html
    assert "&lt;script&gt;alert" in html
