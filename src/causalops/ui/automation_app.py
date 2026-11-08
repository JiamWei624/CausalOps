
"""Restricted automation workbench; UI never grants execution on its own."""
from __future__ import annotations
import os,uuid
from pathlib import Path
import streamlit as st
from causalops.application.research_service import ResearchService
from causalops.application.background import AutomationJobs
from causalops.application.automation_results import snapshot,report_html,export_json,STATES
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import DesignError
from causalops.application.configurable_research import is_configurable,ConfigurablePlan2,parse_plan
from causalops.sample_data.hillstrom import SOURCE,DOWNLOAD,QUESTION

def _open(tid=""):
    if tid:st.query_params["automation"]=tid
    else:st.query_params.pop("automation",None)
    st.query_params["route"]="automation"

def _new():
    _open()
    st.session_state.pop("automation_create_key",None)
    st.session_state.pop("automation_source_review",None)
    for key in list(st.session_state):
        if key=="cfg_upload_new" or key.startswith(("cfg_new_","config_import_new_")):
            st.session_state.pop(key,None)

def _create(co):
    source=st.radio("研究数据来源",["公开 Hillstrom 营销实验","使用自己的数据开展研究"],key="automation_data_source")
    if source=="使用自己的数据开展研究":
        from causalops.ui.configurable_app import editor
        editor(co)
        return
    st.subheader("公开数据与研究范围")
    st.write(QUESTION)
    st.markdown(f"[实验发布者说明]({SOURCE}) · [下载公开数据]({DOWNLOAD})")
    st.write("仅纳入男装邮件与未发邮件两组，以客户为单位，比较分配后两周的访问率。使用分组描述统计和 A/B；女装组不纳入。随机分配依据原实验说明，需要使用者核对。")
    st.caption("受限自动化场景。计划为固定五步、两次统计调用；当前不支持任意自然语言自主规划，不调用模型。")
    location=os.environ.get("CAUSALOPS_HILLSTROM_ARCHIVE")
    configured=Path(location) if location else None
    if configured and configured.is_file():
        st.info("已找到配置的公开实验文件，创建时核验固定数据指纹。")
        upload=None
    else:upload=st.file_uploader("上传公开原始 hillstrom.csv.gz",type=["gz"],key="automation_upload")
    checked=st.checkbox("已核对公开来源、客户单位、随机分配、两组纳入规则和两周访问定义",key="automation_source_review")
    if st.button("生成五步研究计划",type="primary",disabled=not checked or not bool(upload or (configured and configured.is_file()))):
        try:
            if configured and configured.is_file():
                if configured.stat().st_size>5_000_000:raise DesignError("公开实验压缩包超过允许大小。")
                data=configured.read_bytes()
            else:
                if upload.size>5_000_000:raise DesignError("公开实验压缩包超过允许大小。")
                data=upload.getvalue()
            request=st.session_state.setdefault("automation_create_key",uuid.uuid4().hex)
            task=co.create_hillstrom(data,request_id=request,source_confirmed=checked)
            _open(task["id"]);st.rerun()
        except (ValueError,OSError) as exc:
            st.error(str(exc) if isinstance(exc,ValueError) else "公开数据读取失败，请重新选择原始压缩包。")
            st.caption("未创建可执行的自动化计划；请核对原始文件。原有任务与统计结果保留。")

def _budget(view):
    b=view["budget"]
    with st.expander("资源预算与停止原因"):
        st.write(f"模型物理请求：{b['physical_requests']}/12，账本剩余 {12-b['physical_requests']}。统计执行阶段授权模型调用为0；本任务候选规划请求单独记录，通用自主规划关闭。")
        st.write(f"语义修订：{b['semantic_revisions']}/2。固定计划不可原地改写；更换范围需新任务及重新审核。")
        st.write(f"回执输入/输出令牌：{b['input_tokens']}/{b['output_tokens']}；用量未知请求：{b['usage_unknown']}。未调用模型不能表述为一次真实 DeepSeek 请求。")
        if b["price_version"]:st.write(f"已知用量估算 ¥{b['estimated_cost_cny']:.6f}；价格版本 {b['price_version']['version']}，未知用量未计入，¥1为预警。")
        else:st.caption("尚无价格快照。费用未估算，不能将缺少用量视为免费；统计执行本身不需要模型；可选规划按实际账本记录，不将未知用量视为免费。")
        st.dataframe([{"统计步骤":r["name"],"实际工具尝试":r["tool_attempts"],"重试已用":max(0,r["tool_attempts"]-1),"同输入总尝试上限":2} for r in view["steps"] if r["assistant_task_id"]],hide_index=True,width="stretch")
        st.caption("已成功的步骤不会因尚有重试额度而再次执行；仅核实安全的临时故障允许一次重试。")
        if b["stops"]:st.json(b["stops"])
        if view["task"]["reason"]:st.warning(view["task"]["reason"])

