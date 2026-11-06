"""Evidence-bound diagnostics page. Every write requires a visible explicit operation."""
from __future__ import annotations
from html import escape as e
import streamlit as st
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.application.diagnostics.workbench import DiagnosticWorkbench,safe_error
from causalops.application.diagnostics.report_contracts import STATE_LABELS
from causalops.application.automation_results import STATES

NAMES={"PD-01":"身份与证据完整性","PD-02":"随机分配依据记录","PD-06":"观察窗口",
       "PD-07":"双运行与上游门禁","PD-09":"指标与单位数值链","PD-14":"步骤与报告来源"}
ORIGINS={"program_fact":"程序事实","human_declaration":"人工声明核对","mixed":"程序与人工来源"}
LEVELS={"critical":"限制相关结论","major":"需要核对关键条件","moderate":"需要关注","information":"说明"}
MODES={"preflight":"执行前 · 研究条件","post_run":"执行后 · 研究证据"}

def open_diagnostics(mode="preflight",identifier=""):
    st.query_params.update(route="evidence",diagnostic_mode=mode,diagnostic_task=identifier)
    st.query_params.pop("diagnostic_report",None)
    st.session_state["showcase_route"]="evidence"

def _select(mode,subject,report=""):
    st.query_params.update(diagnostic_mode=mode,diagnostic_task=subject)
    if report:st.query_params["diagnostic_report"]=report
    else:st.query_params.pop("diagnostic_report",None)

def ordered_findings(report):
    def key(f):
        category=0 if f.status=="issue" else 1 if f.status=="unknown" else 2 if f.status=="verified" else 3
        level={"critical":0,"major":1,"moderate":2,"information":3}[f.severity.level]
        return category,level,f.rule.id
    return sorted(report.quality.findings,key=key)

def _fmt(value):
    return e(str(value)) if value is not None else "尚未登记"

