"""Minimal user-operated decision panel inside the existing diagnostic snapshot."""
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
from causalops.application.diagnostics.decisions import ResearchDecisionService
from causalops.application.diagnostics.decision_contracts import TYPE_LABELS
from causalops.application.diagnostics.workbench import safe_error
from causalops.application.diagnostics.report_contracts import STATE_LABELS

ERRORS=(ValueError,RuntimeError,OSError,KeyError)

def _when(value):
    return datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M:%S")

def _form(m,mode,subject,view,rows,suggestion=None):
    r=view.report;sid=suggestion.suggestion_id if suggestion else None;token=r.report_id+"_"+(sid or "note")
    current=[e for e in rows if e.origin_verified and not e.superseded_by and e.decision.report_id==r.report_id
             and e.decision.suggestion_id==sid]
    previous=current[-1].decision if current else None
    if suggestion:
        st.write(suggestion.action)
        st.caption("依据诊断："+suggestion.rule_id+" · "+suggestion.diagnostic_id+"；只记录用户决定，不改变检查状态。")
        options=["","accepted","deferred","rejected"]
        kind=st.selectbox("对建议的决定",options,index=options.index(previous.decision_type) if previous else 0,
            format_func=lambda v:TYPE_LABELS.get(v,"请选择决定"),key="decision_type_"+token,disabled=not view.source_current)
    else:
        st.caption("即使没有后续建议，也可记录本报告的解释边界或其他研究决定。备注是用户意见，不会成为诊断事实。")
        kind="note"
    replace=None
    if suggestion and previous:
        replace=previous.decision_id
        st.caption("当前记录："+replace+"。修改后将追加修订，保留原决定；相同提交返回原记录。")
    else:
        eligible=[e.decision for e in rows if m.can_supersede(e,r,sid)]
        byid={x.decision_id:x for x in eligible}
        replace=st.selectbox("修订历史决定（可选）",[""]+list(byid),
            format_func=lambda v:"不修订，记录本次新决定" if not v else TYPE_LABELS[byid[v].decision_type]+" · 报告v"+str(byid[v].report_version)+" · "+v[:12],
            key="decision_replace_"+token,disabled=not view.source_current) or None
        if replace:st.caption("将追加一条明确指向该历史记录的修订，不覆盖原文。")
    confirmed=st.checkbox("我确认仅记录研究决定，不批准或执行统计",key="decision_confirm_"+token,disabled=not view.source_current)
    with st.form("decision_form_"+token):
        reason=st.text_area("决策原因或研究备注",value=previous.reason if previous else "",max_chars=2000,key="decision_reason_"+token)
        submitted=st.form_submit_button("保存研究决定",key="decision_save_"+token,
            disabled=not confirmed or not kind or not view.source_current)
        if submitted:
            try:
                saved=m.save(mode,subject,r.report_id,kind,reason,suggestion_id=sid,supersedes_id=replace,human_confirmed=confirmed)
                st.session_state["decision_saved_"+r.report_id]=saved.decision_id
                st.rerun()
            except ERRORS as exc:st.error("研究决定未保存："+safe_error(exc))

def render_memory(w,mode,subject,view):
    r=view.report
    st.html('<div class="co-decision-memory" data-task-id="'+escape(subject)+'" data-report-id="'+r.report_id+'">研究决定 · 用户记录 · 无统计执行权限</div>')
    try:
        m=ResearchDecisionService(w);rows=m.history(mode,subject)
    except ERRORS as exc:
        st.error("研究决策历史读取失败："+safe_error(exc));return
    st.subheader("相关历史提醒")
    try:
        reminders=m.reminders(mode,subject,r.report_id)
        if not reminders:st.info("暂无可对应的历史问题；自主研究备注只在历史中展示，不自动解读。")
        for item in reminders:
            with st.container(key="decision_reminder_"+item.decision_id+"_"+r.report_id):
                st.html('<span class="decision-reminder" data-kind="'+item.kind+'" data-decision-id="'+item.decision_id+'"></span>')
                if item.kind=="current_verified":st.success(item.rule_id+"："+item.message)
                elif item.kind in ("needs_review","changed"):st.warning(item.rule_id+"："+item.message)
                else:st.info(item.rule_id+"："+item.message)
                st.caption("历史决定："+item.decision_id+"；原报告："+item.prior_report_id+"；当前报告："+item.current_report_id)
                if item.current_status:st.caption("当前检查状态："+STATE_LABELS[item.current_status]+"。状态来自当前报告，不来自用户决定。")
    except ERRORS as exc:st.error("历史问题未能核对："+safe_error(exc))
    st.subheader("记录研究决定")
    st.caption("诊断 → 建议 → 用户研究决定 → 研究需求草案 → 正式计划 → 批准 → 统计运行，是独立状态。本区不创建草案、计划、批准或统计。")
    saved=st.session_state.get("decision_saved_"+r.report_id)
    if saved:st.success("已保存研究决定："+saved+"。重复提交幂等；如该记录已有后继修订，以历史关系为准。")
    if not view.source_current:st.warning("当前报告来源已变化；历史可以查看，但不能据此新增决定。请先显式重新检查。")
    if not r.suggestions:st.info("本报告没有后续建议，可以在下方记录自主研究决定。")
    for i,suggestion in enumerate(r.suggestions,1):
        with st.expander("对建议作出决定 · "+str(i)+" · "+suggestion.rule_id,expanded=True):
            _form(m,mode,subject,view,rows,suggestion)
    with st.expander("自主研究决定",expanded=not bool(r.suggestions)):
        _form(m,mode,subject,view,rows)
    st.subheader("研究决策历史")
    try:rows=m.history(mode,subject)
    except ERRORS as exc:st.error("历史记录未能刷新："+safe_error(exc));return
    if not rows:st.info("尚无研究决定；只有明确提交才会保存。")
    for entry in reversed(rows):
        d=entry.decision
        with st.expander(_when(d.created_at)+" · "+TYPE_LABELS[d.decision_type]+" · 报告v"+str(d.report_version)+" · "+d.decision_id[:12],expanded=True):
            st.text(d.reason or "未填写原因")
            if d.suggestion_action:st.write("当时建议："+d.suggestion_action)
            st.caption("决定："+d.decision_id+"；所属任务："+d.context.task_ref.task_id)
            st.caption("关联报告："+d.report_id+"；诊断快照："+d.assessment_id)
            c=d.context
            st.caption("数据："+(c.data_ref.frame_sha if c.data_ref else "未登记")+"；合同版本："+(str(c.contract_ref.version) if c.contract_ref else "无")+"；计划版本："+(str(c.plan_ref.version) if c.plan_ref else "无"))
            if c.run_refs:st.caption("原运行："+"、".join(x.run_id for x in c.run_refs))
            st.caption("来源：用户主动提交；执行权限：无。关联的是原版本，不能自动当作当前事实或批准。")
            if d.supersedes_id:st.caption("明确修订原决定："+d.supersedes_id)
            if entry.superseded_by:st.warning("该记录已有后继修订："+entry.superseded_by+"；原文仍保留。")
            if not entry.origin_verified:st.warning(entry.origin_error)
            with st.expander("查看决定依据 · "+d.decision_id[:12]):
                st.json({"report_id":d.report_id,"report_sha":d.report_sha,"assessment_sha":d.assessment_sha,
                    "scope":d.context.scope.model_dump(mode="json"),"rule":d.rule.model_dump(mode="json") if d.rule else None,
                    "original_finding_status":d.finding_status,"evidence":[x.model_dump(mode="json") for x in d.evidence_refs],
                    "source_checked_at":d.source_checked_at,"execution_authorized":False})
