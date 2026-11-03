from __future__ import annotations

import json
import os
import hashlib
import logging
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pydantic import ValidationError

from causalops.audits import AuditStatus, audit_did_panel
from causalops.agent import AgentRunResult
from causalops.capabilities import format_method_label, get_method_capability
from causalops.demo_data import DemoScenario, get_demo_scenarios
from causalops.execution import UnsupportedMethodExecutionError
from causalops.results.qa import ResultQAService, ANSWER_PIPELINE_VERSION
from causalops.results.narrative import conclusion_sections
from causalops.results.interpretation import business_sections
from causalops.metadata.presentation_zh import diagnostics_for_display
from causalops.real_data import load_registered_catalog, real_external_model_authorized
from causalops.llm import (
    DeepSeekConfigurationError,
    DeepSeekStructuredModelClient,
    ProposalStatus,
    SpecProposalResult,
)
from causalops.metadata import (
    assignment_label_zh,
    build_field_catalog,
    data_structure_label_zh,
    proposal_risk_message_zh,
    proposal_risk_severity_zh,
    sanitize_defaults,
)
from causalops.metadata.presentation_zh import (
    CHECK_LABELS, CHECK_MESSAGES, assumption_label_zh, claim_label_zh,
    diagnostic_rows_zh, domain_label_zh, evidence_zh, field_label_zh,
    format_p_value_zh, message_zh, research_question_zh, status_label_zh, unit_label_zh,
)
from causalops.conversation import DesignConversationService
from causalops.research import (
    DraftRevisionRecord,
    DraftStatus,
    ResearchRepository,
    ResearchStateError,
    RevisionSource,
)
from causalops.schemas import (
    AssignmentMechanism,
    CausalMethod,
    CausalSpec,
    DataStructure,
    DomainName,
    GateStatus,
    ResultBundle,
)
from causalops.ui.controller import (
    generate_ai_proposal,
    load_uploaded_table,
    run_workflow,
    run_versioned_workflow,
    run_versioned_association_workflow,
    validate_workflow,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
UI_OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "ui-runs"
UI_STATE_DB = Path(
    os.environ.get(
        "CAUSALOPS_STATE_DB",
        str(PROJECT_ROOT / "artifacts" / "state" / "causalops.sqlite3"),
    )
)
LOGGER = logging.getLogger(__name__)


_DRAFT_STATUS_ZH = {
    DraftStatus.DRAFT: "候选草案",
    DraftStatus.NEEDS_REVISION: "需要修改",
    DraftStatus.PENDING_REVIEW: "待人工审核",
    DraftStatus.APPROVED: "已审核通过",
    DraftStatus.REJECTED: "已拒绝",
    DraftStatus.INVALID: "校验未通过",
}


def _format_enum(value: object) -> str:
    return getattr(value, "value", str(value))


def _request_initial_spec(frame: pd.DataFrame, dataset_key: str) -> CausalSpec | None:
    """Collect explicit field roles before persisting the first uploaded-data draft."""
    if len(frame.columns) < 2:
        st.info("至少需要两个字段才能建立处理与结果的研究设计。单变量分析请使用描述统计。")
        return None
    with st.form("initial_design_" + dataset_key):
        st.subheader("新数据的研究定义")
        question = st.text_input("研究问题")
        unit = st.text_input("每条记录代表的分析单位")
        treatment = st.selectbox("处理字段", list(frame.columns), index=None, placeholder="请选择字段")
        outcome = st.selectbox("结果字段", list(frame.columns), index=None, placeholder="请选择字段")
        submitted = st.form_submit_button("建立待审草案")
    if not submitted:
        return None
    if not question.strip() or not unit.strip() or treatment is None or outcome is None or treatment == outcome:
        st.error("请填写问题与分析单位，并选择两个不同的字段。")
        return None
    try:
        return CausalSpec(question=question.strip(), analysis_unit=unit.strip(), treatment=treatment, outcome=outcome)
    except ValueError:
        st.error("研究定义未通过校验。请核对问题、分析单位和字段。")
        return None


def _seed_editor_state(spec: CausalSpec) -> None:
    values = {
        "causalops_domain": spec.domain,
        "causalops_method": spec.candidate_methods[0] if spec.candidate_methods else CausalMethod.DESCRIPTIVE,
        "causalops_analysis_unit": unit_label_zh(spec.analysis_unit),
        "causalops_treatment": spec.treatment,
        "causalops_outcome": spec.outcome,
        "causalops_covariates": spec.covariates,
        "causalops_entity_id": spec.entity_id_column or "<未设置>",
        "causalops_time": spec.time_column or "<未设置>",
        "causalops_treatment_time": spec.treatment_time_column or "<未设置>",
        "causalops_assignment": spec.assignment_mechanism,
        "causalops_data_structure": spec.data_structure,
        "causalops_cluster": spec.cluster_column or "<未设置>",
        "causalops_pre_period": spec.pre_period_days or 28,
        "causalops_post_period": spec.post_period_days or 28,
        "causalops_has_pre_outcome": spec.has_pre_treatment_outcome,
        "causalops_positivity": spec.positivity_plausible is True,
        "causalops_parallel": spec.parallel_trends_plausible is True,
        "causalops_assumptions": "\n".join(assumption_label_zh(a) for a in spec.identification_assumptions),
    }
    st.session_state.update(values)


def _load_revision_into_editor(spec: CausalSpec, revision_id: str) -> None:
    """Replace transient widget state with one persisted draft revision."""

    st.session_state["causalops_question"] = research_question_zh(spec.question)
    _seed_editor_state(spec)
    st.session_state["causalops_editor_revision_id"] = revision_id


def _design_editor(frame: pd.DataFrame, initial: CausalSpec, question: str) -> CausalSpec | None:
    columns = list(frame.columns)
    catalog = build_field_catalog(frame)
    treatment_options = [name for name, item in catalog.items() if item.can_be_treatment] or columns
    outcome_options = [name for name, item in catalog.items() if item.can_be_outcome] or columns
    covariate_options = [name for name, item in catalog.items() if item.can_be_covariate]
    time_options = [name for name, item in catalog.items() if item.can_be_time]

    def field_label(name: str) -> str:
        item = catalog.get(name)
        if item is None or item.label_zh == name:
            return name
        return f"{item.label_zh}（{name}）"

    def repair_single_state(key: str, preferred: str | None, options: list[str]) -> None:
        if not options:
            return
        current = st.session_state.get(key, preferred)
        if current not in options:
            replacement = preferred if preferred in options else options[0]
            if current not in {None, "<未设置>"}:
                st.warning(f"字段 {current} 不再属于当前可选范围，已重置为 {replacement}。")
            st.session_state[key] = replacement

    repair_single_state("causalops_treatment", initial.treatment, treatment_options)
    repair_single_state("causalops_outcome", initial.outcome, outcome_options)
    st.subheader("3. 人工审核与字段映射")
    left, middle, right = st.columns(3)
    domain = left.selectbox(
        "业务领域",
        list(DomainName),
        index=list(DomainName).index(initial.domain),
        format_func=domain_label_zh,
        key="causalops_domain",
    )
    method = middle.selectbox(
        "候选方法",
        list(CausalMethod),
        index=list(CausalMethod).index(initial.candidate_methods[0])
        if initial.candidate_methods
        else list(CausalMethod).index(CausalMethod.DESCRIPTIVE),
        format_func=format_method_label,
        key="causalops_method",
    )
    capability = get_method_capability(method)
    if not capability.executable:
        st.info(capability.unavailable_reason)
    analysis_unit = right.text_input("分析单位", value=unit_label_zh(initial.analysis_unit), key="causalops_analysis_unit")
    if analysis_unit == unit_label_zh(initial.analysis_unit):
        analysis_unit = initial.analysis_unit
    treatment = left.selectbox(
        "处理变量",
        treatment_options,
        index=treatment_options.index(initial.treatment) if initial.treatment in treatment_options else 0,
        format_func=field_label,
        key="causalops_treatment",
    )
    outcome = middle.selectbox(
        "结果变量",
        outcome_options,
        index=outcome_options.index(initial.outcome) if initial.outcome in outcome_options else 0,
        format_func=field_label,
        key="causalops_outcome",
    )
    if capability.uses("covariates"):
        selectable_covariates = [
            column for column in covariate_options if column not in {treatment, outcome}
        ]
        proposed_defaults = st.session_state.get("causalops_covariates", initial.covariates)
        valid_defaults, invalid_defaults = sanitize_defaults(
            proposed_defaults, selectable_covariates
        )
        st.session_state["causalops_covariates"] = valid_defaults
        covariates = st.multiselect(
            "处理前协变量",
            selectable_covariates,
            default=valid_defaults,
            format_func=field_label,
            help="分类与布尔字段将采用受控编码；仍须确认字段在处理发生前已经确定。",
            key="causalops_covariates",
            placeholder="请选择处理前协变量",
        )
        if invalid_defaults:
            reasons = [
                f"{name}：{catalog[name].availability_reason}"
                if name in catalog
                else f"{name}：当前数据集中不存在"
                for name in invalid_defaults
            ]
            st.warning("以下草案或旧会话字段未被静默使用：" + "；".join(reasons))
    else:
        covariates = []

    def optional_select(
        label: str,
        current: str | None,
        key: str,
        candidates: list[str] | None = None,
    ) -> str | None:
        optional_columns = ["<未设置>", *(candidates if candidates is not None else columns)]
        repair_single_state(key, current or "<未设置>", optional_columns)
        selected = st.selectbox(
            label,
            optional_columns,
            index=optional_columns.index(current) if current in optional_columns else 0,
            format_func=lambda value: value if value == "<未设置>" else field_label(value),
            key=key,
        )
        return None if selected == "<未设置>" else selected

    entity_id = None
    time_column = None
    treatment_time = None
    identifier_columns = st.columns(3)
    identifier_index = 0
    if capability.uses("entity_id"):
        with identifier_columns[identifier_index]:
            entity_id = optional_select(
                "实体/随机化单位ID", initial.entity_id_column, "causalops_entity_id"
            )
        identifier_index += 1
    if capability.uses("time_column"):
        with identifier_columns[identifier_index]:
            time_column = optional_select(
                "时间字段", initial.time_column, "causalops_time", time_options
            )
        identifier_index += 1
    if capability.uses("treatment_time"):
        with identifier_columns[identifier_index]:
            treatment_time = optional_select(
                "首次处理时间字段",
                initial.treatment_time_column,
                "causalops_treatment_time",
                time_options,
            )

    assignment = AssignmentMechanism.UNKNOWN
    data_structure = DataStructure.UNKNOWN
    cluster_column = None
    design_columns = st.columns(3)
    design_index = 0
    if capability.uses("assignment"):
        assignment = design_columns[design_index].selectbox(
            "处理分配机制",
            list(AssignmentMechanism),
            index=list(AssignmentMechanism).index(initial.assignment_mechanism),
            format_func=assignment_label_zh,
            key="causalops_assignment",
        )
        design_index += 1
    if capability.uses("data_structure"):
        data_structure = design_columns[design_index].selectbox(
            "数据结构",
            list(DataStructure),
            index=list(DataStructure).index(initial.data_structure),
            format_func=data_structure_label_zh,
            key="causalops_data_structure",
        )
        design_index += 1
    if capability.uses("cluster"):
        with design_columns[design_index]:
            cluster_column = optional_select(
                "聚类字段", initial.cluster_column, "causalops_cluster"
            )

    pre_period: int | None = None
    post_period: int | None = None
    if capability.uses("windows"):
        w1, w2 = st.columns(2)
        pre_period = int(
            w1.number_input(
                "处理前窗口（天）",
                min_value=1,
                value=initial.pre_period_days or 28,
                key="causalops_pre_period",
            )
        )
        post_period = int(
            w2.number_input(
                "处理后窗口（天）",
                min_value=1,
                value=initial.post_period_days or 28,
                key="causalops_post_period",
            )
        )

    has_pre_outcome = initial.has_pre_treatment_outcome
    positivity: bool | None = initial.positivity_plausible
    parallel: bool | None = initial.parallel_trends_plausible
    assumption_columns = st.columns(3)
    assumption_index = 0
    if capability.uses("has_pre_outcome"):
        has_pre_outcome = assumption_columns[assumption_index].checkbox(
            "存在处理前结果/基线指标",
            value=initial.has_pre_treatment_outcome,
            key="causalops_has_pre_outcome",
        )
        assumption_index += 1
    if capability.uses("positivity"):
        positivity = assumption_columns[assumption_index].checkbox(
            "重叠性在业务上合理（仍需实证诊断）",
            value=initial.positivity_plausible is True,
            key="causalops_positivity",
        )
        assumption_index += 1
    if capability.uses("parallel_trends"):
        parallel = assumption_columns[assumption_index].checkbox(
            "平行趋势在业务上合理（仍需实证检验）",
            value=initial.parallel_trends_plausible is True,
            key="causalops_parallel",
        )
    assumptions = st.text_area(
        "识别假设（每行一条）",
        value="\n".join(assumption_label_zh(a) for a in initial.identification_assumptions),
        height=100,
        key="causalops_assumptions",
    )
    try:
        # The editor selects the primary method. Merely rendering the form must
        # preserve additional design methods and fields without visible widgets.
        methods = (
            list(initial.candidate_methods)
            if initial.candidate_methods and method == initial.candidate_methods[0]
            else [method]
        )
        return CausalSpec(
            question=question,
            domain=domain,
            analysis_unit=analysis_unit,
            treatment=treatment,
            outcome=outcome,
            time_column=time_column,
            entity_id_column=entity_id,
            treatment_time_column=treatment_time,
            covariates=covariates,
            candidate_methods=methods,
            identification_assumptions=[
                {assumption_label_zh(a): a for a in initial.identification_assumptions}.get(line.strip(), line.strip())
                for line in assumptions.splitlines() if line.strip()
            ],
            pre_period_days=pre_period,
            post_period_days=post_period,
            cluster_column=cluster_column,
            assignment_mechanism=assignment,
            data_structure=data_structure,
            has_pre_treatment_outcome=has_pre_outcome,
            positivity_plausible=(
                True if positivity is True
                else False if initial.positivity_plausible is False else None
            ),
            parallel_trends_plausible=(
                True if parallel is True
                else False if initial.parallel_trends_plausible is False else None
            ),
            no_interference_plausible=initial.no_interference_plausible,
            source_tables=list(initial.source_tables),
        )
    except ValidationError as exc:
        st.error(f"CausalSpec校验失败：{exc}")
        return None


def _show_result(result: object, known_effect: float | None) -> None:
    bundle = result.bundle
    st.subheader("7. 分析结果与结论边界")
    st.caption(f"运行编号：{bundle.run_id}。结果与诊断来自本次保存的分析记录。")
    if bundle.plan.selected_method == CausalMethod.DID and (
        bundle.evidence.get("estimator", {}).get("estimator_version")
        != "twfe_did_v2_complete_event_reference"
    ):
        st.warning(
            "此结果使用旧版事件时间诊断生成。现已修正基准期与窗口边界，请点击上方运行按钮重新计算；"
            "旧运行记录会保留。"
        )
    if bundle.estimate:
        estimate = bundle.estimate
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("估计值", f"{estimate.estimate:.4f}")
        m2.metric("标准误", f"{estimate.standard_error:.4f}" if estimate.standard_error is not None else "未计算")
        m3.metric("概率值（P值）", format_p_value_zh(estimate.p_value))
        m4.metric("主张等级", claim_label_zh(bundle.claim_level))
        with st.container(border=True):
            st.subheader("主要结论")
            for title, paragraphs in business_sections(bundle):
                st.markdown("**" + title + "**")
                for paragraph in paragraphs: st.write(paragraph)
        if estimate.p_value == 0:
            st.caption("本次概率值计算被数值舍入为零，不能解释为真实概率严格等于零。")
        if estimate.confidence_interval:
            lower, upper = estimate.confidence_interval
            figure = go.Figure()
            figure.add_trace(
                go.Scatter(
                    x=[lower, estimate.estimate, upper],
                    y=["95%置信区间"] * 3,
                    mode="lines+markers",
                    marker={"size": [7, 12, 7]},
                    name="估计值及置信区间",
                )
            )
            figure.add_vline(x=0, line_dash="dash", line_color="gray", annotation_text="零效应")
            if known_effect is not None:
                figure.add_vline(x=known_effect, line_dash="dot", line_color="black", annotation_text="合成数据设定值")
            figure.update_layout(height=240, margin=dict(l=20, r=20, t=25, b=20), xaxis_title="效应估计值")
            st.plotly_chart(figure, width="stretch")
    diagnostic_rows = diagnostic_rows_zh(diagnostics_for_display(bundle))
    st.dataframe(pd.DataFrame(diagnostic_rows), width="stretch", hide_index=True)
    if bundle.warnings:
        for warning in bundle.warnings:
            st.warning(message_zh(warning))
    if bundle.plan.selected_method == CausalMethod.DID:
        from causalops.visualization import build_did_diagnostic_figures, event_table_zh, sensitivity_table_zh
        figures = build_did_diagnostic_figures(bundle)
        for title, figure in figures.items():
            st.markdown(f"#### {title}")
            st.plotly_chart(figure, width="stretch")
        if figures:
            st.caption(
                "动态效应以处理前第1日为基准；误差线为按用户聚类的逐点95%置信区间，"
                "未作同时推断校正。原始轨迹未经回归调整，须结合研究设计解释。"
            )
            with st.expander("查看逐期系数与区间明细", expanded=False):
                st.dataframe(pd.DataFrame(event_table_zh(bundle)), hide_index=True, width="stretch")
            st.markdown("#### 窗口敏感性分析明细")
            st.dataframe(pd.DataFrame(sensitivity_table_zh(bundle)), hide_index=True, width="stretch")
        else:
            st.info("当前运行记录未包含可展示的动态诊断图；请重新运行，交错处理数据需先采用合适的估计方法。")
        sensitivity = bundle.evidence.get("window_sensitivity") or {}
        for limitation in sensitivity.get("limitations", []):
            st.caption(limitation)
    if bundle.plan.selected_method == CausalMethod.REGRESSION_ADJUSTMENT:
        from causalops.visualization import build_regression_diagnostic_figures
        for title,figure in build_regression_diagnostic_figures(bundle).items():
            st.markdown('#### '+title)
            st.plotly_chart(figure,width='stretch')
        with st.expander('查看回归系数与聚类区间'):
            st.dataframe(pd.DataFrame(bundle.evidence.get('estimator',{}).get('coefficient_table',[])).rename(
                columns={'term':'变量','estimate':'系数','standard_error':'聚类标准误','ci_lower':'区间下界','ci_upper':'区间上界'}),hide_index=True)
    st.markdown("#### 综合结论与平台应用边界")
    for title, paragraphs in conclusion_sections(bundle):
        if title == "综合结论与平台应用边界":
            for paragraph in paragraphs:
                st.write(paragraph)
    from causalops.reporting import render_html_report, render_markdown_report
    report_text = render_markdown_report(bundle)
    evidence_path = result.report_path.parent.parent / "evidence" / f"run-{bundle.run_id}.json"
    trace_text = result.trace_path.read_text(encoding="utf-8")
    d1, d2, d3, d4 = st.columns(4)
    d1.download_button("下载中文分析报告", report_text, file_name=result.report_path.name)
    d2.download_button(
        "下载原始证据（JSON格式）",
        evidence_path.read_bytes(),
        file_name=evidence_path.name,
        mime="application/json",
    )
    d3.download_button(
        "下载智能体执行轨迹",
        trace_text,
        file_name=result.trace_path.name,
        mime="application/json",
    )
    html_path = getattr(result, "html_report_path", None)
    html_content = render_html_report(bundle)
    d4.download_button("下载完整图文报告（离线可用）", html_content,
                       file_name=f"report-{bundle.run_id}.html", mime="text/html")
    from causalops.results.interpretation import interpret_run
    st.download_button('下载结论解释证据（JSON）',json.dumps(interpret_run(bundle),ensure_ascii=False,indent=2),
                       file_name=f'interpretation-{bundle.run_id}.json',mime='application/json')


def _restore_saved_result(repository: ResearchRepository, revision: DraftRevisionRecord) -> AgentRunResult | None:
    record = repository.get_latest_analysis_run(
        revision_id=revision.revision_id, dataset_version_id=revision.dataset_version_id,
    )
    if record is None:
        return None
    evidence_path, report_path = Path(record.result_bundle_path), Path(record.report_path)
    trace_path = report_path.parent.parent / "traces" / f"agent-run-{record.run_id}.json"
    html_path = report_path.with_suffix(".html")
    try:
        bundle = ResultBundle.model_validate_json(evidence_path.read_text(encoding="utf-8"))
        if bundle.run_id != record.run_id or bundle.spec != revision.spec:
            raise ValueError("保存结果与草案版本的绑定不一致")
        if not report_path.is_file() or not trace_path.is_file():
            raise ValueError("保存结果的报告或执行轨迹缺失")
    except (OSError, ValueError) as exc:
        st.warning(f"当前版本的历史运行暂时无法恢复：{exc}")
        return None
    return AgentRunResult(bundle=bundle, report_path=report_path, trace_path=trace_path,
                          html_report_path=html_path if html_path.is_file() else None)


def _context_fingerprint(frame: pd.DataFrame, question: str) -> str:
    metadata = {
        "question": question,
        "columns": [(str(column), str(dtype)) for column, dtype in frame.dtypes.items()],
        "row_count": len(frame),
    }
    return hashlib.sha256(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _dataset_content_fingerprint(frame: pd.DataFrame) -> str:
    """Fingerprint values locally so same-schema data changes create new state."""

    digest = hashlib.sha256()
    schema = [(str(column), str(dtype)) for column, dtype in frame.dtypes.items()]
    digest.update(json.dumps(schema, ensure_ascii=False).encode("utf-8"))
    try:
        values = pd.util.hash_pandas_object(frame, index=True).to_numpy()
    except TypeError:
        values = pd.util.hash_pandas_object(frame.astype("string"), index=True).to_numpy()
    digest.update(values.tobytes())
    return digest.hexdigest()


def _show_revision_diff(revision: DraftRevisionRecord) -> None:
    rows = []
    for field, change in revision.diff.get("changes", {}).items():
        rows.append(
            {
                "字段": field,
                "修改前": json.dumps(change.get("before"), ensure_ascii=False),
                "修改后": json.dumps(change.get("after"), ensure_ascii=False),
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.caption("该候选版本与来源版本没有结构化字段差异。")


def _show_revision_research_notes(revision: DraftRevisionRecord) -> None:
    notes = revision.research_notes or {}
    if not notes:
        return
    rationale = str(notes.get("design_rationale", "")).strip()
    if rationale:
        st.markdown("**设计理由**")
        st.write(rationale)
    sections = (
        ("diagnostic_plan", "诊断计划"),
        ("human_review_items", "人工审核项"),
        ("unresolved_risks", "未解决风险"),
    )
    for key, label in sections:
        items = [str(item).strip() for item in notes.get(key, []) if str(item).strip()]
        if items:
            st.markdown(f"**{label}**")
            for item in items:
                st.markdown(f"- {item}")


def _candidate_review_panel(
    repository: ResearchRepository,
    candidate: DraftRevisionRecord,
) -> None:
    if candidate.status not in {DraftStatus.DRAFT, DraftStatus.NEEDS_REVISION}:
        return
    with st.container(border=True):
        st.markdown(
            f"#### 候选修订 V{candidate.version_number}｜{_DRAFT_STATUS_ZH[candidate.status]}"
        )
        st.markdown(f"**修改原因**：{candidate.change_reason}")
        _show_revision_diff(candidate)
        _show_revision_research_notes(candidate)
        accept_col, reject_col, discuss_col = st.columns(3)
        if accept_col.button(
            "接受修改",
            key=f"accept_revision_{candidate.revision_id}",
            help=(
                "接受后会成为当前草案，但仍保持“需要修改”，不能批准或执行。"
                if candidate.status == DraftStatus.NEEDS_REVISION
                else "接受后成为新的当前草案，但仍需重新审核。"
            ),
        ):
            accepted = repository.accept_candidate(candidate.revision_id)
            _seed_editor_state(accepted.spec)
            st.session_state.pop("causalops_candidate_revision_id", None)
            st.rerun()
        if reject_col.button(
            "放弃修改", key=f"reject_revision_{candidate.revision_id}"
        ):
            repository.reject_candidate(candidate.revision_id)
            st.session_state.pop("causalops_candidate_revision_id", None)
            st.rerun()
        discuss_col.caption("继续讨论不会改变当前草案；可在下方研究对话中补充要求。")


def _show_research_history(
    repository: ResearchRepository,
    session_id: str,
) -> None:
    revisions = repository.list_revisions(session_id)
    session = repository.get_session(session_id)
    with st.sidebar:
        st.markdown("### 研究版本")
        st.caption(f"会话：{session.session_id[-10:]}")
        labels = {
            revision.revision_id: (
                f"V{revision.version_number}｜{_DRAFT_STATUS_ZH[revision.status]}"
                + ("｜当前" if revision.revision_id == session.current_draft_revision_id else "")
            )
            for revision in revisions
        }
        if labels:
            selected = st.selectbox(
                "查看历史草案",
                list(labels),
                format_func=lambda revision_id: labels[revision_id],
                key="causalops_history_revision_id",
            )
            historical = repository.get_revision(selected)
            st.caption(historical.change_reason)
            with st.expander("版本差异", expanded=False):
                _show_revision_diff(historical)
                _show_revision_research_notes(historical)


def _safe_provider_error_details(exc: Exception) -> dict[str, object]:
    """Return bounded diagnostics without exposing credentials or request content."""

    body = getattr(exc, "body", None)
    body = body if isinstance(body, dict) else {}
    error_body = body.get("error") if isinstance(body.get("error"), dict) else body
    values = {
        "status_code": getattr(exc, "status_code", None),
        "error_type": getattr(exc, "type", None) or error_body.get("type"),
        "error_code": getattr(exc, "code", None) or error_body.get("code"),
        "parameter": getattr(exc, "param", None) or error_body.get("param"),
        "message": error_body.get("message") or str(exc),
    }
    sanitized: dict[str, object] = {}
    for key, value in values.items():
        if value is None:
            continue
        text = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-[REDACTED]", str(value))
        sanitized[key] = text[:800]
    return sanitized


def _safe_raw_http_details(status_code: int, body: bytes) -> dict[str, object]:
    """Expose only bounded provider diagnostics from a fixed, data-free probe."""

    try:
        raw_text = body.decode("utf-8", errors="replace")
        payload = json.loads(raw_text)
    except Exception:
        payload = None
    details: dict[str, object] = {"status_code": status_code}
    if isinstance(payload, dict):
        error = payload.get("error", payload)
        if isinstance(error, dict):
            mapping = {
                "error_type": error.get("type"),
                "error_code": error.get("code"),
                "parameter": error.get("param"),
                "message": error.get("message"),
            }
            details.update({key: value for key, value in mapping.items() if value is not None})
        data = payload.get("data")
        if status_code == 200 and isinstance(data, list):
            model_ids = [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]
            details["available_models"] = ", ".join(model_ids[:8])
    if "message" not in details:
        details["message"] = raw_text or f"HTTP {status_code}"
    sanitized: dict[str, object] = {}
    for key, value in details.items():
        if value is None:
            continue
        text = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-[REDACTED]", str(value))
        sanitized[key] = re.sub(r"\s+", " ", text).strip()[:800]
    return sanitized


def _run_deepseek_connection_diagnostics() -> list[dict[str, object]]:
    """Run fixed, data-free probes from least to most provider-specific.

    The first probe deliberately matches DeepSeek's published Responses example:
    model + instructions + input only. Optional request fields are introduced only
    after that succeeds, so a 400 can be attributed to a specific protocol layer.
    """

    from openai import OpenAI

    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return [{"probe": "configuration", "ok": False, "message": "DEEPSEEK_API_KEY 未配置"}]
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    client = OpenAI(api_key=key, base_url=base_url, timeout=45.0, max_retries=0)
    results: list[dict[str, object]] = [
        {
            "probe": "runtime_config",
            "ok": True,
            "provider_host": urlparse(base_url).hostname or "unknown",
            "model": model,
            "api_mode": os.environ.get("DEEPSEEK_API_MODE", "responses"),
            "key_fingerprint": os.environ.get(
                "DEEPSEEK_KEY_FINGERPRINT",
                hashlib.sha256(key.encode("utf-8")).hexdigest()[:12],
            ),
            "key_length": len(key),
        }
    ]
    response_probes = [
        (
            "responses_official_minimal",
            {
                "instructions": "Reply with exactly OK.",
                "input": "Connection test. No user data is included.",
            },
        ),
        (
            "responses_optional_fields",
            {
                "instructions": "Reply with exactly OK.",
                "input": "Optional-field protocol test. No user data is included.",
                "reasoning": {"effort": "none"},
                "max_output_tokens": 64,
                "stream": False,
            },
        ),
        (
            "json_object",
            {
                "instructions": "Return only one JSON object: {\"ok\": true}.",
                "input": "Protocol test. No user data is included.",
                "reasoning": {"effort": "none"},
                "max_output_tokens": 64,
                "stream": False,
                "text": {"format": {"type": "json_object"}},
            },
        ),
        (
            "json_schema",
            {
                "instructions": "Return the requested structured object.",
                "input": "Schema test. No user data is included.",
                "reasoning": {"effort": "none"},
                "max_output_tokens": 64,
                "stream": False,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "connection_test",
                        "schema": {
                            "type": "object",
                            "properties": {"ok": {"type": "boolean"}},
                            "required": ["ok"],
                            "additionalProperties": False,
                        },
                    }
                },
            },
        ),
    ]
    responses_ok = True
    for name, arguments in response_probes:
        try:
            response = client.responses.create(
                model=model,
                **arguments,
            )
            results.append(
                {
                    "probe": name,
                    "ok": getattr(response, "status", None) == "completed",
                    "status": getattr(response, "status", None),
                    "model": getattr(response, "model", model),
                }
            )
        except Exception as exc:
            results.append(
                {"probe": name, "ok": False, **_safe_provider_error_details(exc)}
            )
            # Format probes are meaningless if the official minimal request fails.
            if name == "responses_official_minimal":
                responses_ok = False
                break
            # Each later probe depends on the preceding protocol layer.
            break

    if not responses_ok:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly OK."}],
            )
            results.append(
                {
                    "probe": "chat_completions_minimal",
                    "ok": bool(getattr(completion, "choices", None)),
                    "model": getattr(completion, "model", model),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "probe": "chat_completions_minimal",
                    "ok": False,
                    **_safe_provider_error_details(exc),
                }
            )

    # Raw HTTPS probes bypass the OpenAI SDK completely. They use only Python's
    # standard library, fixed payloads, no inherited HTTP proxy, never print the
    # Authorization header, and expose only a bounded/redacted response body.
    try:
        from urllib.error import HTTPError
        from urllib.request import ProxyHandler, Request, build_opener

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        opener = build_opener(ProxyHandler({}))

        def run_raw_probe(
            probe: str,
            *,
            path: str,
            method: str,
            payload: dict[str, object] | None = None,
        ) -> dict[str, object]:
            request = Request(
                f"{base_url}{path}",
                data=(
                    json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    if payload is not None
                    else None
                ),
                headers=headers,
                method=method,
            )
            try:
                with opener.open(request, timeout=45.0) as response:
                    status_code = int(response.status)
                    body = response.read(65536)
            except HTTPError as exc:
                status_code = int(exc.code)
                body = exc.read(65536)
            return {
                "probe": probe,
                "ok": status_code == 200,
                **_safe_raw_http_details(status_code, body),
            }

        results.append(
            run_raw_probe("raw_models_list", path="/models", method="GET")
        )
        results.append(
            run_raw_probe(
                "raw_chat_completions",
                path="/chat/completions",
                method="POST",
                payload={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with exactly OK."}],
                    "stream": False,
                },
            )
        )
    except Exception as exc:
        results.append(
            {
                "probe": "raw_https_transport",
                "ok": False,
                "message": re.sub(
                    r"sk-[A-Za-z0-9_-]+",
                    "sk-[REDACTED]",
                    f"{type(exc).__name__}: {exc}",
                )[:800],
            }
        )
    return results


def _conversation_panel(
    repository: ResearchRepository,
    session_id: str,
    catalog: dict[str, object],
) -> None:
    st.subheader("研究设计持续对话")
    model_enabled = bool(os.environ.get("DEEPSEEK_API_KEY")) and st.session_state.get('causalops_external_model_allowed',True)
    if model_enabled:
        st.caption(
            "DeepSeek 已启用：仅可解释当前设计或生成未激活的候选修订。"
            "它不能接受候选、批准草案或执行分析；不向模型发送数据行。"
        )
        with st.expander("DeepSeek 连接诊断", expanded=False):
            st.caption(
                "仅发送固定的最小测试请求，不包含研究问题、字段、对话或数据行；"
                "先复现官方最小样例，再逐层检查附加参数、JSON Object、"
                "JSON Schema、Chat Completions 与绕过 SDK 的原始 HTTPS 请求。"
            )
            if st.button("运行连接诊断", key="causalops_deepseek_diagnostics"):
                with st.spinner("正在执行最小协议探测……"):
                    st.session_state["causalops_deepseek_diagnostic_results"] = (
                        _run_deepseek_connection_diagnostics()
                    )
            diagnostic_results = st.session_state.get(
                "causalops_deepseek_diagnostic_results"
            )
            if diagnostic_results:
                st.dataframe(
                    pd.DataFrame(diagnostic_results),
                    width="stretch",
                    hide_index=True,
                )
    else:
        st.caption(
            "当前使用本地确定性对话。外部模型只有在密钥已配置且该数据获得发送授权后才会启用。"
        )
    messages = repository.list_chat_messages(session_id)
    if not messages:
        st.caption("可询问为什么选择某方法、比较方法、诊断当前设计，或明确提出修改要求。")
    for message in messages[-8:]:
        with st.chat_message(message.role):
            st.write(message.content)
            if message.intent:
                st.caption(f"意图：{message.intent.value}")
    with st.form("causalops_design_chat", clear_on_submit=True):
        user_message = st.text_area(
            "输入解释、比较、诊断或修改要求",
            placeholder="例如：加入性别和是否认证作为协变量",
            height=80,
        )
        send = st.form_submit_button("发送")
    if send and user_message.strip():
        try:
            model_client = None
            if model_enabled:
                try:
                    model_client = DeepSeekStructuredModelClient()
                except DeepSeekConfigurationError as exc:
                    st.warning(f"DeepSeek 配置不可用，已回退本地确定性对话：{exc}")
            turn = DesignConversationService(
                repository, model_client=model_client
            ).handle(
                session_id=session_id,
                message=user_message.strip(),
                catalog=catalog,
            )
            if turn.candidate_revision:
                st.session_state["causalops_candidate_revision_id"] = (
                    turn.candidate_revision.revision_id
                )
            st.rerun()
        except (ValueError, ResearchStateError) as exc:
            st.error(f"研究对话未完成：{exc}")


def _show_proposal(result: SpecProposalResult) -> None:
    if result.status == ProposalStatus.BLOCKED:
        st.error("AI研究设计草案已被安全门禁阻断；不会进入执行链路。")
    else:
        st.success("已生成结构化研究设计草案。它尚未获批，必须人工核对并通过确定性识别门控。")
    if result.spec is not None:
        spec = result.spec
        capability = get_method_capability(
            spec.candidate_methods[0] if spec.candidate_methods else CausalMethod.DESCRIPTIVE
        )
        with st.container(border=True):
            st.markdown("#### AI 研究设计草案｜待人工审核")
            st.markdown(f"**研究问题**：{research_question_zh(spec.question)}")
            method_names = [format_method_label(method) for method in spec.candidate_methods]
            st.markdown(
                f"**首选方法**：{method_names[0] if method_names else '尚未确定'}  "
                f"\n**备选方法**：{'、'.join(method_names[1:]) if len(method_names) > 1 else '无'}"
            )
            st.caption(
                "方法推荐仅表示研究设计候选，不代表识别条件已经满足。"
                + ("当前已有受控执行器。" if capability.executable else "当前尚无受控执行器。")
            )
            variable_rows = [
                {"角色": "分析单位", "字段/定义": unit_label_zh(spec.analysis_unit)},
                {"角色": "处理变量", "字段/定义": field_label_zh(spec.treatment)},
                {"角色": "结果变量", "字段/定义": field_label_zh(spec.outcome)},
                {"角色": "处理前协变量", "字段/定义": "、".join(field_label_zh(c) for c in spec.covariates) or "尚未指定"},
                {"角色": "实体标识", "字段/定义": field_label_zh(spec.entity_id_column or "尚未指定")},
                {"角色": "时间字段", "字段/定义": field_label_zh(spec.time_column or "尚未指定")},
                {"角色": "首次处理时间", "字段/定义": field_label_zh(spec.treatment_time_column or "尚未指定")},
            ]
            st.dataframe(pd.DataFrame(variable_rows), width="stretch", hide_index=True)
            c1, c2 = st.columns(2)
            c1.markdown(f"**处理分配机制**：{assignment_label_zh(spec.assignment_mechanism)}")
            c2.markdown(f"**数据结构**：{data_structure_label_zh(spec.data_structure)}")
            st.markdown(
                "**识别假设**："
                + ("；".join(assumption_label_zh(a) for a in spec.identification_assumptions) if spec.identification_assumptions else "尚未由人工确认")
            )
    for risk in result.risks:
        st.warning(
            f"[{proposal_risk_severity_zh(risk.severity)}风险] "
            f"{proposal_risk_message_zh(risk.code, risk.message)}"
        )
    for error in result.validation_errors:
        st.error(f"草案校验未通过：{error}")
    with st.expander("本次模型调用审计信息", expanded=False):
        st.json(
            {
                "prompt_sha256": result.prompt_sha256,
                "requires_human_approval": result.requires_human_approval,
                "transmitted_metadata": result.transmitted_metadata,
                "provider_metadata": result.provider_metadata,
            }
        )


def _show_saved_design(revision: DraftRevisionRecord) -> None:
    """Render the persisted design even after session-state loss or restart."""
    spec = revision.spec
    sources = {
        RevisionSource.SYSTEM_INITIAL: "系统初始化设计",
        RevisionSource.AI_PROPOSAL: "人工智能结构化提案",
        RevisionSource.AI_CONVERSATION: "人工智能持续对话修订",
        RevisionSource.CONVERSATION_REVISION: "持续对话修订",
        RevisionSource.USER_EDIT: "人工字段编辑",
    }
    with st.container(border=True):
        st.markdown(f"#### 当前已保存研究设计 V{revision.version_number}")
        st.caption(
            f"来源：{sources.get(revision.source, '已保存设计')}；"
            f"状态：{_DRAFT_STATUS_ZH[revision.status]}。此面板从本地版本库恢复，刷新后仍可查看。"
        )
        st.markdown(f"**研究问题**：{research_question_zh(spec.question)}")
        st.markdown("**候选方法**：" + "、".join(format_method_label(m) for m in spec.candidate_methods))
        rows = [
            {"设计项目": "分析单位", "已保存设置": unit_label_zh(spec.analysis_unit)},
            {"设计项目": "处理变量", "已保存设置": field_label_zh(spec.treatment)},
            {"设计项目": "结果变量", "已保存设置": field_label_zh(spec.outcome)},
            {"设计项目": "处理前协变量", "已保存设置": "、".join(field_label_zh(c) for c in spec.covariates) or "未指定"},
            {"设计项目": "实体标识", "已保存设置": field_label_zh(spec.entity_id_column or "未设置")},
            {"设计项目": "观测日期", "已保存设置": field_label_zh(spec.time_column or "未设置")},
            {"设计项目": "首次处理日期", "已保存设置": field_label_zh(spec.treatment_time_column or "未设置")},
            {"设计项目": "聚类字段", "已保存设置": field_label_zh(spec.cluster_column or "未设置")},
            {"设计项目": "处理分配", "已保存设置": assignment_label_zh(spec.assignment_mechanism)},
            {"设计项目": "数据结构", "已保存设置": data_structure_label_zh(spec.data_structure)},
        ]
        if spec.pre_period_days and spec.post_period_days:
            rows.append({"设计项目": "相对时间窗口", "已保存设置":
                f"处理前第{spec.pre_period_days}日至第1日；处理当日至第{spec.post_period_days - 1}日（后窗共{spec.post_period_days}天）"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.markdown("**识别假设声明**：" + (
            "；".join(assumption_label_zh(a) for a in spec.identification_assumptions)
            or "尚未由人工声明"
        ))
        with st.expander("查看已保存的设计理由、诊断计划和审核事项", expanded=False):
            if revision.research_notes:
                _show_revision_research_notes(revision)
            else:
                st.caption("此版本未保存额外研究说明。")
        with st.expander("查看原始结构化设计（技术字段）", expanded=False):
            st.json(spec.model_dump(mode="json"), expanded=False)


def _show_data_audit(report: dict[str, object]) -> None:
    status = str(report.get("overall_status", "unknown"))
    if status == AuditStatus.BLOCK.value:
        st.error("数据审计发现阻断项：当前不能批准或执行该DID/事件研究草案。")
    elif status == AuditStatus.REVIEW.value:
        st.warning("数据结构可继续人工审核，但仍有必须由研究者确认的口径与识别风险。")
    else:
        st.success("本轮结构审计未发现阻断项；这不代表识别假设已经被验证。")

    metrics = st.columns(5)
    metrics[0].metric("用户数", f"{int(report.get('user_count', 0)):,}")
    metrics[1].metric("处理用户", f"{int(report.get('treated_user_count', 0)):,}")
    metrics[2].metric("从未处理用户", f"{int(report.get('never_treated_user_count', 0)):,}")
    metrics[3].metric("完整前窗用户", f"{int(report.get('complete_pre_window_users', 0)):,}")
    metrics[4].metric("完整后窗用户", f"{int(report.get('complete_post_window_users', 0)):,}")

    coverage = report.get("relative_day_coverage") or []
    if coverage:
        coverage_frame = pd.DataFrame(coverage).rename(
            columns={
                "relative_day": "相对处理日",
                "expected_treated_users": "应观察处理用户",
                "observed_users": "实际观察用户",
                "outcome_nonmissing_users": "结果非缺失用户",
                "row_coverage_rate": "记录覆盖率",
                "outcome_coverage_rate": "结果覆盖率",
            }
        )
        st.markdown("**相对处理日覆盖**")
        st.dataframe(coverage_frame, width="stretch", hide_index=True)

    checks = report.get("checks") or []
    if checks:
        status_zh = {
            AuditStatus.PASS.value: "通过（仅结构层面）",
            AuditStatus.REVIEW.value: "需人工审核",
            AuditStatus.BLOCK.value: "阻断",
        }
        check_rows = []
        for item in checks:
            if not isinstance(item, dict):
                continue
            check_rows.append(
                {
                    "检查项": item.get("label"),
                    "状态": status_zh.get(str(item.get("status")), item.get("status")),
                    "说明": str(item.get("summary", "")).replace("total_interactions", "总互动量").replace("user_id", "用户标识").replace("positivity", "重叠性").replace("SUTVA", "稳定处理与无干扰假设").replace("UGC", "用户生成内容平台"),
                    "证据": json.dumps(evidence_zh(item.get("evidence", {})), ensure_ascii=False),
                }
            )
        st.markdown("**审计检查表**")
        st.dataframe(pd.DataFrame(check_rows), width="stretch", hide_index=True)

    with st.expander("审计边界与完整JSON", expanded=False):
        for limitation in report.get("limitations") or []:
            st.markdown(f"- {limitation}")
        st.json(report, expanded=False)


@st.cache_data(show_spinner=False)
def _load_registered_frame(path: str, mtime_ns: int, expected_sha256: str) -> pd.DataFrame:
    source=Path(path)
    digest=hashlib.sha256()
    with source.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
    if digest.hexdigest()!=expected_sha256:
        raise ValueError('已登记数据文件指纹已改变；请重新核验并登记新的数据版本。')
    return pd.read_parquet(source)


def main() -> None:
    st.set_page_config(page_title="CausalOps", page_icon="📐", layout="wide")
    st.title("CausalOps · 因果研究工作台")
    st.caption("输入问题 → 设计研究 → 识别门控 → 人工确认 → 执行分析 → 自动报告")
    with st.expander("安全与结论边界", expanded=False):
        st.markdown(
            "原始数据行在本机处理。允许外发的摘要按模型配置发送；统计执行限于注册工具。"
            "识别或诊断失败会阻止执行或降低主张等级，显著性不能覆盖设计缺陷。"
        )

    st.subheader("1. 数据来源")
    registered=load_registered_catalog(Path(os.environ.get('CAUSALOPS_REAL_CATALOG',str(PROJECT_ROOT/'artifacts/registered-real-datasets.json'))))
    modes=["内置合成演示", "上传CSV/Parquet"]+(['已登记真实研究数据'] if registered else [])
    requested_dataset=st.query_params.get('dataset')
    source_mode = st.radio("选择数据来源", modes,index=2 if registered and requested_dataset else 0,horizontal=True)
    scenario: DemoScenario | None = None
    source_description = "uploaded local table"
    if source_mode == "内置合成演示":
        scenarios = get_demo_scenarios()
        selected_name = st.selectbox("演示场景", list(scenarios))
        scenario = scenarios[selected_name]
        frame = scenario.frame.copy()
        initial_spec = scenario.spec
        source_description = f"built-in deterministic scenario: {scenario.name}"
        st.info(scenario.description)
    elif source_mode=='已登记真实研究数据':
        by_id={item['id']:item for item in registered}
        ids=list(by_id)
        selected_id=st.selectbox('真实数据分析口径',ids,index=ids.index(requested_dataset) if requested_dataset in ids else 0,
                                 format_func=lambda value:by_id[value]['title'])
        entry=by_id[selected_id]
        path=Path(entry['path'])
        try:
            frame=_load_registered_frame(str(path),path.stat().st_mtime_ns,entry['parquet_sha256'])
            initial_spec=CausalSpec.model_validate(entry['spec'])
        except (ValueError,OSError) as exc:
            st.error(f'已登记数据未能加载：{exc}');return
        source_description=entry['title']
        st.info(entry['note'])
        st.caption('真实数据在E盘本地读取；原始CSV不修改，未通过网页上传。此次用户授权限定关联分析，不代表确认因果识别假设。')
        if not real_external_model_authorized(PROJECT_ROOT,entry['source_sha256']):
            st.info('真实数据的外部模型发送尚未取得明确授权。当前使用本地证据回答；统计结果、报告和问答保存仍可使用。')
        overview=PROJECT_ROOT/'artifacts/real-panel-20261030/真实微博全量分析与接入报告.html'
        if overview.is_file():
            st.download_button('下载真实数据全量对比报告',overview.read_bytes(),file_name=overview.name,mime='text/html')
    else:
        upload = st.file_uploader("上传数据（最大50MB）", type=["csv", "parquet", "pq"])
        if upload is None:
            st.info("请先上传CSV或Parquet文件。")
            return
        try:
            frame = load_uploaded_table(upload.getvalue(), upload.name)
        except Exception as exc:
            st.error(f"读取文件失败：{exc}")
            return
        initial_spec = None
        source_description = f"user-uploaded local file: {Path(upload.name).name}"

    st.session_state['causalops_external_model_allowed'] = (source_mode=='内置合成演示' or (
        source_mode=='已登记真实研究数据' and real_external_model_authorized(PROJECT_ROOT,entry['source_sha256'])))

    c1, c2 = st.columns(2)
    c1.metric("行数", f"{len(frame):,}")
    c2.metric("列数", len(frame.columns))
    st.code(" | ".join(map(str, frame.columns)), language=None)
    catalog = build_field_catalog(frame)
    with st.expander("查看统一字段目录", expanded=False):
        catalog_rows = []
        for item in catalog.values():
            catalog_rows.append(
                {
                    "字段": item.name,
                    "中文名称": item.label_zh,
                    "类型": item.semantic_type,
                    "原始类型": item.dtype,
                    "缺失数": item.missing_count,
                    "唯一值数": item.unique_count,
                    "处理前属性": item.measurement_timing,
                    "可作协变量": "是" if item.can_be_covariate else "否",
                    "说明": item.availability_reason,
                }
            )
        st.dataframe(pd.DataFrame(catalog_rows), width="stretch", hide_index=True)
    if st.checkbox("显示前5行（可能包含敏感字段）", value=False):
        st.dataframe(frame.head(), width="stretch")

    dataset_key = _dataset_content_fingerprint(frame)
    repository = ResearchRepository(UI_STATE_DB)
    research_session = repository.find_latest_session_by_dataset(dataset_key)
    if research_session is None or not research_session.current_draft_revision_id:
        preliminary_spec = initial_spec or _request_initial_spec(frame, dataset_key)
        if preliminary_spec is None:
            return
    if research_session is None:
        research_session = repository.create_session(
            title=source_description,
            dataset_fingerprint=dataset_key,
            row_count=len(frame),
            column_schema={str(name): str(dtype) for name, dtype in frame.dtypes.items()},
        )
    if research_session.current_draft_revision_id:
        current_revision = repository.get_revision(
            research_session.current_draft_revision_id
        )
        base_spec = current_revision.spec
    else:
        current_revision = repository.create_revision(
            research_session.session_id,
            preliminary_spec,
            source=RevisionSource.SYSTEM_INITIAL,
            change_reason="根据当前数据建立初始研究草案",
            activate=True,
            status=DraftStatus.PENDING_REVIEW,
        )
        research_session = repository.get_session(research_session.session_id)
        base_spec = current_revision.spec
    default_question = research_question_zh(base_spec.question)
    if st.session_state.get("causalops_dataset_key") != dataset_key:
        st.session_state["causalops_dataset_key"] = dataset_key
        st.session_state["causalops_research_session_id"] = research_session.session_id
        st.session_state["causalops_question"] = default_question
        st.session_state.pop("causalops_ai_proposal", None)
        st.session_state.pop("causalops_ai_context", None)
        st.session_state.pop("causalops_last_result", None)
        st.session_state["causalops_sensitive_columns"] = []
        _seed_editor_state(base_spec)

    current_revision = repository.get_revision(
        repository.get_session(research_session.session_id).current_draft_revision_id
    )
    if st.session_state.get("causalops_editor_revision_id") != current_revision.revision_id:
        # A candidate can become the active draft during a rerun.  Streamlit keeps
        # keyed widget values across reruns, so explicitly re-seed the editor from
        # the newly active revision; otherwise stale values look like unsaved edits
        # and incorrectly disable the audit/approval controls.
        _load_revision_into_editor(current_revision.spec, current_revision.revision_id)
    dataset_version = repository.get_dataset_version(current_revision.dataset_version_id)
    h1, h2, h3 = st.columns(3)
    h1.metric("研究会话", research_session.session_id[-8:])
    h2.metric("数据版本", f"D{dataset_version.version_number}")
    h3.metric(
        "当前草案",
        f"V{current_revision.version_number}｜{_DRAFT_STATUS_ZH[current_revision.status]}",
    )
    _show_research_history(repository, research_session.session_id)

    st.subheader("2. 问题理解与AI结构化提案")
    if "causalops_question" not in st.session_state:
        st.session_state["causalops_question"] = default_question
    question = st.text_area(
        "研究问题",
        height=90,
        key="causalops_question",
        help="问题文本会与字段名、字段类型、行数一起发送；数据行和样本值不会发送。",
    ).strip()
    # A Chinese display alias must not silently rewrite an approved English spec.
    if question == research_question_zh(base_spec.question):
        question = base_spec.question
    sensitive_columns = st.multiselect(
        "敏感字段标记（仅发送字段名，不发送字段值）",
        list(frame.columns),
        key="causalops_sensitive_columns",
        placeholder="请选择需要标记的字段",
    )
    _show_saved_design(current_revision)
    current_context = _context_fingerprint(frame, question)
    api_configured = bool(os.environ.get("DEEPSEEK_API_KEY")) and st.session_state.get('causalops_external_model_allowed',True)
    if not api_configured:
        st.info(
            '当前数据尚未授权向外部模型发送，使用本地模式；这不代表密钥失效。'
            if not st.session_state.get('causalops_external_model_allowed',True) else
            "尚未在当前进程配置 DEEPSEEK_API_KEY。可继续使用确定性流程；如需AI草案，请使用安全启动脚本。"
        )
    generate = st.button(
        "生成AI研究设计草案",
        disabled=(not api_configured or len(question) < 8),
        help="只生成提案，不运行SQL、不调用估计器、不接触数据行。",
    )
    if generate:
        with st.spinner("正在请求结构化草案并执行本地Schema与安全校验……"):
            proposal = generate_ai_proposal(
                frame,
                question=question,
                allowed_source_tables=["local_dataset"],
                sensitive_columns=[str(item) for item in sensitive_columns],
                client=None,
            )
        st.session_state["causalops_ai_proposal"] = proposal
        st.session_state["causalops_ai_context"] = current_context
        st.session_state["causalops_review_variables"] = False
        st.session_state["causalops_review_covariates"] = False
        st.session_state["causalops_review_assumptions"] = False
        if proposal.status == ProposalStatus.NEEDS_REVIEW and proposal.spec is not None:
            proposed_spec = proposal.spec.model_copy(update={"question": question})
            proposed_validation = validate_workflow(frame, proposed_spec)
            candidate_status = (
                DraftStatus.DRAFT
                if proposed_validation.decision.status == GateStatus.PASS
                and not proposed_validation.inspection["missing_required_columns"]
                else DraftStatus.NEEDS_REVISION
            )
            candidate = repository.create_revision(
                research_session.session_id,
                proposed_spec,
                source=RevisionSource.AI_PROPOSAL,
                change_reason="AI 生成研究设计候选草案",
                parent_revision_id=current_revision.revision_id,
                activate=False,
                status=candidate_status,
                research_notes={"proposal_result": proposal.model_dump(mode="json")},
            )
            st.session_state["causalops_candidate_revision_id"] = candidate.revision_id

    # Pending candidates survive browser refresh and process restarts as well.
    if not st.session_state.get("causalops_candidate_revision_id"):
        pending = [r for r in repository.list_revisions(research_session.session_id)
                   if r.parent_revision_id == current_revision.revision_id
                   and r.revision_id != current_revision.revision_id
                   and r.dataset_version_id == current_revision.dataset_version_id
                   and r.status in {DraftStatus.DRAFT, DraftStatus.NEEDS_REVISION}]
        if pending:
            st.session_state["causalops_candidate_revision_id"] = pending[-1].revision_id
    proposal = st.session_state.get("causalops_ai_proposal")
    if not isinstance(proposal, SpecProposalResult):
        saved_candidate_id = st.session_state.get("causalops_candidate_revision_id")
        if saved_candidate_id:
            try:
                saved_candidate = repository.get_revision(saved_candidate_id)
                payload = saved_candidate.research_notes.get("proposal_result")
                if payload and saved_candidate.spec.question == question:
                    proposal = SpecProposalResult.model_validate(payload)
                    st.session_state["causalops_ai_proposal"] = proposal
                    st.session_state["causalops_ai_context"] = current_context
            except (ResearchStateError, ValidationError):
                pass
    proposal_is_current = (
        isinstance(proposal, SpecProposalResult)
        and st.session_state.get("causalops_ai_context") == current_context
    )
    if isinstance(proposal, SpecProposalResult):
        if proposal_is_current:
            _show_proposal(proposal)
        else:
            st.warning("数据结构或研究问题已变化，原AI草案已失效；请重新生成后再审核。")

    candidate_id = st.session_state.get("causalops_candidate_revision_id")
    if candidate_id:
        try:
            candidate_revision = repository.get_revision(candidate_id)
            _candidate_review_panel(repository, candidate_revision)
        except ResearchStateError:
            st.session_state.pop("causalops_candidate_revision_id", None)

    _conversation_panel(
        repository,
        research_session.session_id,
        build_field_catalog(frame),
    )

    current_revision = repository.get_revision(
        repository.get_session(research_session.session_id).current_draft_revision_id
    )
    editor_initial = current_revision.spec
    spec = _design_editor(frame, editor_initial, question)
    if spec is None:
        return
    st.subheader("4. 确定性识别门控")
    validation = validate_workflow(frame, spec)
    unsaved_changes = spec.model_dump(mode="json") != current_revision.spec.model_dump(mode="json")
    if unsaved_changes:
        st.warning(
            "当前表单与已保存草案不同。修改尚未获得版本号，也不会继承原审批；"
            "请先保存为候选版本。"
        )
        saved_fields = current_revision.spec.model_dump(mode="json")
        edited_fields = spec.model_dump(mode="json")
        with st.expander("查看尚未保存的字段差异", expanded=False):
            st.dataframe(
                pd.DataFrame([
                    {"字段": name, "当前保存值": json.dumps(saved_fields[name], ensure_ascii=False),
                     "表单临时值": json.dumps(edited_fields[name], ensure_ascii=False)}
                    for name in saved_fields if saved_fields[name] != edited_fields[name]
                ]),
                hide_index=True,
                width="stretch",
            )
        st.button(
            f"放弃表单临时修改并重新载入 V{current_revision.version_number}",
            key=f"reset_editor_{current_revision.revision_id}",
            on_click=_load_revision_into_editor,
            args=(current_revision.spec, current_revision.revision_id),
            help="不会删除任何历史版本，只会丢弃当前页面中尚未保存的临时字段值。",
        )
        if st.button("将表单修改保存为候选版本"):
            candidate_status = (
                DraftStatus.DRAFT
                if validation.decision.status == GateStatus.PASS
                and not validation.inspection["missing_required_columns"]
                else DraftStatus.NEEDS_REVISION
            )
            candidate = repository.create_revision(
                research_session.session_id,
                spec,
                source=RevisionSource.USER_EDIT,
                change_reason="用户通过字段编辑器修改研究设计",
                parent_revision_id=current_revision.revision_id,
                activate=False,
                status=candidate_status,
            )
            st.session_state["causalops_candidate_revision_id"] = candidate.revision_id
            st.rerun()
    if validation.inspection["missing_required_columns"]:
        st.error(f"缺少字段：{validation.inspection['missing_required_columns']}")
    decision = validation.decision
    st.dataframe(pd.DataFrame([
        {"检查项": CHECK_LABELS.get(c.name, "领域检查"), "状态": status_label_zh(c.status),
         "说明": CHECK_MESSAGES.get(c.status.value, "需核对"), "是否阻断": "是" if c.blocking else "否"}
        for c in decision.checks
    ]), hide_index=True, width="stretch")
    with st.expander("查看原始识别门控记录（技术字段）", expanded=False):
        st.json(decision.model_dump(mode="json"), expanded=False)
    status = validation.decision.status
    if status == GateStatus.PASS:
        st.success(
            f"识别前置门控通过；路由方法：{format_method_label(decision.selected_method)}；"
            f"主张上限：{claim_label_zh(decision.claim_ceiling)}。"
        )
    elif status == GateStatus.NEEDS_REVIEW:
        st.warning("设计仍需人工补充，当前禁止自动执行。")
    else:
        st.error("识别门控失败，当前禁止执行。")

    stored_validation = validate_workflow(frame, current_revision.spec)
    selected_method_value = stored_validation.decision.selected_method.value
    did_audit_required = selected_method_value in {"did", "event_study"}
    latest_data_audit = None

    st.subheader("5. 数据质量与处理前窗口核验")
    st.caption(
        f"审计对象：V{current_revision.version_number} × D{dataset_version.version_number}。"
        "审计只检查数据结构、窗口覆盖与可诊断性，不估计因果效应，也不替代人工确认识别假设。"
    )
    if did_audit_required:
        latest_data_audit = repository.get_latest_data_audit(
            revision_id=current_revision.revision_id,
            dataset_version_id=current_revision.dataset_version_id,
        )
        run_audit = st.button(
            "运行数据质量与处理前窗口核验",
            help=(
                "结果将以不可变记录绑定当前已保存草案版本与数据集版本；"
                "页面中尚未保存的临时表单值不会进入本次审计。"
            ),
        )
        if run_audit:
            report = audit_did_panel(frame, current_revision.spec)
            repository.record_data_audit(
                session_id=research_session.session_id,
                revision_id=current_revision.revision_id,
                dataset_version_id=current_revision.dataset_version_id,
                audit_type=report.audit_type,
                status=report.overall_status.value,
                report=report.to_dict(),
            )
            st.rerun()
        if latest_data_audit is None:
            st.info("当前版本尚无数据审计记录。完成核验后才能进入批准环节。")
        else:
            st.caption(
                f"最新审计：{latest_data_audit.audit_id[-8:]}｜"
                f"状态：{status_label_zh(latest_data_audit.status)}｜{latest_data_audit.created_at}"
            )
            _show_data_audit(latest_data_audit.report)
    else:
        st.info("当前路由方法不是DID/事件研究；本阶段的处理前窗口核验不适用。")

    audit_allows_approval = (
        not did_audit_required
        or (
            latest_data_audit is not None
            and latest_data_audit.status != AuditStatus.BLOCK.value
        )
    )

    st.subheader("6. 版本化人工审核与执行")
    association_authorization = repository.get_association_authorization(current_revision.revision_id)
    association_mode = association_authorization is not None
    if association_mode:
        st.success('用户已明确授权当前版本进行仅关联分析。因果识别假设保持未确认，未代替人工批准因果研究设计。结果可在第7、8部分直接查看和讨论。')
    execution_capability = get_method_capability(
        stored_validation.decision.selected_method
    )
    if not execution_capability.executable:
        st.info(
            execution_capability.unavailable_reason
            or "当前路由方法尚未开放执行；可以继续完善研究设计，但不能运行分析。"
        )
    st.caption(
        f"当前审核对象：V{current_revision.version_number}；"
        f"数据版本：D{dataset_version.version_number}。审批不会自动传递给其他版本。"
    )
    checklist_prefix = f"approval_{current_revision.revision_id}"
    review_variables = st.checkbox(
        "我已核对研究问题、分析单位、处理变量、结果变量和必要时间字段。",
        key=f"{checklist_prefix}_variables",
    )
    review_covariates = st.checkbox(
        "我已确认协变量均在处理前确定，不含结果泄漏或处理后变量。",
        key=f"{checklist_prefix}_covariates",
    )
    review_assumptions = st.checkbox(
        "我理解随机化、可交换性、重叠性、无干扰和平行趋势不能由大模型代替确认。",
        key=f"{checklist_prefix}_assumptions",
    )
    review_complete = review_variables and review_covariates and review_assumptions
    approval_blockers = []
    if not review_complete:
        approval_blockers.append("三个审核项尚未全部勾选。")
    if unsaved_changes:
        approval_blockers.append("表单与当前保存版本不同：请查看第4部分的字段差异，并保存修改或重新载入当前版本。")
    if stored_validation.decision.status != GateStatus.PASS:
        approval_blockers.append("当前保存版本尚未通过识别前置门控，请查看第4部分。")
    if stored_validation.inspection["missing_required_columns"]:
        approval_blockers.append("数据缺少研究设计要求的字段。")
    if not execution_capability.executable:
        approval_blockers.append(execution_capability.unavailable_reason or "当前方法尚无执行器。")
    if not audit_allows_approval:
        approval_blockers.append("当前版本尚未完成数据核验，或最新审计存在阻断项，请查看第5部分。")
    if current_revision.status == DraftStatus.PENDING_REVIEW:
        if approval_blockers:
            st.info("暂不能批准的原因：\n" + "\n".join(f"- {item}" for item in approval_blockers))
        approve_revision = st.button(
            "批准当前草案版本",
            disabled=bool(approval_blockers),
        )
        if approve_revision:
            try:
                repository.approve_revision(
                    current_revision.revision_id,
                    approved_by="local_user",
                    checklist={
                        "variables": review_variables,
                        "covariates": review_covariates,
                        "assumptions": review_assumptions,
                    },
                )
                st.rerun()
            except ResearchStateError as exc:
                st.error(f"草案未批准：{exc}")
    elif current_revision.status == DraftStatus.APPROVED:
        st.success(f"V{current_revision.version_number} 已绑定当前数据版本并完成人工审批。")
    elif current_revision.status == DraftStatus.NEEDS_REVISION:
        st.warning("当前版本仍需修改；请通过对话或字段编辑器创建新的候选版本。")
    else:
        st.warning(f"当前版本状态为：{_DRAFT_STATUS_ZH[current_revision.status]}。")

    result_binding = (current_revision.revision_id, current_revision.dataset_version_id)
    if st.session_state.get("causalops_last_result_binding") != result_binding:
        st.session_state.pop("causalops_last_result", None)
        st.session_state.pop("causalops_known_effect", None)
        st.session_state["causalops_last_result_binding"] = result_binding
    if "causalops_last_result" not in st.session_state:
        restored_result = _restore_saved_result(repository, current_revision)
        if restored_result is not None:
            st.session_state["causalops_last_result"] = restored_result
            st.session_state["causalops_known_effect"] = scenario.known_effect if scenario else None

    execute = st.button(
        "重新运行已授权的关联分析" if association_mode else "运行白名单Agent",
        type="primary",
        disabled=(
            (current_revision.status != DraftStatus.APPROVED and not association_mode)
            or unsaved_changes
            or (stored_validation.decision.status != GateStatus.PASS and not association_mode)
            or stored_validation.decision.status == GateStatus.BLOCKED
            or not execution_capability.executable
            or not audit_allows_approval
        ),
    )
    if execute:
        try:
            with st.spinner("正在执行估计、诊断、证据记录和报告生成……"):
                runner = run_versioned_association_workflow if association_mode else run_versioned_workflow
                extra={}
                if association_mode and 'causalops_last_result' in st.session_state:
                    extra={'study_context':st.session_state['causalops_last_result'].bundle.evidence.get('study_context',{})}
                versioned_result = runner(
                    frame,
                    repository,
                    session_id=research_session.session_id,
                    revision_id=current_revision.revision_id,
                    output_dir=UI_OUTPUT_ROOT,
                    source_description=source_description,
                    data_kind="synthetic" if scenario else "user_provided",
                    **extra,
                )
                result = versioned_result.agent_result
            st.session_state["causalops_last_result"] = result
            st.session_state["causalops_known_effect"] = scenario.known_effect if scenario else None
        except UnsupportedMethodExecutionError as exc:
            st.error(str(exc))
        except ValueError as exc:
            st.error(f"分析未执行：{exc}")
        except Exception:
            error_id = uuid.uuid4().hex[:10]
            LOGGER.exception("CausalOps UI run failed; error_id=%s", error_id)
            st.error(
                f"分析未完成（错误编号：{error_id}）。请检查字段映射和数据格式；"
                "技术细节已记录在本地日志中。"
            )
    if "causalops_last_result" in st.session_state:
        _show_result(
            st.session_state["causalops_last_result"],
            st.session_state.get("causalops_known_effect"),
        )
        _show_result_qa(repository, research_session.session_id, st.session_state["causalops_last_result"])


def _show_result_qa(repository: ResearchRepository, session_id: str, result: AgentRunResult) -> None:
    st.header("8. 基于本次运行证据的结果问答")
    st.caption("可解释已计算的结果、诊断和窗口比较；新增计算须回到研究设计流程。回答不会接受、批准草案或执行分析。")
    st.caption("仅在配置且获得发送授权后，模型才会接收问题、同一运行的近期问答和汇总证据；不会自动读取原始数据行。")
    quality_root=PROJECT_ROOT/'artifacts/real-panel-20261030/answer-quality-review/round2'
    quality_json=quality_root/'quality-evaluation.json'
    if result.bundle.run_id=='c2bc5d6940bc4a0389daa1eeb0ecabc5' and quality_json.is_file():
        review=json.loads(quality_json.read_text(encoding='utf-8'))
        quality_html=quality_root/'用户问答检查与优化复测.html'
        st.info(f"问答质量已更新：复测正常问题 {review['metrics']['normal_passed']}/{review['metrics']['normal_cases']}；旧回答仍按原样保留。")
        if quality_html.is_file():
            st.download_button('下载问答检查与优化报告',quality_html.read_bytes(),
                               file_name='用户问答检查与优化复测.html',mime='text/html',
                               key='answer_quality_review_download')
    current_run = repository.get_analysis_run(result.bundle.run_id)
    runs = repository.list_analysis_runs(revision_id=current_run.revision_id,
                                        dataset_version_id=current_run.dataset_version_id)
    run_ids = [r.run_id for r in runs]
    selected = st.selectbox("选择要讨论的分析运行", run_ids,
                           index=run_ids.index(current_run.run_id),
                           format_func=lambda value: f"运行 {value[:12]}｜" + next(r.created_at for r in runs if r.run_id == value),
                           key=f"result_qa_run_{current_run.revision_id}")
    run = repository.get_analysis_run(selected)
    if selected != current_run.run_id:
        st.warning("当前讨论的是你在此处选择的历史运行；第7部分仍展示最新主分析结果。请以这里显示的运行编号核对引用。")
    revision = repository.get_revision(run.revision_id)
    dataset = repository.get_dataset_version(run.dataset_version_id)
    st.info(f"问答绑定：草案 V{revision.version_number} × 数据 D{dataset.version_number} × 运行 {selected[:12]}。切换运行后，下方证据和对话会一起切换。")
    model = None
    if os.environ.get("DEEPSEEK_API_KEY") and st.session_state.get('causalops_external_model_allowed',True):
        model = DeepSeekStructuredModelClient(max_output_tokens=4096)
    service = ResultQAService(repository, model)
    try:
        bundle, snapshot = service.prepare(session_id=session_id, run_id=selected)
    except (ValueError, OSError) as exc:
        st.error(f"结果证据不可用：{exc}")
        return
    facts = {f["evidence_id"]: f for f in snapshot["facts"]}
    st.caption(f"证据快照：{snapshot['snapshot_id'][:16]}｜结论等级：{claim_label_zh(bundle.claim_level)}。只向模型提供白名单汇总证据，不发送数据行。")
    with st.expander("运行级证据清单与引用位置"):
        st.dataframe(pd.DataFrame([{"引用编号": f["evidence_id"], "证据名称": f["label"],
                                    "已记录事实": f["text_zh"], "原始证据位置": f["pointer"]}
                                   for f in snapshot["facts"]]), hide_index=True)
    with st.expander("详细解释、综合结论与后续建议", expanded=False):
        for title, paragraphs in conclusion_sections(bundle):
            st.subheader(title)
            for paragraph in paragraphs:
                st.write(paragraph)
    st.caption('可直接问：当前系数对应多少个百分点？原始数据和估计样本为什么不同？为什么不能直接说因果？'
               if bundle.plan.selected_method==CausalMethod.REGRESSION_ADJUSTMENT else
               "可直接问：这个估计值怎么理解？主分析显著是否说明平行趋势成立？窗口比较说明什么？能否外推到真实平台？")
    old_turns = repository.list_previous_result_qa_turns(run_id=selected, exclude_snapshot_id=snapshot["snapshot_id"])
    if old_turns:
        with st.expander("历史解释版本的对话（原样保留，仅供回看）"):
            st.caption("旧版本不会混入新问答上下文；旧回答仍以当时的证据和解释规则为准。")
            for old_turn in old_turns:
                st.write("问题：" + old_turn['question'])
                for old_section in old_turn['answer']['sections']:
                    st.markdown('**'+old_section['title']+'**')
                    st.write(old_section['text'])
    turns = repository.list_result_qa_turns(run_id=selected, snapshot_id=snapshot["snapshot_id"])
    legacy_count=sum(turn['origin']=='user' and turn['answer'].get('pipeline_version')!=ANSWER_PIPELINE_VERSION for turn in turns)
    if legacy_count:
        st.caption('历史回答按原样保留。标为“旧版”的内容可能重复或跑题；新提问使用已优化的问题匹配与引用校验流程。')
    evaluation_count = sum(turn["origin"] == "acceptance_test" for turn in turns)
    if evaluation_count:
        show_evaluations = st.checkbox(f"显示自动验收对话（{evaluation_count}条，含失败与拦截记录）",
                                      key=f"result_qa_evaluations_{selected}")
        if not show_evaluations:
            turns = [turn for turn in turns if turn["origin"] != "acceptance_test"]
    for turn in turns:
        with st.chat_message("user"):
            st.write(turn["question"])
        answer = turn["answer"]
        with st.chat_message("assistant"):
            if answer["used_model"]:
                version_label='当前优化版' if answer.get('pipeline_version')==ANSWER_PIPELINE_VERSION else '旧版回答，原始记录'
                st.caption("DeepSeek 解释｜"+version_label+"｜本地引用校验通过｜数值来自保存的运行证据")
            else:
                st.warning(answer.get("notice") or "本轮为本地证据摘要，未使用模型回答。")
            for section in answer["sections"]:
                st.markdown(f"**{section['title']}**")
                st.write(section["text"])
            with st.expander("核对本条回答的引用"):
                for key in answer["citation_ids"]:
                    fact = facts[key]
                    st.write(f"〔{key}〕{fact['text_zh']}")
                    st.caption(f"证据位置：{fact['pointer']}")
                if answer.get("telemetry"):
                    st.caption("调用记录：" + json.dumps(answer["telemetry"], ensure_ascii=False))
    with st.form(f"result_qa_form_{selected}", clear_on_submit=True):
        question = st.text_area("围绕本次运行提问", key=f"result_qa_question_{selected}",
                                placeholder="例如：主分析系数和处理前联合检验分别说明什么？")
        submit = st.form_submit_button("发送结果问题")
    if submit:
        try:
            with st.spinner("正在核对本次运行证据并生成解释……"):
                service.ask(session_id=session_id, run_id=selected, question=question)
            st.rerun()
        except (ValueError, OSError) as exc:
            st.error(f"问题未发送：{exc}")


if __name__ == "__main__":
    main()
