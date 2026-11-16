"""Native Streamlit conversation workspace, references only; formal actions stay in original routes."""
from __future__ import annotations
import uuid,json,os,re
from html import escape
import streamlit as st
from causalops.assistant.service import AssistantWorkspace
from causalops.application.research_service import ResearchService
from causalops.application.chat_sessions import ChatService
from causalops.ui.design_system import brand_html

from causalops.ui.chat_typography import CHAT_CSS,display_parts,lead_html


def go(route,**params):
    st.query_params.update(route=route,**params)
    st.rerun()

def switch(cid):
    st.query_params.update(route='home',chat=cid)
    st.query_params.pop('panel',None)
    st.query_params.pop('chat_flow',None)
    for name in ('automation','assistant','diagnostic_task','diagnostic_report','diagnostic_mode'):st.query_params.pop(name,None)
    st.rerun()

def _legacy_link(label,route,source=None,key=None,*,tertiary=False):
    meta=(source or {}).get('metadata')
    if st.button(label,key=key,width='stretch',type='tertiary' if tertiary else 'secondary'):
        if meta:
            if meta['domain']=='automation_v2':st.query_params['automation']=meta['subject_id']
            else:
                st.query_params.pop('automation',None)
                st.query_params['assistant']=meta['assistant_session_id']
            if route in ('evidence','decisions'):
                subject=meta['subject_id'] if meta['domain']=='automation_v2' else meta['assistant_session_id']
                if st.query_params.get('diagnostic_task')!=subject:st.query_params.pop('diagnostic_report',None)
                st.query_params.update(diagnostic_mode='post_run' if meta['domain']=='automation_v2' else 'preflight',diagnostic_task=subject)
        if meta and meta['domain']=='assistant' and route in ('configure','review','execution','results'):route='assistant'
        go(route)

def _associate(service,cid):
    a=service.a;co=service.s.automation_v2();options=[''];labels={'':'请选择研究任务'};pairs={}
    with co.ws.connection() as c:tasks=[r[0] for r in c.execute('SELECT id FROM automation_v2_tasks ORDER BY created DESC')]
    auto_sids=set()
    for tid in tasks:
        t=co.task(tid);auto_sids.add(t['session_id']);value='automation_v2:'+tid
        options.append(value);pairs[value]=('automation_v2',tid);labels[value]=t['plan']['scope']['metric']+' · '+tid[:8]+' · '+t['status']
    for row in a.sessions():
        if row['id'] in auto_sids:continue
        value='assistant:'+row['id'];options.append(value);pairs[value]=('assistant',row['id']);labels[value]=row['title']+' · '+row['id'][:8]
    with st.expander('关联已有研究',expanded=False):
        selected=st.selectbox('选择研究任务',options,format_func=lambda x:labels[x],key='chat_bind_select_'+cid)
        st.caption('明确关联后才能引用该研究。会话与研究任务是不同身份；历史消息保留原来源。')
        if st.button('确认关联此研究',disabled=not selected,key='chat_bind_'+cid):
            try:
                service.bind(cid,*pairs[selected]);st.query_params.pop('chat_flow',None);st.rerun()
            except (ValueError,RuntimeError,OSError):st.error('该任务的数据、合同或报告来源未通过核验，未替换当前研究。')

