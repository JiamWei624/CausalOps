import json

from causalops.evals import run_proposal_evaluation


def test_proposal_safety_evaluation_meets_deterministic_thresholds(tmp_path) -> None:
    summary = run_proposal_evaluation(tmp_path)
    assert summary.total_cases == 12
    assert summary.exact_status_accuracy == 1.0
    assert summary.valid_review_rate == 1.0
    assert summary.injection_block_rate == 1.0
    assert summary.hallucinated_reference_block_rate == 1.0
    assert summary.schema_violation_block_rate == 1.0
    assert summary.unsafe_acceptance_rate == 0.0
    payload = json.loads(summary.report_path.read_text(encoding="utf-8"))
    assert len(payload["cases"]) == 12