def report_html(view):
    r=view.report;c=r.context;scope=r.results.scope
    header=f'<article class="co-diagnostic-snapshot" data-report-id="{r.report_id}" data-task-id="{c.task_ref.task_id}" data-session-id="{c.task_ref.session_id}" data-assessment-id="{r.assessment_id}">'
    parts=[header,'<header><h2>研究结果与证据报告</h2>',
        f'<p>报告版本 {r.version} · 生成于 {_fmt(r.created_at)} · 模型解释关闭</p>',
        f'<div class="diag-identity">研究任务：<code>{c.task_ref.task_id}</code><br>诊断报告：<code>{r.report_id}</code><br>诊断快照：<code>{r.assessment_id}</code></div></header>']
    if c.plan_ref:
        parts.append('<p class="diag-identity">正式计划：<code>'+e(c.plan_ref.id)+'</code> · v'+str(c.plan_ref.version)+'</p>')
    if not view.source_current:
        parts.append('<div class="diag-block" role="alert"><b>来源已变化或当前无法核验</b><br>'+e(view.source_error or "请重新检查。")+'<br>原快照保留；当前不展示联合数值，也不能据此保存新需求草案。</div>')
    parts.append('<section><h3>研究风险摘要</h3>')
    if r.results.status=="restricted":
        parts.append('<div class="diag-block"><b>当前证据限制联合结论</b>。以下按确定性规则显示冲突与原因，不使用其他任务的成功报告补数。</div>')
    parts.append('<ul class="diag-risks">')
    for f in ordered_findings(r)[:3]:
        parts.append(f'<li><b>{STATE_LABELS[f.status]}</b> · {NAMES[f.rule.id]} · {LEVELS[f.severity.level]}<p>{e(f.impact.explanation)}</p><a href="#finding-{f.finding_id}">查看依据</a></li>')
    parts.append('</ul><p class="diag-note">范围限于六项已实现规则。来源声明核对不等于证明随机分配过程或全部研究假设。</p></section>')
    parts.append('<section><h2>第一层 · 研究结果</h2>')
    parts.append('<dl class="diag-scope">'+''.join(f'<div><dt>{name}</dt><dd>{_fmt(value)}</dd></div>' for name,value in [
        ("研究问题",r.results.objective or "已登记数据的研究条件核查；尚无正式研究方案"),
        ("分析对象",scope.get("analysis_unit")),("目标指标",scope.get("metric_label") or scope.get("outcome_field")),
        ("指标字段",scope.get("outcome_field")),("指标单位",scope.get("unit")),("观察窗口",scope.get("observation_window")),
        ("比较对象"," / ".join(scope.get("group_labels") or []) or "尚未登记业务组名"),
        ("计划版本","v"+str(c.plan_ref.version) if c.plan_ref else "尚无正式计划"),
        ("批准版本","计划v"+str(r.results.approval["plan_version"]) if r.results.approval else "尚无可引用批准"),
    ])+'</dl>')
    if view.source_current and r.results.status=="available":
        effect=r.results.effect;labels=scope.get("group_labels") or ["对照组","处理组"];ci=effect["ci_pp"]
        parts.append('<div class="diag-metrics">'+''.join(f'<div><small>{e(label)}</small><strong>{e(value)}</strong></div>' for label,value in [
            (labels[0]+"访问率",f'{effect["control_rate"]:.2%}'),(labels[1]+"访问率",f'{effect["treated_rate"]:.2%}'),
            ("绝对差异",f'{effect["pp"]:.2f} 个百分点'),("原95%区间",f'[{ci[0]:.3f}, {ci[1]:.3f}] 个百分点')
        ])+'</div>')
        parts.append(f'<p>本次分析包含 <b>{r.results.sample_size:,}</b> 名客户；使用原 A/B 工具的组间均值差与原区间。访问率差不等于相对增长，也不能直接解释为长期利润。</p>')
        parts.append('<table><thead><tr><th>比较组</th><th>实际样本</th><th>访问率</th></tr></thead><tbody>')
        for g in r.results.group_summary:
            label=labels[int(g["treatment"])]
            parts.append(f'<tr><td>{e(label)}</td><td>{g["n"]:,}</td><td>{g["outcome_mean"]:.2%}</td></tr>')
        parts.append('</tbody></table>')
    else:
        label={"not_run":"尚无正式统计运行","partial":"研究部分完成","restricted":"联合统计结论受到限制","available":"历史数值暂不作为当前结论"}[r.results.status]
        parts.append('<div class="diag-info"><b>'+label+'</b>。不补写估计值或区间；可核对下方研究条件及保存时的证据引用。</div>')
    if r.results.runs:
        parts.append('<div class="diag-identity">'+'<br>'.join(('描述统计' if x["kind"]=="exploration" else "效果分析")+' Run：<code>'+e(x["run_id"])+'</code>' for x in r.results.runs)+'</div>')
    if r.results.approval:parts.append('<p class="diag-note">原批准：<code>'+e(r.results.approval["id"])+'</code>。历史回执不授予新的执行权限。</p>')
    if c.data_ref:
        parts.append('<p class="diag-note">数据版本：<code>'+e(c.data_ref.frame_sha)+'</code>；合同：'+(_fmt(c.contract_ref.id)+" / v"+str(c.contract_ref.version) if c.contract_ref else "尚未登记")+'</p>')
    observed=r.results.design_observations
    if c.phase=="preflight":
        parts.append('<p>分组字段：'+("实际存在" if observed.get("group_field_present") else "尚未确认或未登记")+'；非空组数：'+_fmt(observed.get("nonmissing_group_count"))+'。存在两组不是随机分配依据。</p>')
    parts.append('</section><section><h2>第二层 · 证据质量</h2><p>以下状态来自已保存诊断；不计算研究可信度总分。</p>')
    parts.append('<table><thead><tr><th>已实现检查</th><th>实际状态</th><th>重要程度与来源</th><th>对结论的影响</th></tr></thead><tbody>')
    for f in r.quality.findings:
        parts.append('<tr><td>'+e(f.rule.id+" "+NAMES[f.rule.id])+'</td><td>'+STATE_LABELS[f.status]+'</td><td>'+LEVELS[f.severity.level]+'<br><small>'+ORIGINS[f.source.origin]+'</small></td><td>'+e(f.impact.explanation)+'</td></tr>')
    parts.append('</tbody></table><div class="diag-info"><b>未实现的八项规则</b>：'+e("、".join(r.quality.unimplemented_rules))+'。没有将这些项目计为通过，也没有据此判定研究违规。</div>')
    parts.append('<p class="diag-note">未实施完整的基线、功效、无干扰、外推或长期收益检验。当前仅显示已有六项规则的实际结果。</p></section>')
    parts.append('<section><h2>第三层 · 下一步研究建议</h2>')
    if not r.suggestions:parts.append('<div class="diag-info">当前检查未生成后续建议。</div>')
    for s in r.suggestions:
        parts.append('<div class="diag-action"><b>'+e(s.action)+'</b><p>原因：'+e(s.reason)+'</p><p>需补充：'+e("；".join(s.required_evidence))+'</p><p class="diag-note">来源：'+e(s.rule_id)+' / <code>'+e(s.diagnostic_id)+'</code><br>如涉及新范围，必须另行生成受支持的待审方案并人工审核。该建议没有执行权限。</p></div>')
    parts.append('<p class="diag-note">诊断建议 → 研究需求草案 → 正式待审方案 → 已批准计划 → 真实统计运行，是不同状态。此页只能查看诊断和保存需求，不创建批准或派发统计。</p></section></article>')
    return "".join(parts)