def _sidebar(service,cid,source):
    with st.sidebar:
        st.html(brand_html())
        if st.button('新建研究',icon=':material/add:',type='primary',width='stretch',key='chat_new'):
            switch(service.create(request_key=uuid.uuid4().hex).id)
        search=st.text_input('搜索会话',placeholder='搜索研究或会话',key='chat_history_search',label_visibility='collapsed')
        with st.popover('会话设置'):
            title=st.text_input('会话名称',value=service.label(cid),max_chars=64,key='chat_title_'+cid)
            if st.button('保存名称',key='chat_rename_'+cid):
                try:service.rename(cid,title);st.rerun()
                except ValueError:st.error('请输入1至64字的名称。')
        all_sessions=service.sessions()
        # Explicit presentation-only demo filter; no title heuristics or deletion.
        demo={x for x in os.environ.get('CAUSALOPS_DEMO_HIDDEN_CHATS','').split(',') if re.fullmatch('[a-f0-9]{32}',x)}
        hidden=sum(r.id in demo and r.id!=cid for r in all_sessions)
        include=st.checkbox('包含验收会话',key='chat_include_demo',help='仅影响本机演示列表，原会话与来源不会删除。') if hidden else False
        if hidden and not include:st.caption('演示列表已收起 '+str(hidden)+' 个验收会话')
        sessions=[r for r in all_sessions if (include or r.id not in demo or r.id==cid) and (not search or search.casefold() in service.label(r.id).casefold())]
        labels={r.id:service.label(r.id) for r in sessions}
        ordinal={}
        for row in sorted(sessions,key=lambda r:(r.created,r.id)):
            title=labels[row.id];ordinal[row.id]=1+sum(labels[other.id]==title for other in sessions if (other.created,other.id)<(row.created,row.id))
        def entry(row):
            title=labels[row.id]
            duplicate=sum(v==title for v in labels.values())>1
            display=title+(' · '+str(ordinal[row.id]) if duplicate else '')
            bound=bool(row.active_binding_id)
            if st.button(display,key='chat_session_'+row.id,type='primary' if row.id==cid else 'secondary',width='stretch',
                         icon=':material/science:' if bound else ':material/chat_bubble_outline:',help=title+(' · 已关联研究' if bound else ' · 尚未关联研究')):switch(row.id)
        st.caption('最近会话')
        for row in sessions[:7]:entry(row)
        if len(sessions)>7:
            with st.expander('历史会话'):
                for row in sessions[7:]:entry(row)
        _associate(service,cid)
        with st.expander('研究工具与设置'):
            for route,label in [('configure','数据与研究配置'),('review','方案审核'),('execution','研究执行'),('results','研究结果'),('evidence','证据诊断'),('decisions','研究决定'),('assistant','原单次研究'),('analysis','专业统计方法'),('history','已有研究任务'),('examples','公开案例'),('settings','模型与隐私'),('guide','使用说明')]:
                _legacy_link(label,route,source,key='chat_nav_'+route)
        st.caption('本地单用户 Beta\n\n聊天 ≠ 批准 · 决定 ≠ 执行')

def _start_formal(service,cid,source,*,public=False):
    from causalops.application.chat_workflow import ChatWorkflow
    flow=ChatWorkflow(service)
    h=flow.begin(cid,request_key=uuid.uuid4().hex,public=public)
    st.query_params.update(chat_flow=h.id)
    meta=source.get('metadata')
    if meta and meta['domain']=='automation_v2':
        st.query_params['automation']=meta['subject_id'];go('review')
    else:
        st.query_params.pop('automation',None)
        st.session_state.pop('automation_create_key',None)
        st.session_state.pop('automation_source_review',None)
        st.session_state['automation_data_source']='公开 Hillstrom 营销实验' if public else '使用自己的数据开展研究'
        go('configure')


def _artifact_summary(service,cid):
    from causalops.application.chat_artifacts import artifacts
    try:return artifacts(service,cid,report_id=st.query_params.get('diagnostic_report'))
    except (ValueError,RuntimeError,OSError,KeyError):return dict(diagnostic=None,decisions=dict(count=0,history_count=0),error='诊断或决定来源未通过核验，请从本研究重新打开；未展示其他报告。')


