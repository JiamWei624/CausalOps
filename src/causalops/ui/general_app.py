"""Guided local workflow for arbitrary supported user tables."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from pydantic import ValidationError
from causalops.general.service import GeneralWorkspace,GeneralDesign,DesignError,METHODS,prepare
from causalops.results.interpretation import MetricDefinition
from causalops.results.qa import ResultQAService
from causalops.identification import route_identification
from causalops.metadata.presentation_zh import status_label_zh,diagnostic_rows_zh,diagnostics_for_display
from causalops.reporting import render_html_report,render_markdown_report
from causalops.ui.showcase_widgets import show_conclusion
from causalops.visualization import build_did_diagnostic_figures,build_regression_diagnostic_figures

def render_general():
    ws=GeneralWorkspace();st.title('专业统计分析')
    st.caption('用于明确变量映射与指标口径的专业分析入口。保存设计版本后审核执行，并查阅对应运行的结果与证据。')
    st.info('本入口用于本机单用户分析：CSV/Parquet，最多50MB、100,000行、200列。数据、字段与问题不会自动发送给模型；本页问答使用本地证据。')
    studies=ws.studies();by_id={s.session_id:s for s in studies};requested=st.query_params.get('study')
    mode=st.radio('工作方式',['新建研究','恢复已保存研究'],index=1 if requested in by_id else 0,horizontal=True)
    sid=None;uid=None;current=None
    if mode=='恢复已保存研究':
        if not studies:st.info('还没有已保存研究，请先新建并保存草案。');return
        sid=st.selectbox('选择研究',list(by_id),index=list(by_id).index(requested) if requested in by_id else 0,format_func=lambda x:by_id[x].title+' · '+x[-6:])
        uid=ws.upload_for(sid);current=ws.current(sid)
        st.caption('已从本地工作区恢复，无需重新上传。')
    else:
        upload=st.file_uploader('上传CSV或Parquet分析表',type=['csv','parquet','pq'],key='general_upload')
        a,b=st.columns(2);encoding=a.selectbox('CSV编码',['utf-8-sig','gb18030'],format_func=lambda v:'UTF-8（含BOM）' if v=='utf-8-sig' else 'GB18030（中文旧编码）')
        separator=b.selectbox('CSV分隔符',[',',';','\t'],format_func=lambda v:{',':'逗号',';':'分号','\t':'制表符'}[v])
        if st.button('导入并检查',disabled=upload is None):
            try:
                st.session_state['general_active_upload']=ws.ingest(upload.getvalue(),upload.name,encoding=encoding,separator=separator)
                st.success('文件已导入本地工作区；尚未建立研究设计或执行分析。')
            except (ValueError,OSError) as exc:st.error(str(exc));return
        uid=st.session_state.get('general_active_upload')
        available=ws.uploads()
        if not uid and available:
            chosen=st.selectbox('也可选择本工作区已导入文件',[None]+[x['upload_id'] for x in available],format_func=lambda x:'请选择' if x is None else next(y['name'] for y in available if y['upload_id']==x))
            uid=chosen
        if not uid:st.info('请导入数据后继续设置变量。本入口不预设处理变量、结果变量或分组口径。');return
    try:frame=ws.load_upload(uid)
    except (ValueError,OSError) as exc:st.error(str(exc));return
    a,b,c=st.columns(3);a.metric('原表行数',f'{len(frame):,}');b.metric('字段数',len(frame.columns));c.metric('工作区','本机持久化')
    form_col,meta_col=st.columns(2,gap='medium')
    with meta_col.container(key='panel_pro_fields'):
        st.subheader('字段说明与数据检查')
        with st.expander('1. 数据检查：列类型、缺失与重复',expanded=not bool(current)):
            st.dataframe([{'字段':col,'类型':str(frame[col].dtype),'缺失数':int(frame[col].isna().sum()),'不同取值数':int(frame[col].nunique())} for col in frame],hide_index=True,width='stretch')
            st.caption('检查不能证明字段的业务含义、随机化或测量时序。原表不会被直接改写。')
            if st.checkbox('显示前5行（仅本机，可能含敏感信息）',key='preview_'+uid):st.dataframe(frame.head(),hide_index=True,width='stretch')
    with form_col.container(key='panel_pro_design'):
        saved=GeneralDesign.model_validate(current.research_notes['general_design']) if current else None
        prefix='gd_'+(current.revision_id if current else uid[:16])
        def key(s):return prefix+'_'+s
        cols=list(frame.columns)
        def pick(label,field):
            old=getattr(saved,field,None) if saved else None
            return st.selectbox(label,[None]+cols,index=cols.index(old)+1 if old in cols else 0,key=key(field),format_func=lambda v:'请选择字段' if v is None else v)
        st.subheader('2. 明确字段、方法和指标口径')
        question=st.text_area('你希望回答的研究问题（至少8个字）',value=saved.question if saved else '',key=key('question'),placeholder='例如：在当前样本中，某干预与后续结果有什么差异？')
        unit=st.text_input('每条记录代表的分析单位',value=saved.analysis_unit if saved else '',key=key('unit'),placeholder='例如：客户、教师、企业—日')
        method=st.selectbox('分析方法',list(METHODS),index=list(METHODS).index(saved.method) if saved else None,placeholder='请选择分析方法',key=key('method'),format_func=lambda v:METHODS[v])
        assignment=st.selectbox('处理如何分配', ['unknown','randomized','observational'],index=['unknown','randomized','observational'].index(saved.assignment) if saved else 0,key=key('assignment'),format_func=lambda v:{'unknown':'尚不清楚','randomized':'确有随机分配依据','observational':'观察性分组/非随机'}[v])
        st.caption('不知道分配机制时不要选择随机。观察性回归只作条件关联；PSM/IPW/DML仍需要识别依据，不会因使用机器学习自动得到因果。')
        a,b=st.columns(2)
        with a:treatment=pick('处理/分组字段','treatment')
        with b:outcome=pick('结果字段','outcome')
        values=sorted(frame[treatment].dropna().map(str).unique().tolist()) if treatment else []
        if len(values)>20:st.warning('分组值较多；首版只接受恰有两个组别的分析表，不自动按阈值二分。');values=[]
        a,b=st.columns(2)
        def group(box,label,field):
            old=getattr(saved,field,None) if saved else None
            return box.selectbox(label,[None]+values,index=values.index(old)+1 if old in values else 0,key=key(field)+'_'+str(treatment),format_func=lambda v:'请选择组别' if v is None else v)
        control=group(a,'对照/参考组取值（编码为0）','control_value');treated=group(b,'处理/比较组取值（编码为1）','treated_value')
        a,b=st.columns(2)
        with a:entity=pick('分析实体/随机化单位ID','entity')
        with b:cluster=pick('聚类单位（观察性回归默认使用实体）','cluster')
        cov_options=[c for c in cols if c not in {treatment,outcome,entity,cluster}]
        cov=st.multiselect('控制变量 / 处理前协变量',cov_options,default=[x for x in saved.covariates if x in cov_options] if saved else [],placeholder='选择已核对的处理前字段',key=key('covariates'))
        cov_review=st.checkbox('已核对控制变量角色与测量时点，没有把结果或未来信息当作控制',value=saved.covariates_reviewed if saved else False,key=key('cov_review'))
        allow=st.checkbox('必要字段缺失时，明确采用完整案例分析，并在报告保留排除数量',value=saved.allow_complete_case if saved else False,key=key('missing'))
        a,b=st.columns(2)
        label=a.text_input('结果指标的通俗名称',value=saved.metric.label if saved else '',key=key('metric_label'))
        kinds=['binary','continuous','count'];kind=b.selectbox('结果指标类型',kinds,index=kinds.index(saved.metric.kind) if saved and saved.metric.kind in kinds else None,placeholder='请选择指标类型',key=key('kind'),format_func=lambda v:{'binary':'二元结果（0/1）','continuous':'连续数值','count':'非负整数计数'}[v])
        a,b=st.columns(2);metric_unit=a.text_input('结果数值单位',value=saved.metric.unit if saved else '',key=key('metric_unit'),placeholder='二元结果填概率；其他如美元/客户、分、次')
        window=b.text_input('观察窗口与口径',value=saved.metric.window if saved else '',key=key('window'),placeholder='例如：分配后两周、该年度九个月薪酬')
        direction=st.selectbox('业务方向',['neutral','higher_is_better','lower_is_better'],index=['neutral','higher_is_better','lower_is_better'].index(saved.metric.direction) if saved else 0,key=key('direction'),format_func=lambda v:{'neutral':'暂不定义好坏','higher_is_better':'越高越符合目标','lower_is_better':'越低越符合目标'}[v])
        ratio=st.checkbox('指标有可解释的绝对零点，可在同口径前提下讨论比例变化',value=saved.metric.ratio_scale if saved else False,key=key('ratio'))
        overlap=exchange=parallel=anticipation=panel=False;time=treatment_time=None;pre=post=7
        if method in ('psm','ipw','double_ml','aipw'):
            exchange=st.checkbox('有依据支持给定已选处理前协变量后的条件可交换性（声明，不是已验证）',value=saved.exchangeability_declared if saved else False,key=key('exchange'))
            overlap=st.checkbox('有依据认为两组有共同支撑；仍须进行诊断（声明，不是已验证）',value=saved.overlap_declared if saved else False,key=key('overlap'))
        if method=='did':
            st.info('本入口的DID适用于共同处理日期、含从未处理对照的完整日级面板。交错处理请使用“分析工作台—进阶研究设计”，并显式登记整数期序与首次处理期。')
            a,b=st.columns(2)
            with a:time=pick('日级观测日期字段','time')
            with b:treatment_time=pick('首次处理日期字段（从未处理者留空）','treatment_time')
            a,b=st.columns(2);pre=int(a.number_input('处理前天数',min_value=2,max_value=365,value=saved.pre_days if saved else 7,key=key('pre')));post=int(b.number_input('处理后天数（含处理当日）',min_value=2,max_value=365,value=saved.post_days if saved else 7,key=key('post')))
            panel=st.checkbox('已确认每个实体每天一行，且当前窗口完整',value=saved.panel_confirmed if saved else False,key=key('panel'))
            parallel=st.checkbox('已提供平行趋势的研究依据；执行后仍需经验诊断',value=saved.parallel_declared if saved else False,key=key('parallel'))
            anticipation=st.checkbox('已评估并声明无预期效应；不能判断时不应勾选',value=saved.no_anticipation_declared if saved else False,key=key('anticipation'))
        draft=None;issue=None
        if all(v is not None and str(v).strip() for v in [question,unit,method,treatment,outcome,control,treated,entity,kind,label,metric_unit,window]):
            try:draft=GeneralDesign(question=question,analysis_unit=unit,method=method,treatment=treatment,control_value=control,treated_value=treated,outcome=outcome,entity=entity,cluster=cluster,covariates=cov,assignment=assignment,time=time,treatment_time=treatment_time,pre_days=pre,post_days=post,allow_complete_case=allow,covariates_reviewed=cov_review,overlap_declared=overlap,exchangeability_declared=exchange,parallel_declared=parallel,no_anticipation_declared=anticipation,panel_confirmed=panel,metric=MetricDefinition(label=label,unit='概率' if kind=='binary' else metric_unit,kind=kind,direction=direction,ratio_scale=ratio,window=window,source='user_registered_metric_definition'))
            except ValidationError:issue='研究问题至少8个字；请核对指标与设计字段。'
        else:issue='请先选择方法和指标类型，并补齐问题、单位、处理和结果字段、两个组别、实体ID，以及指标名称、单位与窗口。'
        if st.button('保存研究草案',type='primary'):
            if issue:st.error(issue)
            else:
                try:
                    sid,current=ws.save(uid,draft,sid);st.query_params['study']=sid;st.success('草案已保存，尚未批准或执行。');st.rerun()
                except (ValueError,OSError) as exc:st.error(str(exc))
    if not current:return
    st.subheader('3. 核对已保存草案并执行')
    st.caption(f'当前草案V{current.version_number}；批准只适用于这个草案和对应的数据版本。')
    frozen=GeneralDesign.model_validate(current.research_notes['general_design'])
    changed=draft is None or draft.model_dump(mode='json')!=frozen.model_dump(mode='json')
    if changed:st.warning('上方存在未保存修改或缺少字段。先保存新草案，再核对执行。')
    decision=route_identification(current.spec)
    st.dataframe([{'项目':k,'已保存内容':v} for k,v in [('问题',frozen.question),('方法',METHODS[frozen.method]),('结果指标',frozen.metric.label+' / '+frozen.metric.unit),('窗口',frozen.metric.window),('组别编码',frozen.control_value+' → 0；'+frozen.treated_value+' → 1'),('识别门控',status_label_zh(decision.status))]],hide_index=True,width='stretch')
    quality=current.research_notes['input_quality']
    a,b,c=st.columns(3);a.metric('导入行数',f"{quality['input_rows']:,}");b.metric('纳入分析行数',f"{quality['analysis_rows']:,}");c.metric('按完整案例规则排除',quality['explicit_complete_case_exclusions'])
    with st.expander('查看保存的技术口径（字段名保留原样）'):st.json(quality)
    eligible=decision.selected_method.value==frozen.method and (decision.status.value=='pass' or frozen.method=='regression_adjustment')
    if not eligible:st.warning('所选方法的识别依据尚不完整，请补充设计；不要为了启用按钮而无依据勾选。')
    if frozen.method=='regression_adjustment':st.info('本次仅授权条件关联分析，不确认因果识别，不把关联系数写成干预效果。')
    reviewed=st.checkbox('已核对保存的字段、组别、指标口径和适用范围；理解假设声明不等于验证',key='approve_'+current.revision_id)
    if st.button('审核并执行已保存草案',disabled=changed or not reviewed or not eligible):
        try:
            with st.spinner('正在执行统计、诊断、证据记录和报告生成……'):result=ws.execute(sid,current.revision_id,reviewed=True)
            st.session_state['general_run_'+sid]=result.run_record.run_id;st.success('已保存本次运行。')
        except (ValueError,OSError) as exc:st.error(str(exc))
    runs=ws.runs(sid)
    if not runs:return
    st.subheader('4. 结果、图表与本地证据问答')
    ids=[r.run_id for r in runs];chosen=st.selectbox('选择已保存运行',ids,format_func=lambda x:'运行 '+x[:10]+' · '+next(r.created_at for r in runs if r.run_id==x))
    bundle,run=ws.bundle(chosen)
    if run.revision_id!=current.revision_id:st.warning('这是历史草案的运行，保留其原有设定；不会冒充当前草案结果。')
    show_conclusion(bundle)
    with st.expander('查看诊断和技术图表'):
        st.dataframe(diagnostic_rows_zh(diagnostics_for_display(bundle)),hide_index=True,width='stretch')
        for title,fig in {**build_did_diagnostic_figures(bundle),**build_regression_diagnostic_figures(bundle)}.items():st.plotly_chart(fig,key='general_'+chosen+'_'+title,width='stretch')
    a,b,c=st.columns(3);a.download_button('下载完整图文报告',render_html_report(bundle).encode(),file_name='analysis-'+chosen+'.html',mime='text/html');b.download_button('下载运行证据',bundle.model_dump_json(indent=2),file_name='evidence-'+chosen+'.json',mime='application/json');c.download_button('下载文字报告',render_markdown_report(bundle),file_name='report-'+chosen+'.md')
    qa=ResultQAService(ws.repo,None);_,snapshot=qa.prepare(session_id=sid,run_id=chosen)
    st.caption('本页问答为本地已记录事实摘要，不调用模型、不新增统计估计；如需改变研究问题，请回到设计流程。')
    for turn in ws.repo.list_result_qa_turns(run_id=chosen,snapshot_id=snapshot['snapshot_id']):
        with st.chat_message('user'):st.write(turn['question'])
        with st.chat_message('assistant'):
            for sec in turn['answer']['sections']:st.write(sec['text'])
    with st.form('general_qa_'+chosen,clear_on_submit=True):
        question=st.text_area('围绕本次运行提问',placeholder='例如：当前结果的幅度、区间和解释边界是什么？')
        if st.form_submit_button('查询运行证据'):
            try:qa.ask(session_id=sid,run_id=chosen,question=question);st.rerun()
            except (ValueError,OSError) as exc:st.error(str(exc))