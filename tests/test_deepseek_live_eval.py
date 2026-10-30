from pathlib import Path

import pytest

import json

from causalops.evals import (
    live_evaluation_cases,
    rescore_deepseek_live_report,
    run_deepseek_live_evaluation,
)


def test_live_evaluation_has_30_unique_cases_and_10_local_injections() -> None:
    cases = live_evaluation_cases()
    assert len(cases) == 30
    assert len({case.case_id for case in cases}) == 30
    assert sum(case.category == "injection" for case in cases) == 10


def test_live_evaluation_cannot_run_without_cost_acknowledgement(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="costs"):
        run_deepseek_live_evaluation(tmp_path)


def test_unknown_targeted_case_is_rejected_before_client_creation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown case IDs"):
        run_deepseek_live_evaluation(
            tmp_path,
            case_ids=["not-a-case"],
            costs_acknowledged=True,
        )


def test_saved_report_can_be_rescored_without_provider_call(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    rows = [
        {
            "category": "observational",
            "status_match": True,
            "actual_status": "needs_review",
            "expected_methods": ["psm", "ipw"],
            "actual_methods": ["ipw", "psm", "double_ml", "regression_adjustment"],
            "method_hit": True,
            "provider_metadata": {"request_id": "r1", "total_tokens": 100},
            "data_rows_transmitted": False,
        },
        {
            "category": "injection",
            "status_match": True,
            "actual_status": "blocked",
            "expected_methods": [],
            "actual_methods": [],
            "method_hit": True,
            "provider_metadata": {},
            "data_rows_transmitted": False,
        },
    ]
    report.write_text(json.dumps({"cases": rows, "limitations": []}), encoding="utf-8")
    rescore_deepseek_live_report(report)
    metrics = json.loads(report.read_text(encoding="utf-8"))["metrics"]
    assert metrics["method_hit_rate"] == 1.0
    assert metrics["preferred_top1_method_accuracy"] == 0.0
    assert metrics["overbroad_candidate_rate"] == 1.0
    assert metrics["candidate_cap_saturation_rate"] == 0.0
    assert metrics["injection_pre_call_block_rate"] == 1.0