def _panel(service,cid,source):
    from causalops.application.automation_results import STATES
    with st.container(key='chat_artifacts'):
        st.subheader('研究产物',anchor=False)
        meta=source['metadata']
        if not meta:st.info('尚未关联研究。发送数据或选择已有研究后查看正式产物。');return
        st.markdown('**'+meta['title']+'**')
        sc=meta['scope'];metric=sc.get('metric') or sc.get('metric_label') or sc.get('outcome') or '待确认'
        st.caption('指标 · '+str(metric))
        st.caption('窗口 · '+str(sc.get('window') or sc.get('metric_window') or '待确认'))
        view=source['view'];contract=meta['contract_ref']
        if view:
            t=view['task'];approval=bool(view['report'] and view['report'].get('approval_id'))
            with service.ws.connection() as db:
                approved=db.execute('SELECT revoked FROM automation_v2_approvals WHERE task_id=?',(t['id'],)).fetchone()
            approval_label='已批准' if approved and not approved[0] and not view['binding_error'] else '历史批准，仅供追溯' if approved else '尚未批准'
            st.write(STATES.get(t['status'],t['status'])+' · 计划 v'+str(t['plan']['version'])+' · '+approval_label)
            st.caption(str(len(meta['run_ids']))+' 个实际统计运行')
            if view['report']:
                if st.button('打开完整研究报告',type='primary',key='chat_full_report',width='stretch'):go('chat_report')
            elif st.button('查看计划与正式审核',type='primary',key='chat_review',width='stretch'):_legacy_link_go('review',source)
            if t['status'] in ('approved','running','pause_requested','paused','interrupted','cancelled','blocked'):
                _legacy_link('执行与核查恢复','execution',source,key='chat_execution')
        else:
            st.caption(str(len(meta['run_ids']))+' 个实际统计运行 · 合同'+(' v'+str(contract['version']) if contract else '待确认'))
            if st.button('确认数据并配置研究',type='primary',key='chat_confirm_data',width='stretch'):_start_formal(service,cid,source)
        extras=source.get('_artifacts') or _artifact_summary(service,cid)
        if extras.get('error'):st.warning(extras['error'])
        links=st.columns(2)
        with links[0]:_legacy_link('证据诊断','evidence',source,key='chat_product_evidence',tertiary=True)
        with links[1]:_legacy_link('研究决定','decisions',source,key='chat_product_decisions',tertiary=True)
        if extras['diagnostic']:
            d=extras['diagnostic'];st.caption('诊断 v'+str(d['version'])+' · '+('来源已核验' if d['source_current'] else '来源需要重新核对'))
        if extras['decisions']['count']:st.caption('已保存 '+str(extras['decisions']['count'])+' 条研究决定 · 无执行权限')
        if view:
            with st.expander('方案与执行详情'):
                if st.button('修改条件或查看正式计划',key='chat_revise'):_legacy_link_go('review',source)
                for step in view['steps']:st.caption(step['name']+' · '+STATES.get(step['status'],step['status']))
                if t.get('reason'):st.warning(t['reason'])
        with st.expander('来源与技术详情'):
            st.json(meta)
            if view:st.json(dict(budget=view['budget'],execution_warning=view['binding_error']))


def _legacy_link_go(route,source):
    meta=source.get('metadata')
    if meta and not st.query_params.get('chat_flow'):
        from causalops.application.chat_workflow import ChatWorkflow
        service=ChatService(ResearchService(AssistantWorkspace()))
        cid=st.query_params.get('chat')
        if cid:st.query_params['chat_flow']=ChatWorkflow(service).begin(cid,request_key=uuid.uuid4().hex).id
    if meta and meta['domain']=='automation_v2':st.query_params['automation']=meta['subject_id']
    elif meta:st.query_params['assistant']=meta['assistant_session_id'];route='assistant'
    go(route)


def _answer_markdown(answer):
    text=answer.get('text','本轮未保存可核验的回复。')
    if answer.get('scope')=='verified_automation_report':
        # Presentation only; original response, values and citations stay intact.
        text=re.sub(r'\*\*(范围|研究限制|绝对差|描述性差异|原工具95%区间|区间未执行)\*\*',r'\1',text)
    return text


def _reader_space(reserve):
    """Presentation space for actual composer feedback/status, not task progress."""
    return '<style>[class*="st-key-chat_scroll_"],.st-key-chat_panel_scroll{height:clamp(220px,calc(100dvh - '+str(reserve)+'px),700px)!important}</style>'


