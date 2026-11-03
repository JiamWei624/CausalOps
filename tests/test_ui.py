from io import BytesIO
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from causalops.demo_data import get_demo_scenarios
from causalops.schemas import CausalMethod, GateStatus
from causalops.llm import ProposalStatus, SpecProposalResult, StaticStructuredModelClient
from causalops.ui.controller import (
    dataset_schema_from_frame,
    generate_ai_proposal,
    load_uploaded_table,
    run_workflow,
    run_versioned_workflow,
    validate_workflow,
)
from causalops.research import DraftStatus, ResearchRepository, RevisionSource


def test_all_builtin_scenarios_pass_pre_execution_identification_gate() -> None:
    scenarios = get_demo_scenarios()
    assert len(scenarios) == 6
    for scenario in scenarios.values():
        validation = validate_workflow(scenario.frame, scenario.spec)
        assert validation.inspection["missing_required_columns"] == []
        assert validation.decision.status == GateStatus.PASS


def test_csv_upload_loader_and_workflow(tmp_path: Path) -> None:
    scenario = get_demo_scenarios()["A/B实验"]
    payload = scenario.frame.to_csv(index=False).encode("utf-8")
    loaded = load_uploaded_table(BytesIO(payload), "experiment.csv")
    pd.testing.assert_frame_equal(loaded, scenario.frame, check_dtype=False)
    result = run_workflow(
        loaded,
        scenario.spec,
        tmp_path,
        source_description="test CSV upload",
    )
    assert result.report_path.is_file()
    assert result.trace_path.is_file()


def test_versioned_workflow_binds_run_to_approved_revision(tmp_path: Path) -> None:
    scenario = get_demo_scenarios()["A/B实验"]
    repository = ResearchRepository(tmp_path / "state.sqlite3")
    session = repository.create_session(
        title="A/B versioned run",
        dataset_fingerprint="ab-fingerprint",
        row_count=len(scenario.frame),
        column_schema={str(name): str(dtype) for name, dtype in scenario.frame.dtypes.items()},
    )
    revision = repository.create_revision(
        session.session_id,
        scenario.spec,
        source=RevisionSource.SYSTEM_INITIAL,
        change_reason="初始实验设计",
        activate=True,
        status=DraftStatus.PENDING_REVIEW,
    )
    repository.approve_revision(
        revision.revision_id,
        approved_by="test-user",
        checklist={"variables": True, "covariates": True, "assumptions": True},
    )
    versioned = run_versioned_workflow(
        scenario.frame,
        repository,
        session_id=session.session_id,
        revision_id=revision.revision_id,
        output_dir=tmp_path / "runs",
        source_description="test versioned workflow",
    )
    assert versioned.run_record.run_id == versioned.agent_result.bundle.run_id
    assert versioned.run_record.revision_id == revision.revision_id


