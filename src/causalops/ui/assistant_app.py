"""Task-first interface; official model and local tools share one evidence-bound workspace."""
from __future__ import annotations
import json,copy,re
import pandas as pd
import streamlit as st
from causalops.ui.source_labels import show_source
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
        with st.expander(h['title']+' · '+(('实证文献（已核对相关全文页）' if h.get('full_text_reviewed') else '实证案例（摘要）') if h['scope']=='empirical_example' else '方法规则')):
            for title,text in h['sections'].items():st.markdown('**'+title+'：** '+text)
            if h.get('estimand'):st.markdown('**目标量：** '+h['estimand']);st.code(h['formula'],language='text');st.caption(h['implementation'])
            for source in h['sources']:show_source(source);st.caption(source['locator']+' · 核对日期 '+source['checked_on'])
            st.caption('知识卡 '+h['card_id']+' · 版本 '+h['version'])
            for span in h.get('matched_sections',[]):st.caption('命中章节：'+span['section']+' · 原创方法摘要指纹 '+span['note_sha256'][:12])
            st.caption('原文核对范围以来源登记为准；方法摘要不是论文逐字引文。')

def chart_context(a,sid,rid):
    from causalops.application.task_conclusions import source_dictionary
    body,_=source_dictionary(a,sid,rid)
    labels={f['field']:f['meaning']+'（'+f['field']+'）' for f in body.get('fields',[]) if f.get('meaning')}
    units={f['field']:f['unit'] for f in body.get('fields',[]) if f.get('unit')}
    target=body.get('outcome')
    if target and body.get('metric_label'):labels[target]=body['metric_label']+'（'+target+'）'
    if target and body.get('metric_unit'):units[target]=body['metric_unit']
    return labels,units

def primary_chart_key(bundle,focus,charts):
    if bundle.get('regression'):return '关联系数'
    if bundle['method']=='correlation':return next((key for key in ('两变量相关系数','相关矩阵') if key in charts),None)
    if bundle['summary']['trend']:return next((k for k in charts if k.startswith('时间汇总_')),None)
    return next((k for k in charts if k in ('分布_'+str(focus),'频数_'+str(focus))),next(iter(charts),None))