def _messages(service,cid,current_meta=None):
    messages=service.messages(cid)
    if not messages:
        st.html('<div class="co-chat-welcome"><h1>今天想研究什么？</h1><p>提出目标，确认数据与研究条件，让每个结论有据可查。</p></div>')
        st.markdown('上传一张 **CSV / Parquet**，或从公开营销案例开始。当前自动化支持单表、双组、二元结果。')
    for index,item in enumerate(messages):
        ref=item['reference'];answer=item['answer'] or {}
        workflow=answer.get('source')=='正式研究工作流'
        if not workflow:
            with st.chat_message('user'):st.write(ref.question)
        with st.chat_message('assistant'):
            if not item['available']:st.error(item['error']);continue
            if ref.status=='running':st.info('此轮仍在处理或等待核查，刷新不会重复发送。');continue
            if ref.status=='interrupted':st.warning('此轮回答中断，未自动重发；可检查来源后另行提问。');continue
            if workflow:
                st.caption(answer.get('text','正式研究流程已保存'))
                continue
            if not item['binding'] and current_meta:
                st.caption('消息发送时尚未关联研究；当前绑定见研究面板。')
            if item['binding'] and current_meta and item['binding'].subject_id!=current_meta['subject_id']:
                st.caption('此前研究 · '+str(item['binding'].metadata['scope'].get('metric') or '历史结果')+'（不是当前研究）')
            elif item['binding'] and current_meta and item['binding'].metadata!=current_meta:
                st.caption('消息发送时的研究版本；当前条件见研究面板。')
            with st.container(key='chat_body_'+ref.id):
                parts=display_parts(answer)
                for kind,text in parts:
                    if kind=='lead':st.html(lead_html(text))
                body='\n\n'.join(text for kind,text in parts if kind=='markdown')
                if body:st.markdown(body)
            facts=answer.get('facts',[])
            if facts and answer.get('scope')!='verified_automation_report':
                for f in facts[:8]:st.write(f['text']+'：'+str(f['value']))
            if index==len(messages)-1 and current_meta and item['binding'] and item['binding'].subject_id==current_meta['subject_id']:
                if any(term in ref.question for term in ('诊断','证据质量','研究决定','决策历史')):
                    nav=st.columns(2)
                    with nav[0]:_legacy_link('查看研究诊断','evidence',dict(metadata=current_meta),key='chat_answer_diagnostics')
                    with nav[1]:_legacy_link('记录或查看研究决定','decisions',dict(metadata=current_meta),key='chat_answer_decisions')
            with st.container(key='chat_source_'+ref.id):
                with st.expander('查看回答依据',expanded=False):
                    st.caption(answer.get('source','已保存服务响应'))
                    if item['binding']:st.caption('研究 '+item['binding'].subject_id+' · 绑定版本 '+str(item['binding'].version))
                    st.json(dict(run_ids=answer.get('run_ids',[]),message_id=ref.id,status=ref.status))
                    if facts:st.json(facts)


def _journey(service,cid,source):
    meta=source['metadata'];view=source['view']
    if not meta:
        if st.button('体验公开营销研究',key='chat_start_public'):_start_formal(service,cid,source,public=True)
    elif not view:
        if st.button('确认数据并生成候选方案',type='primary',key='chat_start_config'):_start_formal(service,cid,source)
    else:
        from causalops.application.automation_results import STATES
        t=view['task']
        if t['status']=='candidate':
            if st.button('查看候选与正式审核',type='primary',key='chat_start_review'):_legacy_link_go('review',source)
        elif t['status']!='completed':
            if st.button('查看执行与恢复',key='chat_start_execution'):_legacy_link_go('execution',source)
        elif st.button('阅读完整报告',type='primary',key='chat_result_link'):go('chat_report')


