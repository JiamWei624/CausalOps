from pathlib import Path

import pytest

from causalops.research import (
    DraftStatus,
    ResearchRepository,
    ResearchStateError,
    RevisionSource,
)
from causalops.schemas import CausalMethod, CausalSpec


def _spec(*, outcome: str = "outcome") -> CausalSpec:
    return CausalSpec(
        question="Estimate the treatment effect using observed pre-treatment covariates.",
        analysis_unit="user",
        treatment="treated",
        outcome=outcome,
        covariates=["baseline"],
        candidate_methods=[CausalMethod.PSM],
        identification_assumptions=[
            "conditional exchangeability given observed pre-treatment covariates"
        ],
        positivity_plausible=True,
    )


def _repository(tmp_path: Path) -> ResearchRepository:
    return ResearchRepository(tmp_path / "state" / "causalops.sqlite3")


def test_revision_accept_reject_and_persistence(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    session = repository.create_session(
        title="UGC causal study",
        dataset_fingerprint="fingerprint-v1",
        row_count=100,
        column_schema={"treated": "int64", "outcome": "float64", "baseline": "float64"},
    )
    initial = repository.create_revision(
        session.session_id,
        _spec(),
        source=RevisionSource.SYSTEM_INITIAL,
        change_reason="创建初始研究草案",
        activate=True,
        status=DraftStatus.PENDING_REVIEW,
    )
    candidate = repository.create_revision(
        session.session_id,
        _spec(outcome="outcome_30d"),
        source=RevisionSource.USER_EDIT,
        change_reason="修改结果变量",
        parent_revision_id=initial.revision_id,
        research_notes={
            "design_rationale": "使用30日结果窗口。",
            "diagnostic_plan": ["检查窗口敏感性。"],
            "human_review_items": ["确认结果口径。"],
            "unresolved_risks": [],
        },
    )
    assert repository.get_session(session.session_id).current_draft_revision_id == initial.revision_id
    assert candidate.diff["changed_fields"] == ["outcome"]
    assert initial.research_notes == {}
    assert candidate.research_notes["diagnostic_plan"] == ["检查窗口敏感性。"]

    accepted = repository.accept_candidate(candidate.revision_id)
    assert accepted.status == DraftStatus.PENDING_REVIEW
    assert repository.get_session(session.session_id).current_draft_revision_id == candidate.revision_id

    rejected_candidate = repository.create_revision(
        session.session_id,
        _spec(outcome="outcome_90d"),
        source=RevisionSource.USER_EDIT,
        change_reason="测试另一结果窗口",
    )
    repository.reject_candidate(rejected_candidate.revision_id)
    assert repository.get_session(session.session_id).current_draft_revision_id == candidate.revision_id

    reopened = ResearchRepository(repository.database_path)
    versions = reopened.list_revisions(session.session_id)
    assert [item.version_number for item in versions] == [1, 2, 3]
    assert versions[-1].status == DraftStatus.REJECTED
    assert versions[1].research_notes["human_review_items"] == ["确认结果口径。"]


def test_approval_and_analysis_run_are_bound_to_exact_versions(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    session = repository.create_session(
        title="Version binding",
        dataset_fingerprint="fingerprint-v1",
        row_count=100,
        column_schema={"treated": "int64", "outcome": "float64", "baseline": "float64"},
    )
    revision = repository.create_revision(
        session.session_id,
        _spec(),
        source=RevisionSource.SYSTEM_INITIAL,
        change_reason="初始版本",
        activate=True,
        status=DraftStatus.PENDING_REVIEW,
    )
    with pytest.raises(ResearchStateError, match="审核清单"):
        repository.approve_revision(
            revision.revision_id,
            approved_by="tester",
            checklist={"variables": True, "assumptions": False},
        )
    repository.approve_revision(
        revision.revision_id,
        approved_by="tester",
        checklist={"variables": True, "covariates": True, "assumptions": True},
    )
    run = repository.bind_analysis_run(
        session_id=session.session_id,
        revision_id=revision.revision_id,
        dataset_version_id=revision.dataset_version_id,
        run_id="run-v1",
        result_bundle_path="evidence/run-v1.json",
        report_path="reports/run-v1.md",
    )
    assert run.revision_id == revision.revision_id

    candidate = repository.create_revision(
        session.session_id,
        _spec(outcome="outcome_30d"),
        source=RevisionSource.USER_EDIT,
        change_reason="修改结果变量",
    )
    repository.accept_candidate(candidate.revision_id)
    with pytest.raises(ResearchStateError, match="当前草案"):
        repository.bind_analysis_run(
            session_id=session.session_id,
            revision_id=revision.revision_id,
            dataset_version_id=revision.dataset_version_id,
            run_id="invalid-old-run",
            result_bundle_path="x.json",
            report_path="x.md",
        )
    with pytest.raises(ResearchStateError, match="尚未处于已批准状态"):
        repository.bind_analysis_run(
            session_id=session.session_id,
            revision_id=candidate.revision_id,
            dataset_version_id=candidate.dataset_version_id,
            run_id="invalid-unapproved-run",
            result_bundle_path="x.json",
            report_path="x.md",
        )

    repository.approve_revision(
        candidate.revision_id,
        approved_by="tester",
        checklist={"variables": True, "covariates": True, "assumptions": True},
    )
    repository.register_dataset_version(
        session.session_id,
        fingerprint="fingerprint-v2",
        row_count=101,
        column_schema={"treated": "int64", "outcome": "float64", "baseline": "float64"},
    )
    with pytest.raises(ResearchStateError, match="当前数据集"):
        repository.bind_analysis_run(
            session_id=session.session_id,
            revision_id=candidate.revision_id,
            dataset_version_id=candidate.dataset_version_id,
            run_id="invalid-stale-dataset-run",
            result_bundle_path="x.json",
            report_path="x.md",
        )


def test_data_audit_is_immutable_and_bound_to_exact_versions(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    session = repository.create_session(
        title="DID audit binding",
        dataset_fingerprint="did-fingerprint-v1",
        row_count=14,
        column_schema={"user_id": "object", "event_date": "datetime64[ns]"},
    )
    revision = repository.create_revision(
        session.session_id,
        _spec(),
        source=RevisionSource.SYSTEM_INITIAL,
        change_reason="初始版本",
        activate=True,
        status=DraftStatus.PENDING_REVIEW,
    )
    audit = repository.record_data_audit(
        session_id=session.session_id,
        revision_id=revision.revision_id,
        dataset_version_id=revision.dataset_version_id,
        audit_type="did_panel_pretrend_v1",
        status="needs_review",
        report={"overall_status": "needs_review", "checks": []},
    )

    latest = repository.get_latest_data_audit(
        revision_id=revision.revision_id,
        dataset_version_id=revision.dataset_version_id,
    )
    assert latest == audit
    assert latest.report["overall_status"] == "needs_review"

    candidate = repository.create_revision(
        session.session_id,
        _spec(outcome="outcome_30d"),
        source=RevisionSource.USER_EDIT,
        change_reason="新结果口径",
    )
    assert repository.get_latest_data_audit(
        revision_id=candidate.revision_id,
        dataset_version_id=candidate.dataset_version_id,
    ) is None

    with pytest.raises(ResearchStateError, match="数据集版本"):
        repository.record_data_audit(
            session_id=session.session_id,
            revision_id=candidate.revision_id,
            dataset_version_id="dataset_wrong",
            audit_type="did_panel_pretrend_v1",
            status="blocked",
            report={},
        )