def show_run(a,ref,sid,*,compact=False):
    from causalops.assistant.export import attach_discussion
    rid=ref['run_id']
    from causalops.application.task_conclusions import build_task_conclusion,attach_task_conclusion,TITLES
    conclusion=build_task_conclusion(a,sid,rid)
    saved=a.ex.load(rid) if ref['kind']=='exploration' else None
    from causalops.application.research_report import run_quality
    rq=run_quality(a,sid,rid)
    focus=(conclusion.get('focus') or {}).get('field')
    titles=conclusion.get('titles',TITLES)
    sections=conclusion['sections']
    from causalops.results.rate_units import rate_contrast
    from causalops.ui.group_chart import group_chart
    rates=rate_contrast(a.ws.bundle(rid)[0]) if ref["kind"]=="research" else None
    headline = []
    if saved and saved['method']=='descriptive' and focus:
        field=next((r for r in saved['summary']['numeric'] if r['field']==focus),None)
        if field and field['finite_n']:
            headline=[('有效样本',f"{field['finite_n']:,}"),('均值',f"{field['mean']:.3f}"),('中位数',f"{field['median']:g}")]
    elif ref['kind']=='research':
        from causalops.ui.showcase_support import overview_numbers
        values=overview_numbers(a.ws.bundle(rid)[0])
        if values['estimate'] is not None:
            headline=[('估计差异',f"{values['estimate']:.4g} {values['unit']}")]
    if rates:
        headline=[('对照组比例',f"{rates['control_rate']:.2%}"),('处理组比例',f"{rates['treated_rate']:.2%}"),
                  ('绝对差',f"{rates['pp']:+.2f} 个百分点")]
    with st.container(key='panel_conclusion_'+rid):
        st.subheader('本次分析结果')
        st.text(rq['brief']['question'])
        if rates:
            st.write('处理组的观测比例'+('高于' if rates['pp']>0 else '低于' if rates['pp']<0 else '等于')+'对照组。')
        else:
            st.write(safe_text(sections['meaning']))
        st.caption('适用对象：'+rq['brief']['population'])
    if headline:
        for col,(label,value) in zip(st.columns(len(headline)),headline):col.metric(label,value)
    left,right=st.columns(2,gap='medium')
    with left.container(key='panel_mainchart_'+rid):
        st.subheader('统计图表')
        if rates:
            st.html(group_chart(rates))
        elif saved is not None:
            labels,units=chart_context(a,sid,rid)
            charts=figures(saved,focus=focus,labels=labels,units=units)
            key=primary_chart_key(saved,focus,charts)
            if key in charts:st.plotly_chart(charts[key],key='focus_preview_'+rid,width='stretch')
            else:st.caption('本次运行没有可绘制的主图。')
        elif ref['kind']!='advanced':
            from causalops.ui.showcase_support import conclusion_figures
            charts=conclusion_figures(a.ws.bundle(rid)[0])
            if charts:st.plotly_chart(next(iter(charts.values())),key='focus_preview_'+rid,width='stretch')
            else:st.caption('本次运行未保存可绘制的效应估计。')
        else:
            st.write(safe_text(sections['baseline']))
            st.caption('进阶方法的专用输出见下方统计诊断。')
    with right.container(key='panel_summary_'+rid):
        st.subheader('指标口径与不确定性')
        if rates:
            st.write('绝对差按处理组比例减去对照组比例计算，单位为百分点。')
            if rates['ci_pp']:
                lo,hi=rates['ci_pp']
                st.write(f'差值的置信区间为 {lo:.2f} 至 {hi:.2f} 个百分点，采用本次运行的区间设置。')
        else:
            st.write(safe_text(sections['magnitude']))
        if focus:st.caption('目标指标：'+str(conclusion['focus']['label']))
    bounds,follow=st.columns(2,gap='medium')
    with bounds.container(key='panel_limits_'+rid):
        st.subheader('适用范围与限制')
        st.write(rq['method']['limits'])
        for issue in rq['failed_diagnostics']:st.warning(issue)
        with st.expander('数据来源与样本口径'):
            st.write('估计对象：'+rq['method']['estimand'])
            st.write('数据依据：'+rq['brief']['source'])
            st.write('观察期间：'+rq['brief']['window'])
            for label,value in rq['sample_flow'].items():st.write(label+'：'+str(value))
    with follow.container(key='panel_next_'+rid):
        st.subheader('后续分析')
        st.write(safe_text(sections['action']))
        with st.expander('后续研究建议'):
            for item in rq['next_steps']:st.write('• '+item)
    report=make_report(a,ref,sid,conclusion)
    st.download_button('导出本次分析报告',report,file_name='CausalOps-'+rid+'.html',mime='text/html',key='primary_report_'+rid)
    with st.expander('研究报告预览',expanded=False):
        from html import escape
        pairs=[('研究对象',rq['brief']['population']),('观察期间',rq['brief']['window']),('估计目标',rq['method']['estimand']),('数据来源',rq['brief']['source'])]
        rows=''.join('<div><dt>'+name+'</dt><dd>'+escape(str(value))+'</dd></div>' for name,value in pairs)
        paper_title=(str(conclusion['focus']['label'])+'分布') if saved and saved['method']=='descriptive' and focus else str(rq['brief']['question'])
        paper_metrics='<div class="co-paper-metrics">'+''.join('<div><strong>'+escape(str(value))+'</strong><small>'+escape(label)+'</small></div>' for label,value in headline)+'</div>' if headline else ''
        st.html('<article class="co-paper"><small>CAUSALOPS / 研究报告</small><h2>'+escape(paper_title)+'</h2><hr><h3>主要发现</h3>'+paper_metrics+'<p>'+escape(str(sections['magnitude']))+'</p><h3>研究范围与方法</h3><dl class="co-kv">'+rows+'</dl><h3>不确定性与使用边界</h3><p>'+escape(str(rq['method']['limits']))+'</p><div class="co-note">运行编号：'+escape(rid)+'</div></article>')
    if compact:
        with st.expander('统计图表、诊断与报告'):_show_run_details(a,ref,sid,conclusion,report)
    else:_show_run_details(a,ref,sid,conclusion,report)

def make_report(a,ref,sid,conclusion):
    from causalops.assistant.export import attach_discussion
    from causalops.application.task_conclusions import attach_task_conclusion
    rid=ref['run_id'];focus=(conclusion.get('focus') or {}).get('field')
    if ref['kind']=='exploration':
        labels,units=chart_context(a,sid,rid);report=render_report(a.ex.load(rid),focus=focus,labels=labels,units=units)
    elif ref['kind']=='advanced':report=advanced_ui.report(a.advanced.load(rid))
    else:report=render_html_report(a.ws.bundle(rid)[0])
    from causalops.application.research_report import run_quality,append_quality
    report=append_quality(report,run_quality(a,sid,rid))
    report=attach_discussion(attach_task_conclusion(report,conclusion),a.events(sid),rid,a.library)
    from causalops.ui.visual_layout import report_paper
    if ref['kind']=='research':
        from causalops.results.rate_units import rate_contrast
        from causalops.ui.group_chart import group_chart
        from html import escape
        rates=rate_contrast(a.ws.bundle(rid)[0])
        if rates and '</h1>' in report:
            study=run_quality(a,sid,rid)['brief']['question']
            cover='<section><h2>'+escape(study)+'</h2><p>处理组与对照组绝对差为 '+f"{rates['pp']:+.2f}"+' 个百分点。</p>'+group_chart(rates)+'</section>'
            report=report.replace('</h1>', '</h1>'+cover,1)
    return report_paper(report)