CSS="""<style>
.co-diagnostic-snapshot{color:#234144;font:15px/1.75 "Microsoft YaHei",sans-serif}
.co-diagnostic-snapshot header{padding:20px;border:1px solid #cbded9;border-left:4px solid #167568;border-radius:8px;background:#f7faf9}
.co-diagnostic-snapshot h2{font-size:22px;color:#155f58;margin:0 0 14px}
.co-diagnostic-snapshot h3{font-size:18px;color:#284c48;margin:0 0 12px}
.co-diagnostic-snapshot section{border:1px solid #dce6e3;border-radius:8px;background:white;padding:22px;margin:18px 0}
.co-diagnostic-snapshot .diag-identity{font-size:12px;overflow-wrap:anywhere;color:#5c7474;margin:12px 0}
.diag-selection{color:#657a7b;font-size:13px}
.co-diagnostic-snapshot .diag-note{font-size:12px;color:#657a7b}
.co-diagnostic-snapshot .diag-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:20px 0}
.co-diagnostic-snapshot .diag-metrics small{display:block;color:#617b78}
.co-diagnostic-snapshot .diag-metrics strong{display:block;font-size:22px;color:#146c62}
.co-diagnostic-snapshot .diag-block{border-left:4px solid #a54b42;background:#fff4f1;padding:14px;margin:16px 0}
.co-diagnostic-snapshot .diag-info{padding:13px;background:#f1f6f4;border:1px solid #d9e7e1;border-radius:5px;margin:12px 0}
.co-diagnostic-snapshot table{width:100%;border-collapse:collapse;font-size:13px}
.co-diagnostic-snapshot th,.co-diagnostic-snapshot td{border-bottom:1px solid #dce6e2;padding:12px;text-align:left;vertical-align:top}
.co-diagnostic-snapshot th{background:#f2f7f5}.co-diagnostic-snapshot code{overflow-wrap:anywhere}
.co-diagnostic-snapshot .diag-scope{display:grid;grid-template-columns:1fr 1fr;gap:9px 24px}
.co-diagnostic-snapshot .diag-scope div{display:grid;grid-template-columns:90px 1fr;border-bottom:1px solid #edf1ef;padding:6px}
.co-diagnostic-snapshot dt{color:#667b79}.co-diagnostic-snapshot dd{margin:0;overflow-wrap:anywhere}
.co-diagnostic-snapshot .diag-risks{padding-left:20px}.co-diagnostic-snapshot .diag-risks li{padding:8px 0}
.co-diagnostic-snapshot .diag-risks p{margin:3px 0}.co-diagnostic-snapshot a{color:#146d64}
.co-diagnostic-snapshot .diag-action{padding:14px;border:1px solid #d8e4df;border-radius:6px;margin:12px 0}
[data-stale="true"] .co-diagnostic-snapshot{visibility:hidden}
[data-stale="true"] [class*="st-key-diagnostic_snapshot_"],[data-stale="true"][class*="st-key-diagnostic_snapshot_"]{visibility:hidden;pointer-events:none}
@media(max-width:700px){.co-diagnostic-snapshot .diag-metrics,.co-diagnostic-snapshot .diag-scope{grid-template-columns:1fr 1fr}.co-diagnostic-snapshot section{padding:14px}.co-diagnostic-snapshot table{display:block;overflow:auto}.co-diagnostic-snapshot .diag-scope div{display:block}}
</style>"""