def render(*,focused=False):
    st.html('<style>'+CHAT_CSS+'</style>')
    surface=st.empty()
    service=ChatService(ResearchService(AssistantWorkspace()))
    cid=st.query_params.get('chat')
    if not cid:
        cid=service.create(request_key=uuid.uuid4().hex).id;st.query_params['chat']=cid
    identity=(cid,focused)
    if st.session_state.get('chat_reading_identity')!=identity:
        surface.empty();surface.info('正在核验当前会话与研究来源…')
    try:
        session=service.session(cid);service.reconcile(cid)
        from causalops.application.chat_workflow import ChatWorkflow
        flow=ChatWorkflow(service)
        handoff=st.query_params.get('chat_flow') or flow.active(cid)
        if handoff:st.query_params['chat_flow']=handoff
        try:
            source=flow.refresh(cid,handoff) if handoff else service.view(cid)
            if handoff and source['view'] and source['view']['task']['status']=='completed':flow.answer_goal(cid,handoff)
            source_error=None
        except (ValueError,RuntimeError,OSError):
            source=dict(metadata=None,view=None,runs=[],execution_warning=None)
            source_error='当前研究来源已变化或缺失。未自动替换旧绑定，请核对数据、计划与报告后明确关联。'
    except ValueError:
        with st.sidebar:
            st.html(brand_html())
            if st.button('新建研究'):switch(service.create().id)
        surface.error('此会话不存在或身份无效，未自动打开其他会话。');return
    binding=service.session(cid).active_binding_id
    full_identity=(cid,focused,binding)
    if st.session_state.get('chat_source_identity')!=full_identity:surface.empty()
    st.session_state['chat_source_identity']=full_identity
    st.session_state['chat_reading_identity']=identity
    _sidebar(service,cid,source)
    meta=source['metadata'];model=None
    panel=st.query_params.get('panel')=='1'
    with surface.container():
        with st.container(key='chat_identity'):
            title=service.label(cid)
            if source_error:st.error(source_error)
            if st.session_state.get('chat_return_error'):st.warning(st.session_state.pop('chat_return_error'))
            from causalops.application.automation_results import STATES
            metric=(meta['scope'].get('metric') or meta['scope'].get('metric_label') or '数据待确认') if meta else '新会话'
            state=STATES.get(source['view']['task']['status'],source['view']['task']['status']) if source['view'] else '已登记数据' if meta else '尚未关联研究'
            st.html('<div class="co-chat-head" data-chat-id="'+cid+'"><strong title="'+escape(title,quote=True)+'">'+escape(title)+'</strong><span class="co-chat-context" data-chat-context="'+cid+'" data-research="'+escape(meta['subject_id'] if meta else '')+'">'+escape(metric+' · '+state)+'</span></div>')
        if focused:
            if st.button('返回原对话',key='chat_return'):go('home')
            if source['view']:
                with st.container(key='chat_focused'):
                    from causalops.ui.automation_app import _report
                    _report(source['view'],service.s.automation_v2())
            else:st.warning('当前没有可核验的自动化整体报告。单次研究请使用原报告入口。')
            return
        with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center'):
            if not (panel and source['view'] and source['view']['report']):_journey(service,cid,source)
            if st.button('关闭研究面板' if panel else '展开研究面板',key='chat_panel_toggle'):
                if panel:st.query_params.pop('panel',None)
                else:st.query_params['panel']='1'
                st.rerun()
        if panel:st.html('<style>@media(max-width:1140px){[data-testid=stColumn]:has(.st-key-chat_reading){display:none}}</style>')
        cols=st.columns([2.4,1] if panel else [1],gap='medium')
        with cols[0]:
            with st.container(key='chat_reading'):
                # Follow explicit sends or newly opened history. Composer settings
                # rerun only their fragment and leave the old-message reader intact.
                follow=st.session_state.pop('chat_follow_'+cid,False) or identity!=st.session_state.get('chat_scroll_identity')
                st.session_state['chat_scroll_identity']=identity
                epoch=st.session_state.get('chat_scroll_epoch_'+cid,0)
                with st.container(height=500,border=False,key='chat_scroll_'+cid+'_'+str(epoch),autoscroll=follow):
                    _messages(service,cid,meta)
        if len(cols)>1:
            with cols[1]:
                with st.container(height=500,border=False,key='chat_panel_scroll'):_panel(service,cid,source)
    # The bottom input uses a fragment: settings do not rebuild the reading area.
    with st.bottom:
        with st.container(key='chat_composer_frame'):
            bottom_cols=st.columns([2.4,1] if panel else [1],gap='medium')
            with bottom_cols[0]:_composer(service,cid,source,source_warning=bool(source_error))
            if panel:
                with bottom_cols[1]:
                    with st.container(key='chat_composer_spacer'):pass


