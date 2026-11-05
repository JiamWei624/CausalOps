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
    if overview:
        chosen=st.session_state.get('_graph_pending_'+sid) or st.session_state.get('graph_flow_'+sid) or st.query_params.get('flow')
        overview_flow=next((v for v in overview if v['id']==chosen),overview[0])
    else:
        overview_flow=None
    if overview_flow and overview_flow['request'].get('review_owner') and overview_flow['status']=='completed':
        overview_flow=service.flow(overview_flow['request']['review_owner'])
    from causalops.ui.visual_layout import steps
    status=overview_flow['status'] if overview_flow else 'created'
    phase={'awaiting_review':2,'approved':3,'executing':3,'executed':4,'completed':4}.get(status,0)
    if overview_flow and status=='completed' and not service.output(overview_flow['id'],'execution'):
        steps(['研究问题','资料核对','答复与讨论'],2)
    else:
        steps(['研究问题','研究方案','人工审核','统计执行','结果讨论'],phase)
    primary_results=st.container() if status=='completed' and service.output(overview_flow['id'],'execution') else None
    review_layout=status in ('awaiting_review','needs_clarification') or not overview
    audit_view=False
    if status=='awaiting_review':
        audit_view=st.radio('方案视图',['方案讨论','人工审核'],horizontal=True,key='layout_'+overview_flow['id'],label_visibility='collapsed')=='人工审核'
    if audit_view:
        col_plan,col_audit=st.columns([1.06,1],gap='medium')
        design=col_plan.container(key='panel_design')
        approval=col_audit.container(key='panel_approval')
        design.subheader('拟批准的方案')
        approval.subheader('研究方案审核')
        discussion=st.container()
    elif review_layout:
        col_chat,col_plan=st.columns([.84,1],gap='medium')
        discussion=col_chat.container(key='panel_discussion')
        design=col_plan.container(key='panel_design')
        discussion.subheader('研究助手')
        design.subheader('当前研究方案' if overview else '研究目标与数据概况')
    else:
        discussion=st.container()
        design=st.container()
    if not audit_view:approval=design
    from causalops.ui.onboarding import render_start_actions,render_metric_change
    from causalops.ui.report_target import report_target
    target=report_target(service,sid,overview_flow)
    with design:
        if overview_flow:
            plan=a.get_plan(overview_flow['plan_id']) if overview_flow.get('plan_id') else None
            st.caption(STATUS.get(status,status)+'　｜　'+('方案 V'+str(plan['version']) if plan else '尚无关联方案'))
            if plan and status=='awaiting_review':
                design_steps=plan['plan']['steps']
                bound=service.contracts.bound(overview_flow)
                contract=bound['body'] if bound else {}
                from html import escape
                records=[('研究问题',plan['plan']['objective']),('分析方法','、'.join(a.tools.method(step['tool'],step['config']['method']).label for step in design_steps)),('分析单位',contract.get('analysis_unit')),('目标指标',contract.get('metric_label') or contract.get('outcome')),('观察窗口',contract.get('metric_window')),('方案版本','V'+str(plan['version']))]
                st.html('<dl class="co-kv">'+''.join('<div><dt>'+name+'</dt><dd>'+escape(str(value or '尚未登记'))+'</dd></div>' for name,value in records)+'</dl>')
            render_metric_change(service,jobs,sid,frame,target)
            with st.expander('新分析与口径设置'):render_start_actions(service,jobs,sid,frame,target)
        else:
            render_start_actions(service,jobs,sid,frame,target)
        with st.expander('高级设置：完整数据字典与研究事实',expanded=bool(st.session_state.get('_open_contract_'+sid))):
            render_contract(service,sid,frame,expanded=bool(st.session_state.get('_open_contract_'+sid)))
    with discussion:
        if not overview:
            st.caption('当前仅有数据概况。研究方案获批并运行后，统计结果才会出现在本任务中。')
            with st.expander('查看数据质量'):
                st.write(f'记录 {len(frame):,} 条，字段 {len(frame.columns)} 个。')
                st.dataframe(frame.isna().sum().rename('缺失记录数').rename_axis('字段').reset_index(),hide_index=True)
            if st.button('推荐研究问题',key='starter_discover_'+sid):
                job=jobs.submit_start(sid,'这份数据可以回答哪些研究问题？',mode='explore')
                st.session_state['_graph_pending_'+sid]=job['flow_id']
                st.rerun()
        visible_context=service.contracts.bound(overview_flow) if overview_flow else latest_context
        if visible_context:
            st.caption('方案登记指标：'+str(visible_context['body'].get('metric_label') or visible_context['body'].get('outcome') or '整体数据特征'))
        if overview_flow:
            pending_plans=[v for v in overview if v['status']=='awaiting_review' and v['id']!=overview_flow['id']]
            if pending_plans:
                def return_pending():st.session_state['_graph_pending_'+sid]=pending_plans[0]['id']
                st.button('返回待审计划',key='return_pending_'+sid,on_click=return_pending)
        else:
            st.info('数据已登记。可输入业务问题、比较分析方法，或从数据概况中选择下一步。')
    st.session_state['_job_signature_'+sid]=tuple((j['id'],j['status']) for j in jobs.jobs(sid))
    if not review_layout:discussion.subheader('分析对话')
    discussion.caption('输入分析目标、方案调整要求或结果解读问题。系统保留本轮对话关联，必要时提示补充关键信息。')
    flows=service.flows(sid);choice_key='graph_flow_'+sid
    pending=st.session_state.pop('_graph_pending_'+sid,None)
    if pending:st.session_state[choice_key]=pending
    if flows:
        from causalops.ui.reading import landmark
        ids=[f['id'] for f in flows]
        if st.session_state.get(choice_key) not in ids:
            requested=st.query_params.get('flow')
            st.session_state[choice_key]=requested if requested in ids else ids[0]
        with discussion.expander('历史对话'):
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
        with design:
            render_research_quality(service,f,jobs)
        with discussion:
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
        chat_flow=current
        owner=f['request'].get('review_owner')
        if owner and f['status']=='completed':
            preview=service.output(current,'answer') or {}
            if preview.get('review_owner')==owner:
                with discussion.chat_message('assistant'):st.write(safe_text(preview['text']))
                current=owner
                f=service.flow(owner)
        current_jobs=[j for j in jobs.jobs(sid) if j['flow_id']==current]
        active=any(j['status'] in ACTIVE for j in current_jobs)
        if active:
            st.info('后台正在处理，页面可以继续操作。停止请求会在安全边界生效；正在进行的底层计算不会被强制中断。')
            if st.button('请求停止当前流程',key='graph_cancel_'+current):jobs.cancel(current,human_confirmed=True);st.rerun()
        elif current_jobs and current_jobs[0]['error_note']:st.warning(current_jobs[0]['error_note'])
        from causalops.ui.recovery import render_recovery
        render_recovery(service,jobs,sid,f,active,has_error=bool(current_jobs and current_jobs[0]['error_note']))
        scope=f['request'].get('analysis_scope') if flows else None
        if scope and not scope.get('error'):
            st.info('本次研究口径：'+str(scope['outcome'])+(' · '+scope['metric_window'] if scope.get('metric_window') else '')+
                    ('。新运行尚未交付，下面已保存的报告为历史结果。' if not service.output(current,'execution') else '。'))
        runs=a.completed_runs(sid);refs={r['run_id']:r for r in runs}
        if flows:
            completed=service.output(current,'execution')
            if completed and completed.get('completed') and completed.get('run_ids'):
                last=completed.get('primary_run_ids',completed['run_ids'][-1:])[-1];stamp=(current,last)
                if st.session_state.get('_graph_run_seen_'+sid)!=stamp and last in refs and (a.selected_run(sid)==last or '_graph_run_seen_'+sid in st.session_state):
                    st.session_state['_graph_run_seen_'+sid]=stamp
                    st.session_state['graph_run_'+sid]=last;a.select_run(sid,last)
        if refs:
            selected=a.selected_run(sid)
            from causalops.application.report_scope import report_scope
            scopes = {key:report_scope(a,sid,run) for key,run in refs.items()}
            with st.expander('选择报告（按指标与观察期）',expanded=len(refs)>1):
                rid=st.selectbox('结果展示与追问所依据的运行',list(refs),index=list(refs).index(selected) if selected in refs else 0,format_func=lambda x:' · '.join(v for v in scopes[x] if v)+' · '+a.tools.method(__import__('causalops.assistant.contracts',fromlist=['REGISTRY']).REGISTRY[refs[x]['method']].tool,refs[x]['method']).label+' · '+x[:8],key='graph_run_'+sid)
            if rid!=selected:a.select_run(sid,rid)
            if f['status']=='awaiting_review' and refs[rid]['plan_id']!=f['plan_id']:st.info('以下为先前已完成的结果；当前待审计划尚未执行，不能把旧结论当作新计划的输出。')
            with (primary_results if primary_results is not None else st.container()):
                if completed and rid in completed.get('run_ids',[]):
                    destination('result')
                st.caption('报告依据：计划 V'+str(refs[rid]['plan_version']))
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

        prior=service.output(current,'prior_answer')
        if prior:
            st.markdown('**前序报告解读**')
            st.write(safe_text(prior['text']))
            st.caption('运行来源：'+'、'.join(prior.get('run_ids',[])))
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
        with design:
            advice=service.output(current,'method_research')
            if advice:
                with st.expander('方法依据与适用条件',expanded=f['status']=='awaiting_review' and bool(advice['questions'])):
                    st.write('候选方法：'+ '、'.join(a.tools.method(__import__('causalops.assistant.contracts',fromlist=['REGISTRY']).REGISTRY[m].tool,m).label for m in advice['candidate_methods']))
                    st.caption('检索轮数：'+str(advice['retrieval_passes'])+' 轮；停止原因：'+{'coverage_complete':'规则卡六个部分均有依据','unsupported_method':'当前尚未支持该方法','retrieval_budget':'达到三轮上限','no_new_evidence':'未获得新增依据'}.get(advice['stop_reason'],advice['stop_reason']))
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
                            if differences:
                                before,after=st.columns(2)
                                for box,label in ((before,'修改前'),(after,'修改后')):
                                    box.markdown('**'+label+'**')
                                    for row in differences:
                                        box.caption(row['项目'])
                                        if row['项目'].startswith('步骤'):
                                            details=json.loads(row[label])
                                            if details:
                                                box.write(safe_text(details.get('reason','')))
                                                box.json(details.get('config',{}),expanded=False)
                                            else:box.caption('本版本没有此步骤')
                                        else:box.text(row[label])
                            else:st.info('本候选与前序方案没有配置变化；不会因此沿用执行批准。')

                    for i,step in enumerate(v['steps']):
                        st.markdown('**步骤 '+str(i+1)+' · '+a.tools.method(step['tool'],step['config']['method']).label+'**')
                        st.write(safe_text(step['reason']))
                        if scope and not scope.get('error'):
                            st.write('结果：'+scope['outcome']+'。')
                            if scope.get('start'):
                                st.write('筛选日期：'+scope['start']+' 至 '+scope['end']+'；实际有记录 '+str(scope['covered_days'])+' 个自然日。')
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
        with approval:
            if f.get('plan_id') and f['status']=='awaiting_review' and not active:
                from causalops.application.task_readiness import plan_readiness
                readiness=plan_readiness(service,f,v)
                stale=f['request'].get('contract_ref')!=service.contracts.ref(sid) if 'contract_ref' in f['request'] else False
                st.markdown('**研究方案审核 · V'+str(p['version'])+'**')
                prior=previous_plan(service,f['request'])
                contract=service.contracts.bound(f)
                current_metric=(contract or {}).get('body',{}).get('outcome') or '未单独登记'
                if prior:
                    parent=service.flow(f['request']['conversation_ref']['parent_flow_id'])
                    if parent['plan_id']:
                        parent_contract=service.contracts.bound(parent)
                        old_metric=(parent_contract or {}).get('body',{}).get('outcome') or '未单独登记'
                        st.text('前序方案指标：'+old_metric)
                    elif scope and scope.get('base_outcome'):
                        st.text('原登记指标：'+scope['base_outcome'])
                st.text('本次计划指标：'+current_metric)
                st.markdown('**程序核对**')
                st.write('配置可执行，且口径版本一致。' if readiness['configuration_ready'] and not stale else '当前配置或口径版本仍需处理。')
                st.markdown('**研究声明与识别限制**')
                st.caption('分组如何产生、指标何时测量，应按数据来源确认。结构检查无法证明组间不存在干扰或未观测混杂。')
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
                bound=contract
                for i,step in enumerate(v['steps']):
                    if bound:facts[str(i)]=render_fact_fields(step['config']['method'],bound['body']['method_facts'].get(step['config']['method'],{}),'review_'+p['id']+'_'+str(i))
                    else:facts[str(i)]=confirmations(step,i,p['id'],frame)
                # Submit preview confirmations atomically. A checkbox rerun must not race the approve button.
                review_box=st.form('preview_confirmation_'+current) if owner else st.container()
                with review_box:
                    checked=st.checkbox('我已核对上述计划和本步骤必要事实，同意按当前数据与计划版本进行本地计算。',key='graph_review_'+current)
                    if stale:
                        st.caption('暂不能批准：数据口径已更新，请按最新口径重新制定计划。')
                    elif not readiness['configuration_ready']:
                        st.caption('暂不能批准：请先处理上方列出的配置问题。')
                    elif not owner and not checked:
                        st.caption('暂不能批准：请核对本版本字段和研究声明，再勾选上方确认项。')
                    else:
                        st.caption('核对并勾选后，点击下方批准按钮。系统复核本版本后执行，完成后可打开新报告。')
                    yes,no=st.columns(2)
                    if owner:
                        approve=yes.form_submit_button('接受计划并批准本次执行',type='primary',disabled=not readiness['configuration_ready'] or stale)
                    else:
                        approve=yes.button('接受计划并批准本次执行',type='primary',disabled=not checked or not readiness['configuration_ready'] or stale,key='graph_approve_'+current)
                if approve and not checked:
                    st.warning('请先核对当前版本并勾选确认。尚未批准或执行。')
                if approve and checked and readiness['configuration_ready'] and not stale:
                    try:
                        service.review(current,accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,confirmations=facts,dispatch=False,use_contract_facts=bool(bound))
                        jobs.submit(current)
                        st.session_state['_graph_pending_'+sid]=current
                        st.rerun()
                    except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
                if (st if owner else no).button('放弃本候选计划',key='graph_reject_'+current):
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
        if discovery and discovery['directions']:
            direction_cols=st.columns(min(len(discovery['directions']),3))
            for i,d in enumerate(discovery['directions']):
                with direction_cols[i%len(direction_cols)].container(key=f'panel_direction_{current}_{i}'):
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
    with discussion:
        modes={'自动选择请求类型':'auto','制定分析计划':'plan','方法咨询':'method','解释当前运行':'results','数据概况':'profile'}
        mode='自动选择请求类型'
        with st.expander('高级：手动指定请求类型'):
            manual=st.checkbox('本次由我指定请求类型',key='manual_route_v011_'+sid)
            if manual:mode=st.radio('本轮请求',list(modes),horizontal=True,key='graph_mode_v011_'+sid)
        q=st.chat_input('输入分析目标、方案调整要求或结果解读问题',key='graph_question_'+sid)
    if q:
        try:
            job=jobs.submit_start(sid,q,mode=modes[mode],parent_flow_id=chat_flow if flows else None)
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
                with st.container(key='panel_job_'+job['id']):
                    step_col,trace_col=st.columns(2)
                    step_col.markdown('**执行状态**')
                    step_col.write(labels[job['status']])
                    trace_col.markdown('**最近执行节点**')
                    trace_col.write(NODES.get(last['node'],last['node'])+' / '+STATES.get(last['status'],last['status']) if last else '尚无节点记录')
                    trace_col.caption('流程 '+job['flow_id'][:8])
    watch_background()
