"""Task-first interface; official model and local tools share one evidence-bound workspace."""
from __future__ import annotations
import json,copy,re
import pandas as pd
import streamlit as st
from causalops.assistant.service import AssistantWorkspace,profile,PROTECTED,Plan
from causalops.general.service import METHODS
from causalops.general.exploration import LABELS
from causalops.general.exploration_report import figures,render_report,display
from causalops.reporting import render_html_report
from causalops.ui.showcase_widgets import show_conclusion
from causalops.advanced import presentation as advanced_ui
METHODS={**METHODS,**advanced_ui.LABELS}

def safe_text(value):
    # Uploaded/model prose must never cause automatic third-party image requests.
    return re.sub(r'!\[[^\]]*\]\([^)]*\)', '[已移除外部图片]',str(value))

def show_sources(hits):
    if not hits['hits']:st.info(hits['note']);return
    for h in hits['hits']:
        with st.expander(h['title']+' · '+(('全文实证案例' if h.get('full_text_reviewed') else '实证案例（摘要）') if h['scope']=='empirical_example' else '方法规则')):
            for title,text in h['sections'].items():st.markdown('**'+title+'：** '+text)
            if h.get('estimand'):st.markdown('**目标量：** '+h['estimand']);st.code(h['formula'],language='text');st.caption(h['implementation'])
            for source in h['sources']:st.markdown('['+source['title']+']('+source['url']+')');st.caption(source['locator']+' · 核对日期 '+source['checked_on'])
            st.caption('知识卡 '+h['card_id']+' · 版本 '+h['version'])

def show_run(a,ref,sid):
    from causalops.assistant.export import attach_discussion
    rid=ref['run_id']
    if ref['kind']=='advanced':
        b=a.advanced.load(rid);advanced_ui.display(b)
        st.download_button('下载扩展研究图文报告',attach_discussion(advanced_ui.report(b),a.events(sid),rid,a.library),file_name='advanced-'+rid+'.html',mime='text/html',key='adv_report_'+rid)
        return
    if ref['kind']=='exploration':
        b=a.ex.load(rid);st.caption('运行 '+rid+' · 配置V'+str(b['design_version'])+' · 数据指纹 '+b['data_fingerprint'][:12])
        for line in b['conclusions']:st.write(line)
        if b['regression']:
            st.dataframe(display(b['regression']['coefficients']),hide_index=True,width='stretch');st.info(b['regression']['note'])
            if b['regression'].get('overdispersion_flag'):st.warning('Pearson离散度偏高；应检查计数均值设定、暴露与负二项等替代，当前不自动换模型。')
        for name,f in list(figures(b).items())[:5]:st.plotly_chart(f,key='assist_'+rid+'_'+name,width='stretch')
        with st.expander('完整数据质量与数值统计'):
            st.dataframe(display(b['summary']['columns']),hide_index=True,width='stretch');st.dataframe(display(b['summary']['numeric']),hide_index=True,width='stretch')
        x,y=st.columns(2);x.download_button('下载本次完整图文报告',attach_discussion(render_report(b),a.events(sid),rid,a.library),file_name='CausalOps-'+rid+'.html',mime='text/html',key='ah_'+rid);y.download_button('下载本次运行证据',json.dumps(b,ensure_ascii=False,indent=2),file_name=rid+'.json',key='aj_'+rid)
    else:
        b,run=a.ws.bundle(rid);st.caption('研究运行 '+rid+' · 草案 '+run.revision_id);show_conclusion(b)
        st.download_button('下载研究图文报告',attach_discussion(render_html_report(b),a.events(sid),rid,a.library),file_name='research-'+rid+'.html',mime='text/html',key='rh_'+rid)

