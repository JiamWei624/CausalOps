"""First LangGraph workflow UI; models cannot invoke the review button."""
from __future__ import annotations
import json
import pandas as pd
import streamlit as st
from causalops.ui.source_labels import show_source
from causalops.application.research_service import ResearchService

STATUS={'cancelled':'已停止，可继续','created':'准备中','awaiting_review':'待人工审核','approved':'已批准','executing':'统计执行中','executed':'正在解释结果','completed':'已完成','rejected':'已放弃','blocked':'执行条件不满足','failed':'处理失败，可核对记录','needs_clarification':'需要补充说明'}
NODES={'method_scope':'确定候选方法','method_retrieval':'补充方法依据','method_research':'核对方法条件','cancel':'停止请求','load_context':'核对任务与数据版本','route_intent':'识别请求类型','retrieve_methods':'检索方法依据','draft_plan':'生成待审计划','await_review':'等待人工审核','execute_plan':'执行已批准的统计','answer_results':'核对运行证据并解释','answer_method':'整理方法依据','discover_questions':'推荐可回答的问题','profile_data':'读取数据概况','clarify':'说明需补充的信息','statistical_tool':'统计工具','review':'人工审核','retrieve':'检索结果'}
STATES={'started':'开始','completed':'完成','running':'运行中','blocked':'需要补充','failed':'失败','approved':'已批准','rejected':'已放弃'}