def _plan(view):
    t=view["task"];p=t["plan"]
    custom=is_configurable(p)
    sc=p["scope"]
    from causalops.ui.constrained_planning_app import render as planning
    co=ResearchService(AssistantWorkspace()).automation_v2()
    try:review_allowed=planning(co,t)
    except (ValueError,RuntimeError) as exc:
        st.error(str(exc) if isinstance(exc,DesignError) else "候选计划或来源未通过核验，原研究历史保留；请重新登记正确范围。")
        review_allowed=False
    left,right=st.columns([1.25,1],gap="medium")
    with left.container(border=True):
        st.subheader("完整研究计划")
        st.write(p["objective"])
        if custom:
            cfg=p["configuration"]
            st.write(f"正式字段：{sc['outcome']}；{sc['metric']}；比较组：{cfg['treated_label']} 对比 {cfg['control_label']}；观察窗口：{sc['window']}；分析单位：{sc['analysis_unit']}。")
            st.write(f"计划 v{p['version']}；描述统计1次，"+("符合证据与授权时 A/B 1次。" if any(s["step_id"]=="S04" for s in p["steps"]) else "仅描述统计和证据整合；本路径没有A/B步骤。"))
            st.caption("用户确认的窗口适用于本表全部记录；系统不自动切片。批准只覆盖此计划的实际数据、字段、编码和设计依据。")
        else:
            st.dataframe([{"研究口径":k,"已登记内容":v} for k,v in [
                ("分析单位","客户；每名客户一条记录"),("正式指标","visit / 两周访问率 / 概率"),
                ("比较组","男装邮件（1）－未发邮件（0）"),("观察窗口","分配后两周"),
                ("纳入规则","仅男装邮件与未发邮件；不自动删样本、填补或替换方法"),
                ("计划版本",str(p["version"])),("工具调用","描述统计1次，A/B1次")]],hide_index=True,width="stretch")
        for row,spec in zip(view["steps"],p["steps"]):
            with st.expander(row["name"]+" · "+STATES.get(row["status"],row["status"])):
                st.write("依赖："+("、".join(spec["depends_on"]) or "数据、合同与整体批准"))
                st.caption("统计工具："+spec["config"].get("method","本地只读检查／证据整合"))
                st.json(spec)
        with st.expander("数据与合同身份"):
            st.json({"data":p["data"],"contract_ref":p["contract_ref"],"source":t["source"],"plan_id":p["plan_id"],"plan_sha":t["plan_sha"]})
    with right.container(border=True):
        st.subheader("整体计划审核")
        design_source=sc.get("assignment_source",SOURCE)
        if design_source:st.markdown(f"[用户登记的研究设计依据]({design_source})")
        elif custom:st.warning("随机分配依据未知：本计划只允许描述统计，不授权A/B效果分析。")
        st.write("核对本计划全部逻辑步骤、数据身份、比较组、正式指标、登记窗口和严格缺失策略。批准只覆盖本计划，数据、合同或计划变化后不能沿用。")
        st.caption("程序可核验结构、样本与证据一致性。用户确认来源和研究事实；无干扰等研究假设不能仅靠程序证明。")
        st.write("停止条件：上游证据未通过、批准失效、数据变化、资源不足或运行不确定。每个正式统计步骤仍由服务重新校验授权。")
        confirm=st.checkbox("我已核对完整计划、数据与研究依据，批准本计划范围内自动执行",key="automation_approve_"+t["id"])
        if view["binding_error"]:st.error(view["binding_error"])
        if st.button("批准整份计划并开始",type="primary",disabled=not confirm or bool(view["binding_error"]) or not review_allowed,key="automation_start_"+t["id"]):
            try:
                co=ResearchService(AssistantWorkspace()).automation_v2()
                co.approve(t["id"],expected_plan_sha=t["plan_sha"],human_confirmed=confirm)
                AutomationJobs(co.s).submit_task(t["id"]);st.rerun()
            except (ValueError,RuntimeError) as exc:st.error(str(exc) if isinstance(exc,DesignError) else "未能启动，请核对任务状态，已保存的批准不会被页面刷新重复创建。")
        st.caption("普通聊天中的同意不授予执行权限。审核后自动推进，无需逐步批准。")