def confirmations(step,index,pid,frame):
    cfg=step['config'];key=lambda k:'af_'+pid+'_'+str(index)+'_'+k;facts={}
    if step['tool']=='exploration' and cfg.get('method') in ('ols','logit','poisson'):
        if cfg.get('covariance','HC3')!='cluster':facts['independent_rows_reviewed']=st.checkbox('已确认本步骤的观测单位可按独立行推断（重复用户不能直接勾选）',key=key('iid'))
        facts['allow_complete_case']=st.checkbox('必要字段缺失时允许完整案例分析，并记录排除数',key=key('missing'))
        if cfg.get('method')=='poisson':facts['comparable_exposure_reviewed']=st.checkbox('计数结果的暴露时长和统计口径可比',key=key('exposure'))
    elif step['tool']=='advanced':
        return advanced_ui.confirmations(cfg,key)
    elif step['tool']=='research':
        st.caption('只需核对本步骤相关事实；未确认时程序会停止，不通过改问题绕过。')
        facts['assignment']=st.selectbox('实际分配机制',['unknown','observational','randomized'],format_func=lambda v:{'unknown':'尚不清楚','observational':'非随机/观察性','randomized':'确有随机分配依据'}[v],key=key('assignment'))
        facts['covariates_reviewed']=st.checkbox('已核对协变量在处理前测量，未包含未来/结果信息',key=key('cov'))
        facts['allow_complete_case']=st.checkbox('明确同意完整案例规则，并保留排除数',key=key('missing'))
        m=cfg.get('method')
        if m in ('psm','ipw','double_ml','aipw'):
            facts['exchangeability_declared']=st.checkbox('研究设计有依据支持给定已选协变量后的可交换性（非验证结论）',key=key('exchange'))
            facts['overlap_declared']=st.checkbox('有共同支撑依据，仍需执行诊断',key=key('overlap'))
        if m=='did':
            facts['panel_confirmed']=st.checkbox('已核对共同处理时点、从未处理对照和完整日级面板',key=key('panel'))
            facts['parallel_declared']=st.checkbox('已提供平行趋势的研究论证',key=key('parallel'))
            facts['no_anticipation_declared']=st.checkbox('已评估并声明无预期效应',key=key('anticipation'))
    return facts