@st.fragment
def _composer(service,cid,source,*,source_warning=False):
    meta=source['metadata'];model=None
    with st.container(key='chat_composer_area'):
        mode=st.session_state.get('chat_mode_'+cid,'本地确定性路径')
        with st.container(horizontal=True,horizontal_alignment='distribute',vertical_alignment='center',gap='xsmall'):
            st.caption((str(meta['scope'].get('metric') or '数据待确认')[:6] if meta else '未关联研究')+' · '+('本地' if mode=='本地确定性路径' else '模型辅助'),width='content')
            if st.button('最新消息',type='tertiary',key='chat_latest_'+cid):
                st.session_state['chat_follow_'+cid]=True
                st.session_state['chat_scroll_epoch_'+cid]=st.session_state.get('chat_scroll_epoch_'+cid,0)+1
                st.rerun(scope='app')
            settings=st.popover('回答路径')
        with settings:
            mode=st.radio('本轮回答路径',['本地确定性路径','可选模型辅助'],key='chat_mode_'+cid)
            if meta and meta['domain']=='assistant':
                from causalops.ui.model_setup import task_model
                model=task_model(service.a,meta['assistant_session_id'])
            else:st.caption('自动化报告使用本地保存事实。外部模型连接与任务许可分别管理；未授权不外发。')
        flash=st.session_state.get('chat_feedback_'+cid)
        if flash:st.caption(flash)
        # Reserve space for the actual source error banner, without changing its
        # meaning or using DOM measurements to decide research state.
        reserve=(400 if flash else 360)+(160 if source_warning else 0)
        st.html(_reader_space(reserve))
        prompt=st.chat_input('询问当前研究，或添加数据附件',accept_file=True,file_type=['csv','parquet'],max_upload_size=20,submit_mode='disable',key='chat_composer_'+cid)
    if prompt:
        key=st.session_state.setdefault('chat_request_'+cid,uuid.uuid4().hex)
        try:
            st.html(_reader_space(480+(160 if source_warning else 0)))
            with st.status('正在核验来源并处理本轮请求',expanded=False) as status:
                outcomes=[]
                for i,file in enumerate(prompt.files):
                    outcomes.append(service.import_data(cid,file.getvalue(),name=file.name,request_key=key+':file:'+str(i)))
                if prompt.files:
                    st.query_params.pop('chat_flow',None);st.query_params.pop('automation',None)
                if prompt.text:outcomes.append(service.submit(cid,prompt.text,request_key=key+':text',mode='model' if mode=='可选模型辅助' else 'local',model=model))
                failed=any(x.status in ('failed','blocked','interrupted') for x in outcomes)
                status.update(label='本轮未完成，请查看消息说明' if failed else '本轮处理完成',state='error' if failed else 'complete')
            st.session_state['chat_feedback_'+cid]='本轮处理未完成 · 原因已保存在消息中' if failed else '本轮处理完成 · 已保存'
            st.session_state.pop('chat_request_'+cid,None);st.session_state['chat_follow_'+cid]=True;st.rerun(scope='app')
        except (ValueError,RuntimeError,OSError):
            st.session_state.pop('chat_request_'+cid,None)
            st.session_state['chat_feedback_'+cid]='本轮未通过校验，请检查研究来源或附件后重试。'
            st.rerun(scope='app')