def _live(tid):
    co=ResearchService(AssistantWorkspace()).automation_v2();jobs=AutomationJobs(co.s)
    records=jobs.reconcile(tid)
    try:view=snapshot(co,tid)
    except DesignError as exc:st.info(str(exc));return
    t=view["task"];active=any(j["status"] in ("queued","running") for j in records)
    st.subheader("当前研究任务")
    st.caption("任务 "+t["id"]+" · 计划 "+t["plan"]["plan_id"]+" · v"+str(t["plan"]["version"]))
    st.write("**任务状态："+STATES.get(t["status"],t["status"])+"**")
    if active:st.caption("后台任务正在排队或执行；页面刷新只读取记录。")
    if records and records[0]["error_note"]:st.warning(records[0]["error_note"])
    with co.ws.connection() as db:has_approval=bool(db.execute("SELECT 1 FROM automation_v2_approvals WHERE task_id=?",(tid,)).fetchone())
    planning_paused=t["status"]=="paused" and not has_approval and t["plan"]["schema_version"]=="configurable-research-stage2"
    if t["status"]=="candidate" or planning_paused:
        _plan(view);_budget(view)
        return
    count=sum(r["status"]=="succeeded" for r in view["steps"])
    expected_runs=sum(s["kind"]=="statistical" for s in t["plan"]["steps"])
    total_steps=len(view["steps"])
    st.progress(count/total_steps,text=f"已保存 {count}/{total_steps} 个逻辑步骤 · 已保存统计运行 {sum(bool(r['run_id']) for r in view['steps'])}/{expected_runs}")
    st.caption("进度由实际持久化步骤计算，不表示剩余时间。预览、计划、批准、执行和报告分别保存。")
    actions=st.columns(3)
    if actions[0].button("请求暂停",disabled=t["status"] not in ("approved","running"),key="auto_pause_"+tid):
        co.pause(tid,human_confirmed=True);st.rerun()
    if actions[1].button("核查恢复并继续",disabled=active or t["status"] not in ("paused","interrupted","running","pause_requested"),key="auto_resume_"+tid):
        try:co.user_event(tid,"user_restore");jobs.submit_task(tid,resume=True);st.rerun()
        except DesignError as exc:st.error(str(exc))
    if actions[2].button("继续获批任务",disabled=active or t["status"]!="approved",key="auto_continue_"+tid):
        try:jobs.submit_task(tid);st.rerun()
        except DesignError as exc:st.error(str(exc))
    if t["status"] not in ("cancelled","completed"):
        cancel=st.checkbox("我确认取消当前自动化任务，保留已有结果；取消后不能恢复",key="auto_cancel_check_"+tid)
        if st.button("确认取消任务",disabled=not cancel,key="auto_cancel_"+tid):
            co.cancel(tid,human_confirmed=cancel);st.rerun()
    elif t["status"]=="cancelled":st.warning("当前任务已取消，不能恢复。已有统计证据仍可查看；重新研究需要新建任务并审核。")
    st.subheader("计划执行与证据" if t["plan"]["schema_version"]=="configurable-research-stage2" else "五步执行与证据")
    for row in view["steps"]:
        with st.expander(row["name"]+"："+STATES.get(row["status"],row["status"]),expanded=row["status"] in ("running","blocked","interrupted")):
            st.write("实际统计 Run："+(row["run_id"] or "尚无已确认统计Run；审计和核验不属于统计运行"))
            if row["step_id"] in view["evidence"]:st.json(view["evidence"][row["step_id"]])
            elif t["reason"] and row["status"] in ("blocked","interrupted"):st.warning(t["reason"])
            else:st.caption("此步骤尚未产生可确认的成功证据。")
    st.subheader("研究风险与待确认事项")
    for risk in view["risks"]:
        st.markdown("**"+risk["level"]+"** · "+risk["detail"])
    if t["status"] in ("blocked","paused","interrupted"):
        st.info("保留已保存步骤和原Run。核查上游证据、批准与数据后再恢复；数据或范围改变需要创建新的待审任务。没有绕过门禁的执行入口。")
    _budget(view)
    st.subheader("整体研究报告" if view["report"] else "部分完成与保留结果")
    # Title, metric, both Run IDs and conclusion are one evidence-bound HTML block.
    html=report_html(view);st.html(html)
    seen="auto_report_viewed_"+tid
    if not st.session_state.get(seen):
        co.user_event(tid,"report_viewed");st.session_state[seen]=True
    a,b=st.columns(2)
    a.download_button("导出整体研究报告" if view["report"] else "导出部分完成说明",html.encode("utf8"),file_name="CausalOps_自动化研究报告.html",mime="text/html",key="auto_report_"+tid)
    b.download_button("导出步骤与运行证据",export_json(view),file_name="CausalOps_自动化运行证据.json",mime="application/json",key="auto_evidence_"+tid)
    with st.expander("执行事件与复现记录"):
        st.json(view["events"])