def _forms(w,mode,subject,view):
    r=view.report
    st.subheader("查看依据与研究需求")
    st.caption("下列回执属于本报告生成时点；来源变化不会改写历史记录，也不会取得执行权限。")
    for f in ordered_findings(r):
        st.markdown('<span id="finding-'+f.finding_id+'"></span>',unsafe_allow_html=True)
        with st.expander("查看依据 · "+f.rule.id+" "+NAMES[f.rule.id]):
            st.write(STATE_LABELS[f.status]+" · "+ORIGINS[f.source.origin]+" · "+LEVELS[f.severity.level])
            st.write(f.impact.explanation)
            st.caption("规则版本："+f.rule.version+"；原因码："+f.result.reason_code)
            if f.result.missing_items:st.write("缺少证据："+"；".join(f.result.missing_items))
            if f.result.required_work:st.write("核查事项："+"；".join(f.result.required_work))
            try:st.json(w.evidence(mode,subject,r.report_id,f.finding_id))
            except (ValueError,OSError,RuntimeError,KeyError) as exc:st.error("检查回执读取失败："+safe_error(exc))
    if r.results.status=="available":
        if st.button("查看两个 Run 与原报告的运行证据",key="diag_original_"+r.report_id,disabled=not view.source_current):
            try:st.json(w.original_evidence(mode,subject,r.report_id))
            except (ValueError,OSError,RuntimeError,KeyError) as exc:st.error(safe_error(exc))
    try:
        existing_drafts=w.drafts(mode,subject,r.report_id)
    except (ValueError,OSError,RuntimeError,KeyError) as exc:
        st.error("已有草案读取失败："+safe_error(exc));existing_drafts=[]
    saved_intents={}
    for draft in existing_drafts:
        saved_intents.setdefault(draft.suggestion_id,draft.user_intent)
    for index,s in enumerate(r.suggestions,1):
        with st.expander("保存需求 · 建议"+str(index),expanded=True):
            st.write("**"+s.action+"**")
            st.write("依据："+s.rule_id+" / "+s.diagnostic_id)
            st.write("需要补充："+"；".join(s.required_evidence))
            st.caption("本次只记录研究意图、证据缺口和来源。正式研究范围变化必须另行制定方案并人工审核。")
            confirmed=st.checkbox("我确认只保存研究需求草案，不批准或执行统计",key="diag_confirm_"+r.report_id+"_"+s.suggestion_id)
            with st.form("diag_form_"+r.report_id+"_"+s.suggestion_id):
                intent=st.text_area("研究需求说明",value=saved_intents.get(s.suggestion_id,s.action),max_chars=2000,key="diag_intent_"+r.report_id+"_"+s.suggestion_id)
                submitted=st.form_submit_button("保存为研究需求草案",key="diag_save_"+r.report_id+"_"+s.suggestion_id,
                    disabled=not confirmed or not view.source_current)
                if submitted:
                    try:
                        draft=w.save(mode,subject,r.report_id,s.suggestion_id,intent,confirmed=confirmed)
                        st.success("已保存研究需求草案："+draft.draft_id+"。没有创建批准或执行统计。")
                    except (ValueError,OSError,RuntimeError,KeyError) as exc:st.error("草案未保存："+safe_error(exc))
    try:drafts=w.drafts(mode,subject,r.report_id)
    except (ValueError,OSError,RuntimeError,KeyError) as exc:
        st.error("已有草案读取失败："+safe_error(exc));drafts=[]
    if drafts:
        st.subheader("本报告已保存的研究需求草案")
        st.caption("研究需求草案 · 待补充资料 · 无执行权限；不是正式待审方案或已批准计划。")
        for d in drafts:
            with st.expander("研究需求草案 · "+d.draft_id[:12],expanded=True):
                st.write(d.user_intent)
                st.caption("草案编号："+d.draft_id+"；来源报告："+d.report_id)
                st.write("状态：待补充资料；执行权限：无。")
                st.download_button("导出研究需求草案",d.model_dump_json(indent=2).encode("utf8"),
                    file_name="CausalOps_研究需求草案.json",mime="application/json",key="diag_export_draft_"+d.draft_id)