def render_graph_workspace(a,sid,frame,model):
    from causalops.ui.assistant_app import confirmations,show_run,show_sources,safe_text
    from causalops.application.background import BackgroundJobs, ACTIVE
    from causalops.ui.contracts_editor import render_contract,render_fact_fields
    service=ResearchService(a,model=model);jobs=BackgroundJobs(service);jobs.reconcile(sid)
    overview=service.flows(sid)
    latest_context=service.contracts.latest(sid)
    if latest_context:
        st.caption('当前关注指标：'+str(latest_context['body'].get('metric_label') or latest_context['body'].get('outcome') or '整体数据特征')+'；每行代表：'+(latest_context['body']['analysis_unit'] or '尚未明确')+'。')
    if overview:
        chosen=st.session_state.get('_graph_pending_'+sid) or st.session_state.get('graph_flow_'+sid)
        overview_flow=next((v for v in overview if v['id']==chosen),overview[0])
        with st.container(border=True):
            st.markdown('**当前任务：** '+safe_text(overview_flow['request']['question']))
            st.caption('当前状态：'+STATUS.get(overview_flow['status'],overview_flow['status']))
            next_step={'awaiting_review':'下一步：查看待审计划与必要口径，核对后再批准计算。','completed':'下一步：查看本次研究结论，继续追问或导出报告。','needs_clarification':'下一步：补充字段含义、分组依据或分析目标，再提出问题。','failed':'下一步：查看具体缺项或服务错误，修正后重新制定计划。','blocked':'下一步：核对被阻断步骤的设计要求；不要为了继续运行而确认未知事实。'}.get(overview_flow['status'],'下一步：等待后台状态更新；需要时可请求停止。')
            st.write(next_step)
            pending_plans=[v for v in overview if v['status']=='awaiting_review' and v['id']!=overview_flow['id']]
            if pending_plans:
                def return_pending():st.session_state['_graph_pending_'+sid]=pending_plans[0]['id']
                st.button('返回待审计划',key='return_pending_'+sid,on_click=return_pending,help='回到已有候选，不重新生成，也不自动批准。')

    else:st.info('数据已导入。可参考下方初步建议，或直接输入分析目标。')
    from causalops.ui.onboarding import render_start_actions
    if not overview:render_start_actions(service,jobs,sid,frame)
    else:
        with st.expander('新分析与口径设置'):render_start_actions(service,jobs,sid,frame)
    with st.expander('高级设置：完整数据字典与研究事实',expanded=bool(st.session_state.get('_open_contract_'+sid))):
        render_contract(service,sid,frame,expanded=bool(st.session_state.get('_open_contract_'+sid)))
    st.session_state['_job_signature_'+sid]=tuple((j['id'],j['status']) for j in jobs.jobs(sid))
    st.subheader('分析对话')
    st.caption('输入分析目标、方案调整要求或结果解读问题。系统保留本轮对话关联，必要时提示补充关键信息。')
    flows=service.flows(sid);choice_key='graph_flow_'+sid
    pending=st.session_state.pop('_graph_pending_'+sid,None)
    if pending:st.session_state[choice_key]=pending
    if flows:
        from causalops.ui.reading import landmark
        ids=[f['id'] for f in flows]
        if st.session_state.get(choice_key) not in ids:
            requested=st.query_params.get('flow')
            st.session_state[choice_key]=requested if requested in ids else ids[0]
        with st.expander('历史对话'):
            current=st.selectbox('选择对话记录',ids,format_func=lambda x:STATUS.get(next(f['status'] for f in flows if f['id']==x),'处理中')+' · '+next(f['request'].get('user_question',f['request']['question'])[:45] for f in flows if f['id']==x),key=choice_key)
        if st.query_params.get('flow') != current:
            st.query_params['flow']=current
        f=service.flow(current)
        tracking='_follow_flow_'+sid
        manual_jump=bool(pending)
        if manual_jump:
            st.session_state[tracking]=current
        waiting=f['status'] in ('created','approved','executing','executed')
        advance=not manual_jump and st.session_state.get(tracking)==current
        if not waiting:
            st.session_state.pop(tracking,None)
        def destination(name):
            landmark(name, move=manual_jump or advance, from_wait=advance)
        if waiting:
            landmark('wait',move=manual_jump)
            st.info('请求已登记，正在处理。完成后可在本任务中查看结果。')
        elif f['status'] in ('failed','blocked','needs_clarification'):
            destination('issue')
        from causalops.ui.research_quality import render_research_quality
        render_research_quality(service,f,jobs)
        from causalops.application.conversation import conversation_history
        history=conversation_history(service,current)
        if history:
            with st.expander('前序对话 · 最近 '+str(min(3,len(history)))+' 轮',expanded=True):
                for turn in history[-3:]:
                    with st.chat_message('user'):st.write(safe_text(turn['question']))
                    if turn['answer']:
                        with st.chat_message('assistant'):
                            st.caption(turn['answer']['source']);st.write(safe_text(turn['answer']['text'][:360])+('…' if len(turn['answer']['text'])>360 else ''))
                    elif turn['status']=='awaiting_review':
                        with st.chat_message('assistant'):st.write('系统记录：本轮已形成待审计划，等待明确审核。')
                    elif turn['status']=='completed':
                        with st.chat_message('assistant'):st.write('系统记录：本轮流程已完成，历史结果保留。')
                    def restore_turn(fid=turn['flow_id']):st.session_state['_graph_pending_'+sid]=fid
                    st.button('查看该轮记录',key='restore_turn_'+turn['flow_id'],on_click=restore_turn)
        with st.chat_message('user'):st.write(safe_text(f['request'].get('user_question',f['request']['question'])))
        current_jobs=[j for j in jobs.jobs(sid) if j['flow_id']==current]
        active=any(j['status'] in ACTIVE for j in current_jobs)
        if active:
            st.info('后台正在处理，页面可以继续操作。停止请求会在安全边界生效；正在进行的底层计算不会被强制中断。')
            if st.button('请求停止当前流程',key='graph_cancel_'+current):jobs.cancel(current,human_confirmed=True);st.rerun()
        elif current_jobs and current_jobs[0]['error_note']:st.warning(current_jobs[0]['error_note'])
        from causalops.ui.recovery import render_recovery
        render_recovery(service,jobs,sid,f,active,has_error=bool(current_jobs and current_jobs[0]['error_note']))
        runs=a.completed_runs(sid);refs={r['run_id']:r for r in runs}
        if flows:
            completed=service.output(current,'execution')
            if completed and completed.get('completed') and completed.get('run_ids'):
                last=completed.get('primary_run_ids',completed['run_ids'][-1:])[-1];stamp=(current,last)
                if st.session_state.get('_graph_run_seen_'+sid)!=stamp and last in refs:
                    st.session_state['_graph_run_seen_'+sid]=stamp
                    st.session_state['graph_run_'+sid]=last;a.select_run(sid,last)
        if refs:
            selected=a.selected_run(sid)
            with st.expander('历史分析结果'):
                rid=st.selectbox('结果展示与追问所依据的运行',list(refs),index=list(refs).index(selected) if selected in refs else 0,format_func=lambda x:a.tools.method(__import__('causalops.assistant.contracts',fromlist=['REGISTRY']).REGISTRY[refs[x]['method']].tool,refs[x]['method']).label+' · '+x[:8],key='graph_run_'+sid)
            if rid!=selected:a.select_run(sid,rid)
            if f['status']=='awaiting_review' and refs[rid]['plan_id']!=f['plan_id']:st.info('以下为先前已完成的结果；当前待审计划尚未执行，不能把旧结论当作新计划的输出。')
            if completed and rid in completed.get('run_ids',[]):
                destination('result')
            st.subheader('分析结果')
            show_run(a,refs[rid],sid,compact=True)
            followups=st.columns(2)
            for col,label,question in [(followups[0],'解读本次结果','请解释本次保存结果的主要发现、幅度和实际含义，不要重新计算。'),(followups[1],'查看限制与下一步','请根据本次保存结果说明分析限制与可行的下一步，不要重新计算。')]:
                if col.button(label,key='result_action_'+label+'_'+current,disabled=active,width='stretch'):
                    try:
                        job=jobs.submit_start(sid,question,mode='results',parent_flow_id=current)
                        st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
                    except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))

            if refs[rid]['method']=='descriptive':
                st.caption('从描述统计进入下一步：可围绕分布中的差异提出问题，也可直接输入自己的业务目标。')
                if st.button('根据这张表推荐后续问题',key='from_description_'+current,disabled=active):
                    try:
                        job=jobs.submit_start(sid,'根据当前字段推荐两个可进一步分析的问题，说明每个问题还需补充哪些信息。',mode='explore',parent_flow_id=current)
                        st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
                    except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))

        answer=service.output(current,'answer')
        if answer:
            if not completed and f['status']=='completed':
                destination('answer')
            st.markdown('**'+{'method_only':'方法说明','question_options':'分析建议','data_overview':'数据概览'}.get(answer.get('scope'),'结果解读' if answer.get('run_ids') else '信息补充')+'**')
            st.caption(answer['source']);st.write(safe_text(answer['text']))
            if answer.get('facts'):
                from causalops.assistant.service import friendly_fact_label,display_number
                if answer['source'].startswith('本地'):
                    for fact in answer['facts'][:4]:st.write(friendly_fact_label(fact['text'])+'：'+display_number(fact['value']))
                with st.expander('核对回答使用的精确运行证据'):
                    st.dataframe([{'指标':f['text'],'数值':str(f['value']),'证据标识':f['id'],'运行编号':f['run_id']} for f in answer['facts']],hide_index=True,width='stretch')
        advice=service.output(current,'method_research')
        if advice:
            with st.expander('方法依据与适用条件',expanded=f['status']=='awaiting_review' and bool(advice['questions'])):
                st.write('候选方法：'+ '、'.join(a.tools.method(__import__('causalops.assistant.contracts',fromlist=['REGISTRY']).REGISTRY[m].tool,m).label for m in advice['candidate_methods']))
                st.caption('实际检索 '+str(advice['retrieval_passes'])+' 轮；停止原因：'+{'coverage_complete':'规则卡六个部分均有依据','unsupported_method':'当前尚未支持该方法','retrieval_budget':'达到三轮上限','no_new_evidence':'未获得新增依据'}.get(advice['stop_reason'],advice['stop_reason']))
                if advice['conditions']:st.dataframe([{'检查内容':x['condition'],'状态':{'declared':'已登记声明（未证明）','structural':'结构核对','missing':'待补充','diagnostic_required':'待执行诊断'}[x['status']],'说明':x['detail']} for x in advice['conditions']],hide_index=True,width='stretch')
                for question in advice['questions']:st.info(safe_text(question))
        st.caption('分析状态：'+STATUS.get(f['status'],f['status']))
        if f['plan_id']:
            p=a.get_plan(f['plan_id']);v=p['plan']
            if f['status']=='awaiting_review':destination('plan')
            with st.expander('分析方案 · V'+str(p['version']),expanded=f['status']=='awaiting_review'):
                st.markdown('**待审计划 V'+str(p['version'])+'**' if f['status']=='awaiting_review' else '**来源计划 V'+str(p['version'])+'**')
                st.write(safe_text(v['objective']))
                from causalops.application.conversation import previous_plan,plan_differences
                prior=previous_plan(service,f['request'])
                if prior:
                    differences=plan_differences(prior,v)
                    with st.expander('与前序方案的差异',expanded=f['status']=='awaiting_review'):
                        if differences:st.dataframe(differences,hide_index=True,width='stretch')
                        else:st.info('本候选与前序方案没有配置变化；不会因此沿用执行批准。')

                for i,step in enumerate(v['steps']):
                    st.markdown('**步骤 '+str(i+1)+' · '+a.tools.method(step['tool'],step['config']['method']).label+'**')
                    st.write(safe_text(step['reason']))
                    from causalops.application.research_quality import method_contract
                    mc=method_contract(step['config']['method'])
                    st.caption('估计对象：'+mc['estimand']+'；适用样本：'+mc['population'])
                    with st.expander('本方法的诊断、推断与来源'):
                        st.write(mc['diagnostics']);st.write(mc['limits']);st.write(mc['inference'])
                        for source in mc['sources']:show_source(source)
                    cfg=step['config'];st.caption('分析字段：'+', '.join(list(dict.fromkeys(cfg.get('numeric',[])+cfg.get('categorical',[])+cfg.get('predictors',[])+cfg.get('covariates',[]))))+'；结果：'+str(cfg.get('outcome') or '分布/汇总'))
                for q in v['required_questions']:st.info(safe_text(q))
                with st.expander('核对完整配置、计划和数据版本'):
                    st.json(v);st.caption('计划指纹 '+p['sha']+'；数据指纹 '+f['request']['data']['frame_sha'])
                if f['status']=='awaiting_review' and not active:
                    from causalops.application.task_readiness import plan_readiness
                    readiness=plan_readiness(service,f,v)
                    stale=f['request'].get('contract_ref')!=service.contracts.ref(sid) if 'contract_ref' in f['request'] else False
                    for error in readiness['errors']:st.warning(error)
                    if readiness['errors'] or stale:
                        st.caption('本候选尚未执行；已保存结果不受影响。请先补充任务上方的数据口径，保存后重新制定计划。')
                        def edit_blocked():st.session_state['_open_contract_'+sid]=True
                        st.button('打开本任务的口径设置',key='open_blocked_'+current,on_click=edit_blocked)
                    if stale:st.warning('数据字典已更新，本候选引用旧版本；请重新制定计划。')
                    if not readiness['configuration_ready'] or stale:
                        if st.button('按最新口径重新制定计划',key='replan_'+current):
                            try:
                                job=jobs.submit_start(sid,f['request']['question'],mode='plan');st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
                            except (ValueError,RuntimeError) as exc:st.error(str(exc))
                    st.write('如变量或方法不合适，请放弃本候选，再提出新的计划；不会自动改变人工事实。')
                    facts={}
                    bound=service.contracts.bound(f)
                    for i,step in enumerate(v['steps']):
                        if bound:facts[str(i)]=render_fact_fields(step['config']['method'],bound['body']['method_facts'].get(step['config']['method'],{}),'review_'+p['id']+'_'+str(i))
                        else:facts[str(i)]=confirmations(step,i,p['id'],frame)
                    checked=st.checkbox('我已核对上述计划和本步骤必要事实，同意按当前数据与计划版本进行本地计算。',key='graph_review_'+current)
                    yes,no=st.columns(2)
                    if yes.button('接受计划并批准本次执行',type='primary',disabled=not checked or not readiness['configuration_ready'] or stale,key='graph_approve_'+current):
                        try:
                            service.review(current,accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,confirmations=facts,dispatch=False,use_contract_facts=bool(bound))
                            jobs.submit(current)
                            st.session_state['_graph_pending_'+sid]=current
                            st.rerun()
                        except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
                    if no.button('放弃本候选计划',key='graph_reject_'+current):
                        try:service.review(current,accept=False,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True);st.rerun()
                        except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
        if not active and (f['status'] in ('approved','executing','failed','cancelled') or (current_jobs and current_jobs[0]['status']=='interrupted')):
            st.info('可继续保存的流程。系统会复核数据字典、批准与代码版本，保留已完成的统计步骤；恢复模型请求时需重新提供原配置的认证信息。')
            if st.button('检查批准并继续流程',key='graph_resume_'+current):
                try:jobs.resume(current,human_confirmed=True);st.rerun()
                except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
        execution=service.output(current,'execution')
        if execution:
            for t in execution['tasks']:
                if t['state']!='completed':st.warning('步骤 '+str(t['ordinal']+1)+'：'+str((t['result'] or {}).get('error','未完成。请核对研究条件。')))
        discovery=service.output(current,'discovery')
        if discovery:
            for i,d in enumerate(discovery['directions']):
                with st.container(border=True):
                    st.markdown('**'+safe_text(d['title'])+'**');st.write(safe_text(d['question']))
                    st.caption('涉及字段：'+('、'.join(d['fields']) or '根据可用字段确定'))
                    for question in d['needs_confirmation']:st.write('待确认：'+safe_text(question))
                    st.caption('解释范围：'+safe_text(d['limitation']))
                    if st.button('制定分析方案',key='direction_'+current+'_'+str(i)):
                        try:
                            job=jobs.submit_start(sid,'采用第'+str(i+1)+'项建议',mode='plan',parent_flow_id=current);st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
                        except (ValueError,RuntimeError) as exc:st.error(str(exc))
        pr=service.output(current,'profile')
        if pr:
            with st.expander('字段检查明细'):st.dataframe(pd.DataFrame(pr['fields']).rename(columns={'field':'字段','dtype':'类型','missing_n':'缺失数','numeric':'数值字段','distinct_n':'唯一值数','likely_identifier':'疑似标识','infinite_n':'无穷值数'}),hide_index=True,width='stretch')
        retrieval=service.output(current,'retrieval')
        if retrieval:
            with st.expander('本轮实际检索的方法依据'):show_sources(retrieval)
        with st.expander('实际步骤与暂停恢复记录'):
            rows=service.events(current)
            st.dataframe([{'顺序':e['seq'],'步骤':NODES.get(e['node'],e['node']),'状态':STATES.get(e['status'],e['status']),'时间':e['created']} for e in rows],hide_index=True,width='stretch')
            st.caption('记录来自实际节点和工具调用，不是对最终文字的模拟播放。')
            st.download_button('下载流程记录（JSON）',json.dumps({'flow_id':current,'events':rows,'snapshot':service.snapshot(current)},ensure_ascii=False,indent=2),file_name='workflow-'+current+'.json',mime='application/json',key='graph_trace_'+current)
    else:st.info('数据已登记。输入分析问题后，系统会检索方法并提出待审计划；不会在未审核前进行统计估计。')
    if not flows and a.completed_runs(sid):
        historical={r['run_id']:r for r in a.completed_runs(sid)}
        rid=a.selected_run(sid) or next(iter(historical))
        st.subheader('已保存的分析结果');show_run(a,historical[rid],sid,compact=True)
    modes={'自动选择请求类型':'auto','制定分析计划':'plan','方法咨询':'method','解释当前运行':'results','数据概况':'profile'}
    mode='自动选择请求类型'
    with st.expander('高级：手动指定请求类型'):
        manual=st.checkbox('本次由我指定请求类型',key='manual_route_v011_'+sid)
        if manual:mode=st.radio('本轮请求',list(modes),horizontal=True,key='graph_mode_v011_'+sid)
    q=st.chat_input('输入分析目标、方案调整要求或结果解读问题',key='graph_question_'+sid)
    if q:
        try:
            job=jobs.submit_start(sid,q,mode=modes[mode],parent_flow_id=current if flows else None)
            st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
        except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc));st.info('未执行未批准的统计；已有结果保持不变。')

    @st.fragment(run_every=1)
    def watch_background():
        records=jobs.jobs(sid)
        signature=tuple((j['id'],j['status']) for j in records)
        key='_job_signature_'+sid
        old=st.session_state.get(key);st.session_state[key]=signature
        if old is not None and old!=signature:st.rerun()
        running=[j for j in records if j['status'] in ACTIVE]
        if running:
            labels={'queued':'排队中','running':'后台处理中','cancel_requested':'正在安全停止'}
            for job in running:
                events=service.events(job['flow_id'])
                last=events[-1] if events else None
                st.caption(labels[job['status']]+' · '+job['flow_id'][:8]+(' · '+NODES.get(last['node'],last['node'])+' / '+STATES.get(last['status'],last['status']) if last else ''))
    watch_background()