def render():
    # Streamlit retains dimmed stale DOM while a different task rerenders.
    # Hide only stale automation report bodies until their bound identity is current.
    st.html('<style>[data-stale="true"] .co-automation-report{visibility:hidden;}</style>')
    st.caption("切换任务时等待当前报告载入；过期报告会暂时隐藏，报告中的任务与运行来源应与当前任务一致。")
    st.title("自动化研究",anchor=False)
    co=ResearchService(AssistantWorkspace()).automation_v2()
    with co.ws.connection() as c:ids=[r[0] for r in c.execute("SELECT id FROM automation_v2_tasks ORDER BY created DESC,id DESC")]
    selected=st.query_params.get("automation","")
    if selected and selected not in ids:
        st.warning("所选自动化任务不存在于当前工作区，请从已有任务中选择。");selected=""
    def label(tid):
        if not tid:return "创建新的公开营销研究"
        t=co.task(tid)
        sc=t["plan"]["scope"]
        return sc["metric"]+" · "+" / ".join(sc["groups"].values())+" · "+sc["window"]+" · "+STATES.get(t["status"],t["status"])+" · "+tid[:8]
    choice=st.selectbox("自动化任务与历史报告",[""]+ids,index=([""]+ids).index(selected),format_func=label,key="auto_history_"+selected)
    if choice!=selected:
        _open(choice);st.rerun()
    st.button("创建新的自动化研究",on_click=_new)
    if selected:
        from causalops.ui.diagnostics_app import open_diagnostics
        task=co.task(selected)
        custom=is_configurable(task["plan"])
        if custom:
            st.info("当前用户配置研究已接入六项证据诊断、三层报告和同任务研究决定。诊断只读、不补造未执行的Run，其余八项规则仍未实现。")
            st.button("查看当前研究的证据诊断",on_click=open_diagnostics,args=("post_run",selected),key="auto_diag_"+selected)
            if st.button("修改研究条件（新候选并重新审核）",key="config_revise_"+selected):
                st.query_params["config_edit"]=selected;st.rerun()
            if st.query_params.get("config_edit")==selected:
                from causalops.ui.configurable_app import editor
                editor(co,previous=task)
                return
        else:st.button("查看当前研究的证据诊断",on_click=open_diagnostics,args=("post_run",selected),key="auto_diag_"+selected)
        st.button("检查当前数据的研究条件",on_click=open_diagnostics,args=("preflight",task["session_id"]),key="auto_prediag_"+selected)
    if selected:
        jobs=AutomationJobs(co.s)
        watching=any(j["status"] in ("queued","running") for j in jobs.reconcile(selected))
        @st.fragment(run_every=2 if watching else None)
        def current_task():
            active=any(j["status"] in ("queued","running") for j in jobs.reconcile(selected))
            if active!=watching:
                # Refresh selector labels and clear the previous dynamic layout
                # once a background job settles; completed reports stay static.
                st.rerun()
            _live(selected)
        current_task()
    else:_create(co)