def _show_run_details(a,ref,sid,conclusion,report):
    from causalops.assistant.export import attach_discussion
    from causalops.application.task_conclusions import attach_task_conclusion
    rid=ref['run_id']
    if ref['kind']=='advanced':
        b=a.advanced.load(rid);advanced_ui.display(b)
        st.download_button('下载研究报告（HTML）',report,file_name='advanced-'+rid+'.html',mime='text/html',key='adv_report_'+rid)
        return
    if ref['kind']=='exploration':
        b=a.ex.load(rid);st.caption('运行 '+rid+' · 配置V'+str(b['design_version'])+' · 数据指纹 '+b['data_fingerprint'][:12])
        for line in b['conclusions']:st.write(line)
        if b['regression']:
            table=display(b['regression']['coefficients'])
            formats={c:st.column_config.NumberColumn(format='scientific' if c=='P值' else '%.4g') for c in table.select_dtypes(include='number').columns}
            st.dataframe(table,column_config=formats,hide_index=True,width='stretch');st.info(b['regression']['note'])
            if b['regression'].get('overdispersion_flag'):st.warning('Pearson离散度偏高；应检查计数均值设定、暴露与负二项等替代，当前不自动换模型。')
        labels,units=chart_context(a,sid,rid);focus=(conclusion.get('focus') or {}).get('field');charts=figures(b,focus=focus,labels=labels,units=units);primary=primary_chart_key(b,focus,charts)
        for name,f in list(charts.items())[:5]:
            if name!=primary:st.plotly_chart(f,key='assist_'+rid+'_'+name,width='stretch')
        with st.expander('完整数据质量与数值统计'):
            st.dataframe(display(b['summary']['columns']),hide_index=True,width='stretch');st.dataframe(display(b['summary']['numeric']),hide_index=True,width='stretch')
        x,y=st.columns(2);x.download_button('下载分析报告（HTML）',report,file_name='CausalOps-'+rid+'.html',mime='text/html',key='ah_'+rid);y.download_button('下载运行证据（JSON）',json.dumps(b,ensure_ascii=False,indent=2),file_name=rid+'.json',key='aj_'+rid)
    else:
        b,run=a.ws.bundle(rid);st.caption('研究运行 '+rid+' · 草案 '+run.revision_id);show_conclusion(b)
        st.download_button('下载研究图文报告',report,file_name='research-'+rid+'.html',mime='text/html',key='rh_'+rid)

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
    a=AssistantWorkspace()
    from causalops import __version__
    from causalops.ui.visual_layout import steps
    sessions=a.sessions();byid={s['id']:s for s in sessions};sid=st.query_params.get('assistant')
    with a.ws.connection() as c:
        exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='automation_v2_tasks'").fetchone()
        automatic=c.execute("SELECT id FROM automation_v2_tasks WHERE session_id=?",(sid,)).fetchone() if exists and sid else None
    if automatic:
        st.info("当前任务属于固定五步自动化研究，请在对应工作台查看整体计划、步骤和报告。")
        if st.button("打开此自动化任务"):
            st.query_params.update(route="automation",automation=automatic[0])
            st.rerun()
        return
    if sid not in byid:
        st.title('创建研究任务',anchor=False)
        st.caption('登记数据与研究口径。此阶段不执行统计估计。')
        steps(['导入与数据检查','确认指标与研究对象','提出研究问题'],0)
        left,right=st.columns([.96,1],gap='medium')
        with left.container(key='panel_upload'):
            st.subheader('导入分析表')
            upload=st.file_uploader('CSV / Parquet（不超过50MB、10万行、200列）',type=['csv','parquet','pq'],key='assistant_file',label_visibility='collapsed')
            with st.expander('文件编码与分隔符设置'):
                enc=st.selectbox('编码',['utf-8-sig','gb18030'],key='assistant_enc');sep=st.selectbox('分隔符',['auto',',',';','\t'],format_func=lambda v:{'auto':'自动识别（不明确时提示确认）',',':'逗号',';':'分号','\t':'制表符'}[v],key='assistant_sep')
        with left.container(key='panel_intake'):
            st.subheader('研究任务设置')
            title=st.text_input('任务名称（可选）',key='assistant_title',placeholder='例如：客户访问与转化研究')
            known=a.ws.uploads();uid=st.selectbox('或选择已导入的本地表',[None]+[x['upload_id'] for x in known],format_func=lambda x:'不使用已有表' if x is None else next(v['name']+' · '+x[-6:] for v in known if v['upload_id']==x),key='assistant_known')
            question=st.text_area('初步研究问题（可选）',value=st.session_state.get('_intake_question',''),key='intake_draft_question',placeholder='可先导入数据，再确定研究问题。')
        with right.container(key='panel_field_preview'):
            st.subheader('数据概况与字段目录')
            preview=None
            rejected=False
            try:
                if upload:
                    from causalops.general.service import read_table
                    preview=read_table(upload.getvalue(),upload.name,encoding=enc,separator=sep)
                elif uid:
                    preview=a.ws.load_upload(uid)
            except (ValueError,RuntimeError,OSError) as exc:
                rejected=True
                reason=str(exc)
                st.error(reason)
                if '列名' in reason:
                    advice='请检查首行，给空列命名并区分重名字段。'
                elif any(term in reason for term in ('编码','分隔','列数')):
                    advice='请检查文件编码、分隔符和每行的列数。'
                else:
                    advice='请按上方错误说明修正文件。'
                st.info(advice+'可在导入框中直接替换文件；通过校验后即可创建任务。')
            if preview is None and not rejected:
                st.info('选择文件后显示真实行数、字段类型与缺失情况。')
            elif preview is not None:
                k=st.columns(3)
                k[0].metric('数据行数',f'{len(preview):,}');k[1].metric('字段数',len(preview.columns));k[2].metric('缺失单元格',int(preview.isna().sum().sum()))
                st.dataframe(pd.DataFrame({'字段':list(preview),'类型':preview.dtypes.astype(str).tolist(),'缺失数':preview.isna().sum().tolist()}),hide_index=True,width='stretch')
            st.caption('字段目录仅说明数据结构，分析单位与变量含义须按实际口径确认。')
        with right:
            if st.button('创建任务并检查数据',type='primary',disabled=preview is None):
                try:
                    with st.status('正在登记数据并检查质量',expanded=True) as status:
                        from importlib.util import find_spec
                        graph_ready=find_spec('langgraph') is not None and find_spec('langchain_core') is not None
                        if graph_ready:
                            from causalops.application.research_service import ResearchService
                            sid=ResearchService(a).create_task(payload=upload.getvalue() if upload else None,name=upload.name if upload else None,upload_id=None if upload else uid,title=title or (upload.name if upload else '本地分析任务'),encoding=enc,separator=sep)
                            st.write('数据已登记，原始文件不作修改。分析计划将在审核后执行。')
                            status.update(label='字段与数据结构检查已完成',state='complete')
                        else:
                            if upload:uid=a.ws.ingest(upload.getvalue(),upload.name,encoding=enc,separator=sep)
                            sid=a.create(uid,title or (upload.name if upload else '本地分析任务'));st.write('数据已登记，原始文件不作修改。')
                            status.update(label='数据已登记，等待制定分析计划',state='complete')
                    st.session_state['_open_overview']=True;st.query_params['assistant']=sid;st.query_params.pop('flow',None);st.rerun()
                except (ValueError,RuntimeError,OSError) as exc:
                    st.error(str(exc));st.info('本次导入检查未完成，未执行回归或因果分析。原始文件与已有任务保留。编码问题请展开文件设置；格式或容量超限请准备新的分析表后再创建任务。')
                    st.button('返回首页与模型连接',key='import_recovery_home',on_click=lambda: (st.session_state.update(showcase_route='home'),st.query_params.update(route='home')))
            st.caption('此按钮只登记文件并核对结构，不执行回归或因果分析，不向模型发送数据。')
        return
    from causalops.ui.reading import landmark
    landmark('overview', move=st.session_state.pop('_open_overview', False))
    s=a.session(sid);frame=a.ws.load_upload(s['upload_id']);pr=profile(frame)
    st.title(s['title'],anchor=False)
    st.caption('当前任务编号：'+sid+'。研究问题、方案版本与运行记录保存在此任务中。')
    if not a.plans(sid):
        st.info('数据已登记。可先查看数据质量，或在下方输入研究问题。')
    with st.sidebar.expander('当前任务 · 数据与权限'):
        with st.expander('数据概况与字段目录'):
            top=st.columns(3)
            top[0].metric('数据行数',f'{pr["rows"]:,}');top[1].metric('字段数',pr['columns'])
            dataset_name=next((item['name'] for item in a.ws.uploads() if item['upload_id']==s['upload_id']),None)
            if dataset_name:top[2].text(dataset_name)
            st.dataframe(pd.DataFrame(pr['fields']).rename(columns={'field':'字段','dtype':'类型','missing_n':'缺失数','distinct_n':'非缺失唯一值数','numeric':'是否数值','likely_identifier':'疑似标识/敏感字段','infinite_n':'无穷值数'}),hide_index=True,width='stretch')
            st.caption(pr['meaning'])
        from causalops.ui.model_setup import task_model
        model=task_model(a,sid)
    from importlib.util import find_spec
    if find_spec('langgraph') is not None and find_spec('langchain_core') is not None:
        use_graph=True
        if use_graph:
            from causalops.ui.graph_app import render_graph_workspace
            render_graph_workspace(a,sid,frame,model)
            return
    plans=a.plans(sid)
    if plans:
        latest=plans[0];state={'candidate':'待审核','accepted':'待执行','completed':'已完成','rejected':'已放弃'}[latest['state']]
        st.caption('当前计划：V'+str(latest['version'])+' · '+state+'。研究事实与识别条件须经人工审核。')
    completed=a.completed_runs(sid);byrun={r['run_id']:r for r in completed};qa_compare=None
    if byrun:
        selector='assistant_result_runid_'+sid
        selected=a.selected_run(sid)
        if st.session_state.get(selector) not in byrun:st.session_state[selector]=selected
        focus=st.session_state.pop('assistant_focus_run_'+sid,None)
        if focus in byrun:st.session_state[selector]=focus
        rid=st.selectbox('当前讨论与展示的运行',list(byrun),format_func=lambda r:LABELS.get(byrun[r].get('method'),METHODS.get(byrun[r].get('method'),byrun[r]['kind']))+' · 计划V'+str(byrun[r]['plan_version'])+' · '+r[:8],key=selector)
        if rid!=selected:a.select_run(sid,rid)
        st.caption('结果展示、解释和报告均以此运行为准。切换后不会重新估计；历史回答仍保留原证据范围。')
        if st.checkbox('本轮明确比较多条运行',key='assistant_compare_'+sid):
            qa_compare=st.multiselect('选择比较的运行（最多三条，同一数据任务）',list(byrun),default=[rid],max_selections=3,format_func=lambda r:byrun[r].get('method',byrun[r]['kind'])+' · '+r[:8],key='assistant_compare_runs_'+sid)
    tab_task,tab_result,tab_methods,tab_advanced,tab_trial=st.tabs(['研究计划与讨论','结果与报告','方法与文献','进阶研究设计','使用评测'])
    with tab_task:
        events=a.events(sid)
        for event in events:
            if event['kind']=='user':
                with st.chat_message('user'):st.write(event['body']['question'])
            if event['kind']=='answer':
                with st.chat_message('assistant'):
                    body=event['body'];st.caption(body['source']);st.write(safe_text(body['text']))
                    if body.get('run_ids'):st.caption('本轮依据的运行：'+'、'.join(r[:8] for r in body['run_ids']))
                    if body.get('display_note'):st.caption(body['display_note'])
                    if body['facts']:
                        with st.expander('核对本轮引用的运行事实'):
                            st.dataframe([{'引用':f.get('citation_label','本地事实'),'指标':f['text'],'精确值':str(f['value']),'完整证据标识':f['id'],'运行编号':f['run_id']} for f in body['facts']],hide_index=True,width='stretch')
                    for cid in body.get('citations',[]):
                        card=next((c for c in a.library.cards if c['card_id']==cid),None)
                        if card:
                            st.caption('方法依据：'+card['title']+' · '+('实证案例（摘要）' if card['scope']=='empirical_example' else '方法规则'))
                            for source_id in card['source_ids']:
                                source=a.library.catalog['sources'][source_id];show_source(source)
            if event['kind']=='proposal':
                with st.chat_message('assistant'):st.write('待审计划 V'+str(event['body']['version'])+'，来源：'+event['body']['source']+'。请审阅下方计划及变量设定。')
        if plans:
            p=plans[0];v=p['plan'];st.subheader('当前计划 V'+str(p['version'])+' · '+{'candidate':'待审核','accepted':'已接受，待执行','completed':'已完成','rejected':'已放弃'}[p['state']])
            st.write(safe_text(v['objective']))
            if p['state']=='completed':st.caption('下列内容为计划生成时登记的设计与待确认事项。执行时的审核依据和诊断结果保存在对应运行报告中。')
            for note in v['dataset_notes']:
                if not re.search(r'schema|steps\.\d|tool_placeholder|额外字段|额外键',note,re.I):st.caption(safe_text(note))
            for i,step in enumerate(v['steps']):
                cfg=step['config'];label=LABELS.get(cfg.get('method'),METHODS.get(cfg.get('method'),cfg.get('method','研究')))
                with st.container(border=True):
                    st.markdown('**'+str(i+1)+'. '+label+'**');st.write(safe_text(step['reason']))
                    st.caption('结果字段：'+str(cfg.get('outcome') or '分布/汇总')+'；分析字段：'+', '.join(cfg.get('numeric',[])+cfg.get('predictors',[])+cfg.get('covariates',[])))
                    if step['tool']=='advanced':st.caption('处理：'+str(cfg.get('treatment') or '按首次处理期/阈值定义')+'；工具：'+', '.join(cfg.get('instruments',[]))+'；运行变量：'+str(cfg.get('running') or '不适用')+'；期序：'+str(cfg.get('time') or '不适用')+'；首次处理期：'+str(cfg.get('cohort') or '不适用'))
            if v['required_questions']:
                with st.expander('计划生成时的待确认事项' if p['state']=='completed' else '执行前待确认事项',expanded=p['state']!='completed'):
                    for q in v['required_questions']:st.write('• '+q)
            with st.expander('计划版本与变更记录'):
                if len(plans)>1:
                    old=plans[1]['plan'];st.json({'previous_version':plans[1]['version'],'changed_fields':[k for k in v if old.get(k)!=v[k]]})
                st.json(v)
            if p['state']=='candidate':
                with st.expander('修改变量设定（保存为新版本）'):
                    edited=copy.deepcopy(v)
                    for i,step in enumerate(edited['steps']):
                        cfg=step['config'];st.markdown('**步骤 '+str(i+1)+'**');key=lambda k:'edit_'+p['id']+'_'+str(i)+'_'+k
                        options=list(frame.columns)
                        numeric=[c for c in options if pd.api.types.is_numeric_dtype(frame[c])]
                        if step['tool']=='exploration':
                            cfg['numeric']=st.multiselect('统计数值字段',numeric,default=[c for c in cfg.get('numeric',[]) if c in numeric],key=key('numeric'))
                            cfg['categorical']=st.multiselect('统计分类字段',options,default=cfg.get('categorical',[]),key=key('cat'))
                            if cfg.get('method') in ('ols','logit','poisson'):
                                current=cfg.get('outcome');cfg['outcome']=st.selectbox('结果字段',numeric,index=numeric.index(current) if current in numeric else None,placeholder='请选择结果字段',key=key('outcome')) if numeric else None
                                cfg['predictors']=st.multiselect('自变量（不要选ID/未来结果）',[c for c in options if c!=cfg.get('outcome')],default=[c for c in cfg.get('predictors',[]) if c!=cfg.get('outcome')],key=key('predictors'))
                        elif step['tool']=='advanced':
                            st.caption('扩展方法映射请使用“进阶研究设计”选项卡生成新候选，避免静默改动研究口径。')
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
                    if st.button('保存修订计划',key='refine_'+p['id']):
                        try:a.refine(sid,edited);st.rerun()
                        except (ValueError,RuntimeError) as exc:st.error(str(exc))
            if p['state']=='candidate':
                x,y=st.columns(2)
                safe=all(t['tool']=='exploration' and t['config'].get('method') in ('descriptive','correlation') for t in v['steps'])
                if x.button('接受并执行探索分析' if safe else '接受分析计划',type='primary',key='accept_'+p['id']):
                    a.accept(p['id'],p['sha'])
                    if safe:
                        with st.status('正在执行已授权的探索分析',expanded=True) as status:
                            tasks=a.execute(p['id'],permit=True,progress=lambda i,step,state:st.write('步骤 '+str(i+1)+' · '+step['config']['method']+' · '+{'running':'正在运行','completed':'完成','blocked':'待补充'}[state]));status.update(label='已完成' if all(t['state']=='completed' for t in tasks) else '需要补充信息',state='complete' if all(t['state']=='completed' for t in tasks) else 'error')
                    st.rerun()
                if y.button('放弃分析计划',key='reject_'+p['id']):a.reject(p['id']);st.rerun()
            if p['state']=='accepted':
                facts={}
                with st.expander('执行前研究设计审核',expanded=any(t['tool'] in ('research','advanced') or t['config'].get('method') in ('ols','logit','poisson') for t in v['steps'])):
                    for i,step in enumerate(v['steps']):
                        st.markdown('**步骤 '+str(i+1)+'**');facts[str(i)]=confirmations(step,i,p['id'],frame)
                if st.button('执行分析计划',type='primary',key='execute_'+p['id']):
                    with st.status('统计分析执行中',expanded=True) as status:
                        def progress(i,step,state):st.write('步骤 '+str(i+1)+' · '+step['config'].get('method','研究')+' · '+{'running':'正在运行','completed':'完成','blocked':'需要补充'}[state])
                        tasks=a.execute(p['id'],permit=True,confirmations=facts,progress=progress);finished=[t['result']['run_id'] for t in tasks if t['state']=='completed'];st.session_state['assistant_focus_run_'+sid]=finished[-1] if finished else None;done=all(t['state']=='completed' for t in tasks);status.update(label='分析已完成' if done else '执行已暂停，请检查原因',state='complete' if done else 'error')
                    st.rerun()
            task_rows=a.tasks(p['id'])
            if task_rows:st.dataframe([{'步骤':t['ordinal']+1,'状态':{'pending':'等待执行','running':'执行中','completed':'已完成','blocked':'待补充','interrupted':'执行已中断','cancelled':'已取消'}[t['state']],'计算用时（秒）':(t['result'] or {}).get('seconds')} for t in task_rows],hide_index=True,width='stretch')
            for t in task_rows:
                if t['state']=='blocked':st.warning('步骤'+str(t['ordinal']+1)+'：'+t['result']['error'])
            if any(t['state']=='running' for t in task_rows):
                st.warning('有步骤仍标记为运行中。检查恢复只会在确认原进程退出后处理，不并行重算。')
                x,y=st.columns(2)
                if x.button('检查中断并恢复记录',key='recover_'+p['id']):a.recover(p['id']);st.rerun()
                if y.button('请求停止后续步骤',key='cancel_'+p['id']):a.cancel(p['id']);st.rerun()
                st.caption('当前统计函数采用协作式取消：正在计算的结果会先保存，再停止后续步骤。')
            if any(t['state']=='cancelled' for t in task_rows):
                if st.button('恢复已取消的未完成步骤',key='resume_'+p['id']):a.resume(p['id'],permit=True);st.rerun()
            if task_rows:
                with st.expander('执行尝试与恢复检查点'):
                    for task in task_rows:
                        st.write('步骤 '+str(task['ordinal']+1));st.json(a.runtime.attempts(task['id']))
            if p['state']=='completed':st.success('分析已完成。结果、诊断和报告已保存，可继续讨论或创建修订计划。')
        action=st.radio('提问类型',['自动识别','制定或修订分析计划','解读分析结果','方法咨询'],horizontal=True,key='assistant_action')
        q=st.chat_input('输入研究问题、计划修改要求或结果解释问题',key='assistant_chat')
        if q:
            try:
                intent='plan' if action=='制定或修订分析计划' or (action=='自动识别' and __import__('re').search('帮我分析|分析一下|做一个|加上|改用|重新分析|生成.*计划|建模|做.*回归|比较.*关系',q)) else 'answer'
                with st.spinner('正在检索方法并'+('生成候选计划' if intent=='plan' else '核对运行证据')):
                    if intent=='plan':a.propose(sid,q,model)
                    else:
                        if qa_compare is not None:
                            if len(qa_compare)<2:raise ValueError('跨运行比较请明确选择至少两条运行。')
                            answer=a.ask(sid,q,model,compare_run_ids=qa_compare)
                        else:answer=a.ask(sid,q,model,run_id=a.selected_run(sid))
                        # Answering cannot silently change the user's selected run.
                st.rerun()
            except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc));st.info('未展示未经校验的模型结果；已有运行和原始数据保持不变。')
    with tab_result:
        if not byrun:st.info('当前任务尚无已完成的分析。请先审核并执行分析计划。')
        else:
            rid=a.selected_run(sid);show_run(a,byrun[rid],sid)
            with st.expander('独立运行证据审阅（A2A，本地服务）'):
                st.caption('只提交运行编号。独立服务检查已明确导出的事实归属、数值范围和区间顺序；不重新估计，也不验证识别假设。')
                if st.button('导出并审阅当前运行证据',key='assistant_a2a_evidence_'+sid):
                    try:
                        import asyncio
                        from causalops.protocols.local_services import ensure_reviewer
                        from causalops.protocols.reviewer_server import request_review
                        a.export_readonly(sid);ensure_reviewer(a.ws.root)
                        reply=asyncio.run(request_review({'action':'review_evidence','run_id':rid}))
                        a.event(sid,'a2a_evidence_review',{'run_id':rid,'transport':'A2A1.0_JSONRPC_loopback','events':reply,'execution_performed':False})
                        st.success('运行证据审阅已完成。');st.json(reply)
                    except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
            st.subheader('结果复核与后续研究')
            st.caption('读取当前运行诊断并检索方法依据。缺少事实时列出问题；修订始终保存为待审候选，不自动批准或执行。')
            observe_q=st.text_area('需要复核的问题',value='根据本次运行诊断，说明还缺少哪些依据，以及下一步适合做什么。',key='assistant_observe_q_'+sid)
            allow_candidate=st.checkbox('允许提出新的待审计划（仍需人工接受）',key='assistant_observe_candidate_'+sid)
            if st.button('复核本次运行并提出下一步',key='assistant_observe_'+sid):
                try:
                    from causalops.assistant.observation import EvidenceLoop
                    with st.spinner('正在核对运行诊断和方法条件'):
                        EvidenceLoop(a).run(sid,observe_q,run_id=rid,model=model,allow_candidate=allow_candidate)
                    st.rerun()
                except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
            observations=[e['body'] for e in a.events(sid) if e['kind']=='observation_loop' and e['body']['run_id']==rid]
            if observations:
                last=observations[-1];st.caption('复核已保存；停止原因：'+{'human_fact_required':'需要人工补充事实','finished':'证据复核结束','candidate_requires_human_review':'候选计划待审核','candidate_permission_required':'尚未授权提出候选','step_budget':'达到观察步数上限','model_call_budget':'达到模型调用上限','repeated_action':'重复动作已停止','time_budget':'达到时间预算','validation_failed':'建议未通过本地校验，未执行','provider_error':'模型服务未完成请求','proposal_validation_failed':'修订未通过校验，未创建候选'}.get(last['stop_reason'],last['stop_reason']))
                for row in last['trace']:
                    st.write(safe_text(row['reason']))
                    for question in row.get('questions',[]):st.write('• '+safe_text(question))
                    if row.get('retrieval'):show_sources(row['retrieval'])
                with st.expander('复核记录与预算'):st.json(last)
    with tab_methods:
        query=st.text_input('检索方法、条件、诊断或商业/学术案例',value='如何选择方法并检查识别条件',key='assistant_search')
        if query:show_sources(a.library.search(query))
        if st.button('导出授权证据供 MCP 查询',key='assist_mcp_export'):
            count=a.export_readonly(sid);st.success('已导出'+str(count)+'个已保存运行；不含原始行或ID值。')
        st.caption('检索范围为本地方法知识库，不包含导入数据与会话。文献条目标注核对范围、页码与版本；其结论不能直接替代当前研究的识别依据。')
    with tab_advanced:
        advanced_ui.builder(a,sid,frame)
        with st.expander('独立方法审阅（A2A，本地服务）'):
            st.caption('向独立服务提交方法问题，返回适用条件、检查要求和文献依据。该服务使用已整理的规则与知识卡，不接收数据行，也无计划审批或分析执行权限。')
            peer_method=st.selectbox('审阅的方法',list(advanced_ui.LABELS),format_func=lambda v:advanced_ui.LABELS[v],key='a2a_method_'+sid)
            peer_question=st.text_input('发给审阅者的问题',value='应当检查哪些识别条件和失败情形？',key='a2a_question_'+sid)
            if st.button('提交方法审阅',key='a2a_request_'+sid):
                try:
                    import asyncio
                    from causalops.protocols.reviewer_server import request_review
                    from causalops.protocols.local_services import ensure_reviewer
                    ensure_reviewer(a.ws.root)
                    reply=asyncio.run(request_review({'action':'review_method','method':peer_method,'question':peer_question}))
                    a.event(sid,'a2a_review',{'transport':'A2A1.0_JSONRPC_loopback','events':reply,'execution_performed':False})
                    st.success('方法审阅已完成，当前分析计划未作修改。');st.json(reply)
                except Exception as exc:st.error('本机审阅服务未完成：'+type(exc).__name__+'。请按扩展手册启动8512端口服务。')
    with tab_trial:
        from causalops.ui.user_trial import render_user_trial
        render_user_trial(a.ws)