def render():
    st.html(CSS)
    st.title("研究证据诊断",anchor=False)
    st.caption("显式触发、本地只读核验、模型解释关闭。历史诊断与研究计划、批准和统计运行分别保存。")
    # Stable sibling slots: clear the prior report before selection/URL changes.
    # A source check or widget rerun can never label old body text with a new task.
    controls=st.container(key="diagnostic_controls")
    output=st.empty()
    with controls:
        w=DiagnosticWorkbench(ResearchService(AssistantWorkspace()))
        mode=st.query_params.get("diagnostic_mode","preflight")
        if mode not in MODES:mode="preflight"
        picked=st.radio("诊断阶段",list(MODES),index=list(MODES).index(mode),format_func=MODES.get,horizontal=True,key="diag_mode_"+mode)
        if picked!=mode:
            _select(picked,"");st.rerun()
        items=w.subjects(mode)
        if not items:
            st.info("当前没有可诊断的任务。请先登记数据；执行后诊断需要已有的自动化研究任务。")
            return
        byid={x["id"]:x for x in items}
        selected=st.query_params.get("diagnostic_task","")
        if selected and selected not in byid:
            st.error("所选任务不存在或不属于当前范围，未替换为其他任务。");return
        def label(value):
            if not value:return "请选择研究任务"
            item=byid[value]
            return item["title"]+" · "+STATES.get(item["status"],item["status"])+" · "+value[:8]
        options=[""]+list(byid)
        choice=st.selectbox("诊断任务",options,index=options.index(selected),format_func=label,key="diag_subject_"+mode+"_"+selected)
        if choice!=selected:
            _select(mode,choice);st.rerun()
        st.html('<p class="diag-selection" data-mode="'+mode+'" data-task="'+e(selected)+'">检查范围：'+("已登记数据与研究合同" if mode=="preflight" else "本任务已保存的五步研究证据")+'</p>')
        if not selected:
            st.info("请明确选择任务。页面不会自动借用最近运行或其他任务的报告。");return
        st.caption("执行前只读取登记数据与合同；执行后仅引用本任务固定五步保存的证据。更换指标、窗口或方法仍需正式研究流程。")
        check="检查研究条件" if mode=="preflight" else "检查研究证据"
        if st.button(check,key="diag_check_"+mode+"_"+selected,type="primary"):
            try:
                output.info("正在核对当前选择；旧报告暂不展示。不会执行统计。")
                with st.spinner("正在核对已保存证据，不执行统计…"):
                    report=w.create(mode,selected)
                _select(mode,selected,report.report_id);st.rerun()
            except (ValueError,OSError,RuntimeError,KeyError) as exc:
                output.empty()
                st.error("本次检查未完成："+safe_error(exc))
                st.info("未使用其他任务的结果。已有研究与报告保留；请核对数据、合同或原生工件后显式重试。")
                return
        try:history=w.history(mode,selected)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:
            st.error("历史诊断目录读取失败："+safe_error(exc));return
        report_id=st.query_params.get("diagnostic_report","")
        byreport={x["id"]:x for x in history}
        history_ids=[""]+list(byreport)
        if report_id and report_id not in byreport:
            st.error("所选诊断报告不存在、版本不匹配或不属于当前任务；未打开其他历史成功报告。");return
        history_choice=st.selectbox("历史诊断报告",history_ids,index=history_ids.index(report_id),
            format_func=lambda x:"请选择已保存诊断" if not x else "诊断版本 "+str(byreport[x]["version"])+" · "+x[:12],
            key="diag_history_"+mode+"_"+selected+"_"+report_id)
        if history_choice!=report_id:
            _select(mode,selected,history_choice);st.rerun()
        if not report_id:
            st.info("尚未选中诊断快照。点击上方检查，或明确选择已有历史版本。刷新不会自动生成报告。");return
    output.info("正在读取并核验所选报告；暂不展示其他版本。")
    try:view=w.load(mode,selected,report_id)
    except (ValueError,OSError,RuntimeError,KeyError) as exc:
        with output.container():
            st.error("诊断报告读取失败："+safe_error(exc))
            st.info("原统计结果不会被覆盖。请核对当前任务、报告版本与证据；没有展示其他报告代替。")
        return
    with output.container():
        with st.container(key="diagnostic_snapshot_"+report_id):
            st.html(report_html(view))
            _forms(w,mode,selected,view)
            st.download_button("导出诊断报告快照",view.report.model_dump_json(indent=2).encode("utf8"),
                file_name="CausalOps_诊断报告快照.json",mime="application/json",key="diag_export_"+report_id)
            st.caption("导出为生成时点的原始快照；过期快照不能作为当前结论或新执行授权。")