def render_assistant():
    a=AssistantWorkspace();st.title('CausalOps · 分析助手')
    st.caption('把问题交给助手：理解数据 → 检索依据 → 提出计划 → 执行工具 → 解读证据。高级字段收在需要时才打开。')
    sessions=a.sessions();byid={s['id']:s for s in sessions};sid=st.query_params.get('assistant')
    with st.sidebar:
        if byid:
            chosen=st.selectbox('恢复分析任务',[None]+list(byid),index=list(byid).index(sid)+1 if sid in byid else 0,format_func=lambda x:'新建任务' if x is None else byid[x]['title']+' · '+x[-6:],key='assistant_history')
            if chosen and chosen!=sid:st.query_params['assistant']=chosen;st.rerun()
        if sid and st.button('新建另一项任务',key='assistant_new'):st.query_params.pop('assistant',None);st.rerun()
    if sid not in byid:
        st.markdown('**先上传表格。你不用先选模型或统计方法。**')
        upload=st.file_uploader('CSV / Parquet（不超过50MB、10万行、200列）',type=['csv','parquet','pq'],key='assistant_file')
        with st.expander('中文旧编码或特殊分隔符'):
            enc=st.selectbox('编码',['utf-8-sig','gb18030'],key='assistant_enc');sep=st.selectbox('分隔符',[',',';','\t'],format_func=lambda v:{',':'逗号',';':'分号','\t':'制表符'}[v],key='assistant_sep')
        title=st.text_input('任务名称（可选）',key='assistant_title',placeholder='例如：客户访问与转化研究')
        known=a.ws.uploads();uid=st.selectbox('或选择已导入的本地表',[None]+[x['upload_id'] for x in known],format_func=lambda x:'不使用已有表' if x is None else next(v['name']+' · '+x[-6:] for v in known if v['upload_id']==x),key='assistant_known')
        if st.button('创建任务并自动体检',type='primary',disabled=not upload and not uid):
            try:
                with st.status('正在建立任务与数据体检',expanded=True) as status:
                    if upload:uid=a.ws.ingest(upload.getvalue(),upload.name,encoding=enc,separator=sep)
                    sid=a.create(uid,title or (upload.name if upload else '本地分析任务'));st.write('数据已登记，只生成本地分析副本。')
                    p=a.propose(sid,'请先完成数据质量、缺失和分布的描述性体检');a.accept(p['id'],p['sha']);a.execute(p['id'],permit=True);status.update(label='数据体检已完成',state='complete')
                st.query_params['assistant']=sid;st.rerun()
            except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
        st.caption('此按钮授权本地描述性体检，不批准因果研究，也不向模型发送数据。')
        return
    s=a.session(sid);frame=a.ws.load_upload(s['upload_id']);pr=profile(frame)
    top=st.columns(3);top[0].metric('数据行数',f'{pr["rows"]:,}');top[1].metric('字段数',pr['columns']);top[2].metric('当前任务',sid[-8:])
    with st.expander('数据与字段：助手看到了什么'):
        st.dataframe(pd.DataFrame(pr['fields']).rename(columns={'field':'字段','dtype':'类型','missing_n':'缺失数','distinct_n':'非缺失不同值数','numeric':'是否数值','likely_identifier':'疑似标识/敏感字段','infinite_n':'无穷值数'}),hide_index=True,width='stretch');st.caption(pr['meaning'])
    with st.expander('模型与发送权限：默认不外发'):
        st.caption('仅支持DeepSeek官方API。密钥只在当前浏览器会话内存中，不写入数据库、报告或Git。刷新会话后可能需重新填写。')
        key=st.text_input('官方API密钥',type='password',key='assistant_api_key',help='粘贴后按回车提交，再勾选当前任务授权；密钥只在会话内存中。')
        st.caption('发送范围：过滤标识后的字段名、类型、缺失/唯一值数量、研究问题、近期对话及运行数字事实。不会发送原始行、ID值或论文全文。')
        consent=a.consent_enabled(sid);check=st.checkbox('允许当前数据任务发送上述范围',value=consent,key='assistant_consent_'+sid)
        if check!=consent:a.consent(sid,check)
        if st.button('查看确切发送内容示例',key='assistant_preview'):
            st.json(a.external_payload(sid,'请解释当前数据并提出分析计划'))
        st.caption('先核对问题中是否含敏感信息；工作台会阻断常见密钥、邮箱和长标识。授权只适用于此任务，可随时撤回。')
    model=None
    if st.session_state.get('assistant_api_key') and a.consent_enabled(sid):
        from causalops.llm.deepseek import DeepSeekStructuredModelClient
        try:model=DeepSeekStructuredModelClient(api_key=st.session_state['assistant_api_key'],base_url='https://api.deepseek.com',model='deepseek-flash',max_output_tokens=5000,max_retries=1)
        except RuntimeError as exc:st.warning(type(exc).__name__+'：可继续本地模式。')
    st.caption('当前：'+('DeepSeek官方模型提出计划/解释，统计由本机工具执行。' if model else '本地规则与证据模式；配置官方模型和当前任务权限后可使用自然语言智能规划。'))
    plans=a.plans(sid);tab_task,tab_result,tab_methods,tab_advanced,tab_trial=st.tabs(['任务与对话','结果与报告','方法依据 RAG','扩展研究设计','用户任务评测'])
    with tab_task:
        events=a.events(sid)
        for event in events:
            if event['kind']=='user':
                with st.chat_message('user'):st.write(event['body']['question'])
            if event['kind']=='answer':
                with st.chat_message('assistant'):
                    body=event['body'];st.caption(body['source']);st.write(safe_text(body['text']))
                    if body.get('display_note'):st.caption(body['display_note'])
                    if body['facts']:
                        with st.expander('核对本轮引用的运行事实'):
                            st.dataframe([{'引用':f.get('citation_label','本地事实'),'指标':f['text'],'精确值':str(f['value']),'完整证据标识':f['id'],'运行编号':f['run_id']} for f in body['facts']],hide_index=True,width='stretch')
                    for cid in body.get('citations',[]):
                        card=next((c for c in a.library.cards if c['card_id']==cid),None)
                        if card:
                            st.caption('方法依据：'+card['title']+' · '+('实证案例（摘要）' if card['scope']=='empirical_example' else '方法规则'))
                            for source_id in card['source_ids']:
                                source=a.library.catalog['sources'][source_id];st.markdown('['+source['title']+']('+source['url']+')')
            if event['kind']=='proposal':
                with st.chat_message('assistant'):st.write('已生成计划 V'+str(event['body']['version'])+'，来源：'+event['body']['source']+'。请核对下方任务卡。')
        if plans:
            p=plans[0];v=p['plan'];st.subheader('当前计划 V'+str(p['version'])+' · '+{'candidate':'等待查看与接受','accepted':'已接受，可继续执行','completed':'执行完成','rejected':'已放弃'}[p['state']])
            st.write(safe_text(v['objective']))
            for note in v['dataset_notes']:
                if not re.search(r'schema|steps\.\d|tool_placeholder|额外字段|额外键',note,re.I):st.caption(safe_text(note))
            for i,step in enumerate(v['steps']):
                cfg=step['config'];label=LABELS.get(cfg.get('method'),METHODS.get(cfg.get('method'),cfg.get('method','研究')))
                with st.container(border=True):
                    st.markdown('**'+str(i+1)+'. '+label+'**');st.write(safe_text(step['reason']))
                    st.caption('结果字段：'+str(cfg.get('outcome') or '分布/汇总')+'；分析字段：'+', '.join(cfg.get('numeric',[])+cfg.get('predictors',[])+cfg.get('covariates',[])))
                    if step['tool']=='advanced':st.caption('处理：'+str(cfg.get('treatment') or '按首次处理期/阈值定义')+'；工具：'+', '.join(cfg.get('instruments',[]))+'；运行变量：'+str(cfg.get('running') or '不适用')+'；期序：'+str(cfg.get('time') or '不适用')+'；首次处理期：'+str(cfg.get('cohort') or '不适用'))
            if v['required_questions']:
                with st.expander('需要补充的问题',expanded=True):
                    for q in v['required_questions']:st.write('• '+q)
            with st.expander('查看版本差异与完整计划'):
                if len(plans)>1:
                    old=plans[1]['plan'];st.json({'previous_version':plans[1]['version'],'changed_fields':[k for k in v if old.get(k)!=v[k]]})
                st.json(v)
            if p['state']=='candidate':
                with st.expander('调整字段与方法（本地生成新候选，不覆盖当前版本）'):
                    edited=copy.deepcopy(v)
                    for i,step in enumerate(edited['steps']):
                        cfg=step['config'];st.markdown('**步骤 '+str(i+1)+'**');key=lambda k:'edit_'+p['id']+'_'+str(i)+'_'+k
                        options=list(frame.columns)
                        numeric=[c for c in options if pd.api.types.is_numeric_dtype(frame[c])]
                        if step['tool']=='exploration':
                            cfg['numeric']=st.multiselect('统计数值字段',numeric,default=[c for c in cfg.get('numeric',[]) if c in numeric],key=key('numeric'))
                            cfg['categorical']=st.multiselect('统计分类字段',options,default=cfg.get('categorical',[]),key=key('cat'))
                            if cfg.get('method') in ('ols','logit','poisson'):
                                current=cfg.get('outcome');cfg['outcome']=st.selectbox('结果字段',numeric,index=numeric.index(current) if current in numeric else 0,key=key('outcome')) if numeric else None
                                cfg['predictors']=st.multiselect('自变量（不要选ID/未来结果）',[c for c in options if c!=cfg.get('outcome')],default=[c for c in cfg.get('predictors',[]) if c!=cfg.get('outcome')],key=key('predictors'))
                        elif step['tool']=='advanced':
                            st.caption('扩展方法映射请使用“扩展研究设计”选项卡生成新候选，避免静默改动研究口径。')
                        else:
                            def choose(label,field):
                                old=cfg.get(field);return st.selectbox(label,[None]+options,index=options.index(old)+1 if old in options else 0,key=key(field))
                            cfg['outcome']=choose('结果字段','outcome');cfg['treatment']=choose('处理字段','treatment');cfg['entity']=choose('实体/随机化单位ID','entity');cfg['cluster']=choose('聚类字段（可选）','cluster')
                            cfg['analysis_unit']=st.text_input('一行代表什么',value=cfg.get('analysis_unit',''),key=key('unit'))
                            values=sorted(frame[cfg['treatment']].dropna().astype(str).unique().tolist()) if cfg.get('treatment') else []
                            for role,label in [('control_value','对照值'),('treated_value','处理值')]:
                                old=cfg.get(role);cfg[role]=st.selectbox(label,[None]+values,index=values.index(old)+1 if old in values else 0,key=key(role))
                            cfg['covariates']=st.multiselect('处理前协变量',[c for c in options if c not in (cfg.get('outcome'),cfg.get('treatment'),cfg.get('entity'),cfg.get('cluster'))],default=[c for c in cfg.get('covariates',[]) if c not in (cfg.get('outcome'),cfg.get('treatment'),cfg.get('entity'),cfg.get('cluster'))],key=key('cov'))
                            metric=cfg.get('metric',{});metric['label']=st.text_input('指标名称',value=metric.get('label',''),key=key('label'));metric['unit']=st.text_input('指标单位',value=metric.get('unit',''),key=key('metricunit'));metric['window']=st.text_input('观察窗口与统计口径',value=metric.get('window',''),key=key('window'));metric.setdefault('kind','continuous');metric.setdefault('direction','neutral');metric.setdefault('ratio_scale',False);metric.setdefault('source','user_local_registration');cfg['metric']=metric
                    if st.button('保存为新候选计划',key='refine_'+p['id']):
                        try:a.refine(sid,edited);st.rerun()
                        except (ValueError,RuntimeError) as exc:st.error(str(exc))
            if p['state']=='candidate':
                x,y=st.columns(2)
                safe=all(t['tool']=='exploration' and t['config'].get('method') in ('descriptive','correlation') for t in v['steps'])
                if x.button('接受并执行探索计划' if safe else '接受此计划',type='primary',key='accept_'+p['id']):
                    a.accept(p['id'],p['sha'])
                    if safe:
                        with st.status('连续完成已授权的探索步骤',expanded=True) as status:
                            tasks=a.execute(p['id'],permit=True,progress=lambda i,step,state:st.write('步骤 '+str(i+1)+' · '+step['config']['method']+' · '+{'running':'正在运行','completed':'完成','blocked':'待补充'}[state]));status.update(label='执行完成' if all(t['state']=='completed' for t in tasks) else '需要补充信息',state='complete' if all(t['state']=='completed' for t in tasks) else 'error')
                    st.rerun()
                if y.button('放弃此计划',key='reject_'+p['id']):a.reject(p['id']);st.rerun()
            if p['state']=='accepted':
                facts={}
                with st.expander('仅在模型/研究步骤需要时核对事实',expanded=any(t['tool'] in ('research','advanced') or t['config'].get('method') in ('ols','logit','poisson') for t in v['steps'])):
                    for i,step in enumerate(v['steps']):
                        st.markdown('**步骤 '+str(i+1)+'**');facts[str(i)]=confirmations(step,i,p['id'],frame)
                if st.button('执行已接受计划，连续完成可运行步骤',type='primary',key='execute_'+p['id']):
                    with st.status('执行工具任务',expanded=True) as status:
                        def progress(i,step,state):st.write('步骤 '+str(i+1)+' · '+step['config'].get('method','研究')+' · '+{'running':'正在运行','completed':'完成','blocked':'需要补充'}[state])
                        tasks=a.execute(p['id'],permit=True,confirmations=facts,progress=progress);finished=[t['result']['run_id'] for t in tasks if t['state']=='completed'];st.session_state['assistant_focus_run_'+sid]=finished[-1] if finished else None;done=all(t['state']=='completed' for t in tasks);status.update(label='全部完成' if done else '已暂停，查看具体原因',state='complete' if done else 'error')
                    st.rerun()
            task_rows=a.tasks(p['id'])
            if task_rows:st.dataframe([{'步骤':t['ordinal']+1,'状态':{'pending':'等待执行','running':'执行中','completed':'已完成','blocked':'待补充'}[t['state']],'计算用时（秒）':(t['result'] or {}).get('seconds')} for t in task_rows],hide_index=True,width='stretch')
            for t in task_rows:
                if t['state']=='blocked':st.warning('步骤'+str(t['ordinal']+1)+'：'+t['result']['error'])
            if p['state']=='completed':st.success('计划已完成。可在“结果与报告”查看，或继续提问/提出新任务。刷新不重复执行。')
        action=st.radio('本轮目标',['自动判断','提出/修改分析计划','解释已有结果','方法咨询'],horizontal=True,key='assistant_action')
        q=st.chat_input('例如：比较 total_bill 与 tip 的关系；或解释刚才的结果与局限',key='assistant_chat')
        if q:
            try:
                intent='plan' if action=='提出/修改分析计划' or (action=='自动判断' and __import__('re').search('帮我分析|分析一下|做一个|加上|改用|重新分析|生成.*计划|建模|做.*回归|比较.*关系',q)) else 'answer'
                with st.spinner('正在检索方法并'+('生成候选计划' if intent=='plan' else '核对运行证据')):
                    if intent=='plan':a.propose(sid,q,model)
                    else:
                        answer=a.ask(sid,q,model)
                        if answer.get('facts'):st.session_state['assistant_focus_run_'+sid]=answer['facts'][0]['run_id']
                st.rerun()
            except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc));st.info('未展示未经校验的模型结果；已有运行和原始数据保持不变。')
    with tab_result:
        completed=[]
        for p in plans:
            for t in a.tasks(p['id']):
                if t['state']=='completed':completed.append(t['result'])
        if not completed:st.info('先接受并运行一个计划。')
        else:
            focus=st.session_state.pop('assistant_focus_run_'+sid,None)
            byrun={r['run_id']:r for r in completed};selector='assistant_result_runid_'+sid
            newest=next((p for p in plans if any(t['state']=='completed' for t in a.tasks(p['id']))),None)
            if newest and st.session_state.get('assistant_seen_result_plan_'+sid)!=newest['id']:
                if focus is None:focus=next(t['result']['run_id'] for t in reversed(a.tasks(newest['id'])) if t['state']=='completed')
                st.session_state['assistant_seen_result_plan_'+sid]=newest['id']
            if focus is None and selector not in st.session_state:
                answers=[e['body'] for e in a.events(sid) if e['kind']=='answer' and e['body'].get('facts')]
                if answers:focus=answers[-1]['facts'][0]['run_id']
            if focus in byrun:st.session_state[selector]=focus
            elif st.session_state.get(selector) not in byrun:st.session_state[selector]=next(iter(byrun))
            st.caption('默认定位最近运行/回答引用的运行；选择绑定运行编号，新增计划不会把旧序号错指到另一结果。')
            rid=st.selectbox('选择本任务已保存运行',list(byrun),format_func=lambda rid:LABELS.get(byrun[rid].get('method'),METHODS.get(byrun[rid].get('method'),byrun[rid]['kind']))+' · '+rid[:8],key=selector)
            show_run(a,byrun[rid],sid)
    with tab_methods:
        query=st.text_input('检索方法、条件、诊断或商业/学术案例',value='如何选择方法并检查识别条件',key='assistant_search')
        if query:show_sources(a.library.search(query))
        if st.button('为只读MCP导出当前任务的数字证据',key='assist_mcp_export'):
            count=a.export_readonly(sid);st.success('已导出'+str(count)+'个已保存运行；不含原始行或ID值。')
        st.caption('本地稀疏检索；知识库不含客户表格或聊天。实证案例区分摘要与已核对全文，来源显示具体范围和页码；文献不证明当前数据的识别条件。')
    with tab_advanced:
        advanced_ui.builder(a,sid,frame)
        with st.expander('跨 Agent 方法审阅（A2A，本机只读）'):
            st.caption('交给独立方法审阅服务；只传本轮方法和问题，不发送表格行，不接受、批准或执行。此服务使用规则和来源卡，不冒充另一个大模型。')
            peer_method=st.selectbox('审阅的方法',['iv_2sls','rd_sharp','staggered_did'],key='a2a_method_'+sid)
            peer_question=st.text_input('发给审阅者的问题',value='应当检查哪些识别条件和失败情形？',key='a2a_question_'+sid)
            if st.button('请求本机A2A审阅',key='a2a_request_'+sid):
                try:
                    import asyncio
                    from causalops.protocols.reviewer_server import request_review
                    from causalops.protocols.local_services import ensure_reviewer
                    ensure_reviewer(a.ws.root)
                    reply=asyncio.run(request_review({'action':'review_method','method':peer_method,'question':peer_question}))
                    a.event(sid,'a2a_review',{'transport':'A2A1.0_JSONRPC_loopback','events':reply,'execution_performed':False})
                    st.success('真实跨进程审阅已返回，未修改当前计划。');st.json(reply)
                except Exception as exc:st.error('本机审阅服务未完成：'+type(exc).__name__+'。请按扩展手册启动8512端口服务。')
    with tab_trial:
        from causalops.ui.user_trial import render_user_trial
        render_user_trial(a.ws)