def test_streamlit_app_renders_without_exception(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAUSALOPS_STATE_DB", str(tmp_path / "render.sqlite3"))
    app_path = Path(__file__).resolve().parents[1] / "src" / "causalops" / "ui" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "CausalOps · 因果研究工作台"
    proposal_button = next(item for item in app.button if item.label == "生成AI研究设计草案")
    assert proposal_button.disabled is True
    method_selector = next(item for item in app.selectbox if item.label == "候选方法")
    assert "描述性分析（仅设计，暂不可运行）" in method_selector.options


def test_streamlit_disables_execution_for_design_only_method(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAUSALOPS_STATE_DB", str(tmp_path / "design-only.sqlite3"))
    app_path = Path(__file__).resolve().parents[1] / "src" / "causalops" / "ui" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    method_selector = next(item for item in app.selectbox if item.label == "候选方法")
    method_selector.select(CausalMethod.DESCRIPTIVE).run(timeout=30)
    run_button = next(item for item in app.button if item.label == "运行白名单Agent")
    assert run_button.disabled is True
    assert any("通用工作台独立入口" in item.value for item in app.info)


def test_streamlit_chat_modification_creates_candidate_before_acceptance(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "chat-candidate.sqlite3"
    monkeypatch.setenv("CAUSALOPS_STATE_DB", str(database))
    app_path = Path(__file__).resolve().parents[1] / "src" / "causalops" / "ui" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    session_metric = next(item for item in app.metric if item.label == "研究会话")
    session_suffix = session_metric.value
    chat_input = next(
        item for item in app.text_area if item.label == "输入解释、比较、诊断或修改要求"
    )
    chat_input.set_value("请帮我改成 PSM")
    next(item for item in app.button if item.label == "发送").click().run(timeout=30)

    repository = ResearchRepository(database)
    sessions = repository.list_sessions()
    assert len(sessions) == 1
    session = sessions[0]
    revisions = repository.list_revisions(session.session_id)
    assert len(revisions) == 2
    assert session.current_draft_revision_id == revisions[0].revision_id
    assert str(session_suffix) == session.session_id[-8:]

    accept = next(item for item in app.button if item.label == "接受修改")
    accept.click().run(timeout=30)
    current = repository.get_session(session.session_id)
    accepted = repository.get_revision(current.current_draft_revision_id)
    assert accepted.version_number == 2
    assert accepted.status == DraftStatus.NEEDS_REVISION


def test_controller_sends_metadata_not_rows_to_structured_client() -> None:
    frame = pd.DataFrame(
        {
            "user_id": ["secret-user-1", "secret-user-2"],
            "treated": [0, 1],
            "outcome": [1.2, 2.4],
        }
    )
    schema = dataset_schema_from_frame(frame, allowed_source_tables=["local_dataset"])
    assert schema.row_count == 2
    assert schema.columns == {"user_id": "object", "treated": "int64", "outcome": "float64"}
    assert "secret-user-1" not in schema.model_dump_json()

    client = StaticStructuredModelClient(
        {
            "question": "What is the causal effect of treatment on the outcome?",
            "domain": "generic",
            "analysis_unit": "user",
            "treatment": "treated",
            "outcome": "outcome",
            "covariates": [],
            "candidate_methods": ["descriptive"],
            "source_tables": ["local_dataset"],
        }
    )
    result = generate_ai_proposal(
        frame,
        question="Estimate the causal effect with explicit review.",
        allowed_source_tables=["local_dataset"],
        client=client,
    )
    assert result.status == ProposalStatus.NEEDS_REVIEW
    assert result.transmitted_metadata["data_rows_transmitted"] is False


def test_streamlit_default_did_flow_executes_end_to_end(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAUSALOPS_STATE_DB", str(tmp_path / "did-flow.sqlite3"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    app_path = Path(__file__).resolve().parents[1] / "src" / "causalops" / "ui" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    audit_button = next(
        item for item in app.button if item.label == "运行数据质量与处理前窗口核验"
    )
    assert audit_button.disabled is False
    audit_button.click().run(timeout=30)
    for prefix in (
        "我已核对研究问题",
        "我已确认协变量均在处理前确定",
        "我理解随机化",
    ):
        next(item for item in app.checkbox if item.label.startswith(prefix)).check()
    app.run(timeout=30)
    approve_button = next(item for item in app.button if item.label == "批准当前草案版本")
    assert approve_button.disabled is False
    approve_button.click().run(timeout=30)
    run_button = next(item for item in app.button if item.label == "运行白名单Agent")
    assert run_button.disabled is False
    run_button.click().run(timeout=60)
    assert not app.exception
    assert any(item.label == "估计值" for item in app.metric)
    assert {item.label for item in app.download_button} == {
        '下载中文分析报告','下载原始证据（JSON格式）','下载智能体执行轨迹','下载完整图文报告（离线可用）','下载结论解释证据（JSON）'}
    assert len(app.get("plotly_chart")) == 4
    assert any("窗口敏感性分析明细" in m.value for m in app.markdown)
    # A fresh browser session restores the exact persisted run with no new click.
    restored = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not restored.exception
    assert any(item.label == "估计值" for item in restored.metric)
    assert len(restored.get("plotly_chart")) == 4
    assert {item.label for item in restored.download_button} == {item.label for item in app.download_button}
    assert any("基于本次运行证据的结果问答" in h.value for h in restored.header)
    next(item for item in restored.text_area if item.label == "围绕本次运行提问").set_value("这个估计值如何解释？")
    next(item for item in restored.button if item.label == "发送结果问题").click().run(timeout=30)
    assert not restored.exception
    assert any("这个估计值如何解释" in m.value for m in restored.markdown)
    again = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not again.exception
    assert any("这个估计值如何解释" in m.value for m in again.markdown)
    assert any("本地证据摘要" in m.value for m in again.markdown)


def test_saved_revision_audit_remains_available_with_unsaved_form_values(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CAUSALOPS_STATE_DB", str(tmp_path / "audit-current-revision.sqlite3"))
    app_path = Path(__file__).resolve().parents[1] / "src" / "causalops" / "ui" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    analysis_unit = next(item for item in app.text_input if item.label == "分析单位")
    analysis_unit.set_value("temporary_unsaved_unit").run(timeout=30)

    audit_button = next(
        item for item in app.button if item.label == "运行数据质量与处理前窗口核验"
    )
    assert audit_button.disabled is False
    assert any(item.label.startswith("放弃表单临时修改并重新载入 V") for item in app.button)


def test_multimethod_accepted_revision_survives_editor_roundtrip_and_can_be_approved(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "multimethod.sqlite3"
    monkeypatch.setenv("CAUSALOPS_STATE_DB", str(database))
    app_path = Path(__file__).resolve().parents[1] / "src" / "causalops" / "ui" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    repository = ResearchRepository(database)
    session = repository.list_sessions()[0]
    initial = repository.get_revision(session.current_draft_revision_id)
    spec = initial.spec.model_copy(update={
        "candidate_methods": [CausalMethod.DID, CausalMethod.EVENT_STUDY],
        "source_tables": ["local_dataset"],
        "has_pre_treatment_outcome": True,
        "positivity_plausible": False,
        "no_interference_plausible": False,
    })
    revision = repository.create_revision(
        session.session_id,
        spec,
        source=RevisionSource.USER_EDIT,
        change_reason="回归测试：保留多方法与未显示字段",
        activate=True,
        status=DraftStatus.PENDING_REVIEW,
    )
    app.run(timeout=30)
    assert not app.exception
    assert not any("当前表单与已保存草案不同" in item.value for item in app.warning)
    next(item for item in app.button if item.label == "运行数据质量与处理前窗口核验").click().run(timeout=30)
    for prefix in ("我已核对研究问题", "我已确认协变量", "我理解随机化"):
        next(item for item in app.checkbox if item.label.startswith(prefix)).check()
    app.run(timeout=30)
    approve = next(item for item in app.button if item.label == "批准当前草案版本")
    assert approve.disabled is False
    assert repository.get_revision(revision.revision_id).spec == spec
    assert repository.get_revision(revision.revision_id).status == DraftStatus.PENDING_REVIEW


def test_saved_design_is_visible_after_restart_without_temporary_proposal(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "persistent-design.sqlite3"
    monkeypatch.setenv("CAUSALOPS_STATE_DB", str(database))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    app_path = Path(__file__).resolve().parents[1] / "src" / "causalops" / "ui" / "app.py"
    initial_app = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not initial_app.exception
    repo = ResearchRepository(database)
    session = repo.list_sessions()[0]
    current = repo.get_revision(session.current_draft_revision_id)
    revision = repo.create_revision(
        session.session_id, current.spec, source=RevisionSource.AI_CONVERSATION,
        change_reason="已保存的设计说明", activate=True, status=DraftStatus.PENDING_REVIEW,
        research_notes={"design_rationale": "保留双重差分，核对处理前结果覆盖。"},
    )
    fresh_app = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not fresh_app.exception
    assert any(f"当前已保存研究设计 V{revision.version_number}" in m.value for m in fresh_app.markdown)
    assert any("保留双重差分" in item.value for item in fresh_app.markdown)
    assert fresh_app.text_area(key="causalops_question").value == "收到人工智能回复是否提高用户后续互动？"
    assert repo.get_revision(revision.revision_id).spec == current.spec
    assert not any("当前表单与已保存草案不同" in item.value for item in fresh_app.warning)


def test_pending_ai_proposal_and_review_actions_are_restored_after_restart(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "persistent-proposal.sqlite3"
    monkeypatch.setenv("CAUSALOPS_STATE_DB", str(database))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-placeholder")
    scenario = get_demo_scenarios()["DID：AI回复与后续互动"]
    proposal = SpecProposalResult(
        status=ProposalStatus.NEEDS_REVIEW, spec=scenario.spec,
        prompt_sha256="test-digest", transmitted_metadata={"data_rows_transmitted": False},
        provider_metadata={"test_double": True},
    )
    monkeypatch.setattr("causalops.ui.controller.generate_ai_proposal", lambda *a, **k: proposal)
    app_path = Path(__file__).resolve().parents[1] / "src" / "causalops" / "ui" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    next(item for item in app.button if item.label == "生成AI研究设计草案").click().run(timeout=30)
    assert not app.exception
    repo = ResearchRepository(database)
    session = repo.list_sessions()[0]
    current_id = session.current_draft_revision_id
    assert len(repo.list_revisions(session.session_id)) == 2
    fresh = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not fresh.exception
    assert any("AI 研究设计草案" in m.value for m in fresh.markdown)
    assert any(item.label == "接受修改" for item in fresh.button)
    assert repo.get_session(session.session_id).current_draft_revision_id == current_id
