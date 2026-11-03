"""No treatment field is required by the exploratory UI."""
from __future__ import annotations
import json
import streamlit as st
from pydantic import ValidationError
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.general.exploration import ExplorationWorkspace,ExplorationDesign,LABELS
from causalops.general.exploration_report import display,figures,render_report

def render_exploration(method):
    st.title(LABELS[method]);st.caption('导入数据并明确统计口径后保存配置。每次分析对应独立运行记录，支持报告导出与历史结果恢复。')
    st.info('无需填写处理组或因果假设。数据与问题仅在本机处理；描述、相关和关联回归不能自动解释为因果。')
    ws=GeneralWorkspace();ex=ExplorationWorkspace(ws);studies=ex.studies(method);byid={x['study_id']:x for x in studies};req=st.query_params.get('explore')
    pending=st.session_state.pop('exp_open_'+method,None)
    if pending:st.session_state['exp_mode_'+method]='恢复已保存分析'
    mode=st.radio('分析记录',['新建分析','恢复已保存分析'],index=int(req in byid),horizontal=True,key='exp_mode_'+method);saved=None;uid=None;sid=None
    if mode=='恢复已保存分析':
        if not studies:st.info('还没有此类分析配置。');return
        sid=st.selectbox('选择已保存分析',list(byid),index=list(byid).index(req) if req in byid else 0,format_func=lambda v:byid[v]['design'].question+' · V'+str(byid[v]['version'])+' · '+v[-8:],key='exp_study_'+method);saved=byid[sid];uid=saved['upload_id']
    else:
        upload=st.file_uploader('上传探索分析CSV或Parquet',type=['csv','parquet','pq'],key='exp_upload_'+method)
        a,b=st.columns(2);encoding=a.selectbox('文件编码',['utf-8-sig','gb18030'],key='exp_enc_'+method);separator=b.selectbox('字段分隔符',[',',';','\t'],format_func=lambda x:{',':'逗号',';':'分号','\t':'制表符'}[x],key='exp_sep_'+method)
        if st.button('导入探索分析表',disabled=upload is None,key='exp_import_'+method):
            try:st.session_state['exp_uid_'+method]=ws.ingest(upload.getvalue(),upload.name,encoding=encoding,separator=separator)
            except (ValueError,OSError) as e:st.error(str(e));return
        uid=st.session_state.get('exp_uid_'+method)
        if not uid:
            known=ws.uploads();uid=st.selectbox('或选择已导入的本地表',[None]+[x['upload_id'] for x in known],format_func=lambda x:'请选择' if x is None else next(y['name'] for y in known if y['upload_id']==x),key='exp_known_'+method)
        if not uid:st.info('先导入文件或选择已导入表。');return
    try:f=ws.load_upload(uid)
    except (ValueError,OSError) as e:st.error(str(e));return
    a,b=st.columns(2);a.metric('原表行数',len(f));b.metric('字段数',len(f.columns));cols=list(f)
    old=saved['design'] if saved else ExplorationDesign(question='请填写本次分析希望回答的问题',method=method)
    prefix='exp_'+method+'_'+(sid+str(saved['version']) if saved else uid[:16]);key=lambda x:prefix+'_'+x
    st.subheader('1. 选择分析字段与口径')
    question=st.text_area('本次分析问题',value=old.question if saved else '',key=key('question'))
    numeric=st.multiselect('数值字段（不自动把ID当作指标）',cols,default=old.numeric,key=key('numeric'))
    categorical=st.multiselect('分类字段（最多10个）',cols,default=old.categorical,key=key('categorical'))
    def pick(label,field):
        v=getattr(old,field);return st.selectbox(label,[None]+cols,index=cols.index(v)+1 if v in cols else 0,format_func=lambda x:'不使用' if x is None else x,key=key(field))
    group=pick('分组字段（可选，最多50类）','group');date=pick('日期字段（可选，仅用于时间汇总）','date');freq=st.selectbox('时间汇总粒度',['D','M','Q','Y'],index=['D','M','Q','Y'].index(old.frequency),format_func=lambda x:{'D':'日','M':'月','Q':'季度','Y':'年'}[x],key=key('frequency'))
    y=None;predictors=[];cov='HC3';cluster=None;lags=1;iid=False;complete=False
    if method=='correlation':st.caption('按变量对使用完整有限观测，输出Pearson/Spearman及对应样本数；不自动产生显著性筛选。')
    if method=='ols':
        y=pick('回归数值结果字段','outcome');predictors=st.multiselect('回归自变量',cols,default=old.predictors,key=key('predictors'))
        cov=st.selectbox('协方差与推断方式',['HC3','cluster','HAC'],index=['HC3','cluster','HAC'].index(old.covariance),format_func=lambda x:{'HC3':'HC3：异方差稳健（仍需行独立）','cluster':'聚类稳健：重复实体/组','HAC':'HAC：按时间排序的单序列'}[x],key=key('cov'))
        if cov=='HC3':iid=st.checkbox('已确认本次分析行独立；HC3不修复重复实体或时间依赖',value=old.independent_rows_reviewed,key=key('iid'))
        if cov=='cluster':cluster=pick('聚类字段（至少20个聚类）','cluster')
        if cov=='HAC':lags=int(st.number_input('HAC最大滞后阶数',min_value=1,max_value=30,value=old.maxlags,key=key('lags')))
        complete=st.checkbox('回归采用完整案例规则并记录排除数量',value=old.allow_complete_case,key=key('complete'))
    design=None
    try:design=ExplorationDesign(question=question,method=method,numeric=numeric,categorical=categorical,group=group,date=date,frequency=freq,outcome=y,predictors=predictors,covariance=cov,cluster=cluster,maxlags=lags,independent_rows_reviewed=iid,allow_complete_case=complete)
    except ValidationError:pass
    if st.button('保存分析配置',key=key('save'),type='primary'):
        if design is None:st.error('问题至少8个字，请补充分析配置。')
        else:
            try:sid,v=ex.save(uid,design,sid);st.query_params['explore']=sid;st.query_params['mode']=method;st.session_state['exp_open_'+method]=sid;st.rerun()
            except (ValueError,OSError) as e:st.error(str(e))
    if not saved:return
    st.subheader('2. 核对并运行已保存配置');st.caption('配置V'+str(saved['version'])+'；运行仅使用已保存字段，原表不改写。')
    changed=design is None or design!=old
    if changed:st.warning('当前表单尚有未保存修改，请先保存新配置。')
    run_clicked=st.button('运行已保存分析',disabled=changed,key=key('run'))
    if run_clicked:
        try:
            with st.spinner('计算本地统计与证据……'):ex.run(sid,saved['version'])
            st.success('运行已保存。')
        except (ValueError,OSError) as e:st.error(str(e))
    runs=ex.runs(sid)
    if not runs:return
    st.subheader('3. 分析结果、图表与结论');rid=st.selectbox('选择探索分析运行',runs,key='explore_run_'+sid);b=ex.load(rid)
    if b['design_version']!=saved['version']:st.warning('此运行属于历史配置，保留原口径。')
    st.caption('探索分析运行编号：'+rid+'；配置V'+str(b['design_version']))
    for line in b['conclusions']:st.write(line)
    charts = iter(figures(b).items())
    primary = next(charts, None)
    if primary:
        title, fig = primary
        st.plotly_chart(fig, key=rid+'_'+title, width='stretch')
    secondary = list(charts)
    if secondary:
        with st.expander('补充图表'):
            for title, fig in secondary:
                st.plotly_chart(fig, key=rid+'_'+title, width='stretch')
    summary=b['summary']
    for label,field in [('数据质量','columns'),('数值描述','numeric'),('分组描述','grouped'),('时间汇总','trend'),('探索性相关','correlations')]:
        if summary[field]:
            with st.expander(label,expanded=field in ('numeric','correlations')):st.dataframe(display(summary[field]),hide_index=True,width='stretch')
    for c in summary['categorical']:
        with st.expander('分类频数：'+c['field']):st.caption('分母为全表'+str(c['denominator'])+'行；剩余类别'+str(c['remaining_n'])+'行。');st.dataframe(display(c['top']),hide_index=True,width='stretch')
    if summary.get('date_quality'):st.caption('日期不可用行数：'+str(summary['date_quality']['unusable_rows'])+'；时间汇总不补缺期。')
    if b['regression']:st.subheader('关联回归结果');st.dataframe(display(b['regression']['coefficients']),hide_index=True,width='stretch');st.caption(b['regression']['note'])

    for warning in b['warnings']:st.caption(warning)
    a,c=st.columns(2);a.download_button('下载探索分析图文报告',render_report(b),file_name=method+'-'+rid+'.html',mime='text/html');c.download_button('下载探索分析证据JSON',json.dumps(b,ensure_ascii=False,indent=2),file_name=rid+'.json',mime='application/json')