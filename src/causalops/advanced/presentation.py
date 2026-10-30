"""Human-readable advanced research forms and reports; no hidden estimator selection."""
from html import escape
import json
import pandas as pd
import plotly.graph_objects as go
from causalops.advanced.service import LABELS,AdvancedDesign

def report(b):
    body='<h1>'+escape(LABELS[b['method']])+' · 运行报告</h1><p>'+escape(b['conclusion'])+'</p>'
    body+='<p>估计标准误 '+str(b['std_error'])+'；P值 '+format(b['p_value'],'.4g')+'；纳入 '+str(b['analysis_rows'])+' 行。P值数值为0时表示计算舍入，非真实概率严格为零。</p>'
    body+='<h2>结论边界与行动</h2><p>单位为原始结果单位；无可解释业务基线或成本时，不生成相对收益、ROI或总体提升。请优先审阅下述风险，再做预定稳健性分析或补充数据。</p><ul>'+''.join('<li>'+escape(w)+'</li>' for w in b['warnings'])+'</ul>'
    for key,label in [('first_stage','第一阶段相关性诊断'),('diagnostics','诊断'),('group_time','批次×时间ATT'),('event_study','事件期ATT与逐点区间')]:
        if key in b:body+='<h2>'+label+'</h2>'+pd.DataFrame(b[key]).to_html(index=False,escape=True)
    fig=go.Figure(go.Scatter(x=[b['estimate']],y=['估计差异'],mode='markers',error_x=dict(type='data',array=[b['ci95'][1]-b['estimate']],arrayminus=[b['estimate']-b['ci95'][0]])));fig.add_vline(x=0,line_dash='dash');fig.update_layout(xaxis_title='原始结果单位；95%区间')
    body+='<h2>估计与不确定性</h2>'+fig.to_html(full_html=False,include_plotlyjs=True)
    if 'event_study' in b:
        e=pd.DataFrame(b['event_study']);f=go.Figure(go.Scatter(x=e['relative_period'],y=e['ATT'],mode='lines+markers',error_y=dict(type='data',array=e['upper']-e['ATT'],arrayminus=e['ATT']-e['lower'])));f.add_hline(y=0,line_dash='dash');f.update_layout(xaxis_title='事件期',yaxis_title='ATT及逐点95%区间');body+=f.to_html(full_html=False,include_plotlyjs=False)
    body+='<h2>复现与人工依据</h2><pre>'+escape(json.dumps(b,ensure_ascii=False,indent=2))+'</pre>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>body{font:16px/1.8 Microsoft YaHei,Arial;max-width:1100px;margin:40px auto;padding:20px;color:#243639}table{border-collapse:collapse;width:100%}td,th{padding:8px;border:1px solid #ccd}pre{white-space:pre-wrap;overflow-wrap:anywhere}h2{margin-top:30px}</style>'+body+'</html>'

def display(b):
    import streamlit as st
    st.subheader(LABELS[b['method']]);st.write(b['conclusion'])
    cols=st.columns(3);cols[0].metric('估计差异',format(b['estimate'],'.4g'));cols[1].metric('标准误',format(b['std_error'],'.4g'));cols[2].metric('P值',format(b['p_value'],'.4g') if b['p_value'] else '数值舍入为0')
    st.caption('实现 '+b['implementation']+' · 包版本 '+b['package_version']+' · 运行 '+b['run_id'])
    for w in b['warnings']:st.warning(w)
    if 'first_stage' in b:
        table=pd.DataFrame(b['first_stage']).rename(columns={'term':'内生变量','rsquared':'第一阶段R²','partial.rsquared':'部分R²','shea.rsquared':'Shea部分R²','f.stat':'第一阶段Wald统计量','f.pval':'工具相关性P值','f.dist':'参考分布'})
        for c in table.select_dtypes(include='number'):table[c]=table[c].map(lambda v:format(v,'.4g'))
        st.dataframe(table,hide_index=True,width='stretch')
    fig=go.Figure(go.Scatter(x=[b['estimate']],y=['估计差异'],mode='markers',error_x=dict(type='data',array=[b['ci95'][1]-b['estimate']],arrayminus=[b['estimate']-b['ci95'][0]])));fig.add_vline(x=0,line_dash='dash');fig.update_layout(height=240,xaxis_title='结果原单位与95%区间');st.plotly_chart(fig,width='stretch')
    if 'event_study' in b:
        e=pd.DataFrame(b['event_study']);fig=go.Figure(go.Scatter(x=e['relative_period'],y=e['ATT'],mode='lines+markers',error_y=dict(type='data',array=e['upper']-e['ATT'],arrayminus=e['ATT']-e['lower'])));fig.add_hline(y=0,line_dash='dash');fig.update_layout(xaxis_title='距首次处理的期数',yaxis_title='ATT（原单位；逐点95%区间）');st.plotly_chart(fig,width='stretch')
    if 'plot' in b:
        p=pd.DataFrame(b['plot']);fig=go.Figure(go.Scatter(x=p.x,y=p.y,mode='markers',marker_size=8));fig.add_vline(x=b['design']['cutoff'],line_dash='dash');fig.update_layout(xaxis_title='运行变量分箱均值',yaxis_title='结果分箱均值（描述性图；不是估计曲线）');st.plotly_chart(fig,width='stretch')
    with st.expander('完整诊断与复现证据'):st.json(b)

def confirmations(cfg,key):
    import streamlit as st
    f={};m=cfg['method'];f['design_evidence']=st.text_area('具体设计依据（至少12字；记录制度、时序、样本与局限，不由模型确认）',key=key('evidence'))
    fields={'iv_2sls':{'instrument_exogeneity_reviewed':'有工具外生性的设计依据','exclusion_reviewed':'有排除限制的实质论证','monotonicity_reviewed':'二元处理的局部解释有单调性论证'},'rd_sharp':{'continuity_reviewed':'阈值处潜在结果与其他因素连续的依据','no_manipulation_reviewed':'已评估阈值排序/操纵风险（不等于密度检验通过）','threshold_rule_reviewed':'阈值及清晰处理规则事先存在，非按结果挑选'},'staggered_did':{'parallel_reviewed':'有批次条件平行趋势的设计论证','no_anticipation_reviewed':'有无预期效应依据，当前anticipation固定为0'}}[m]
    if m=='iv_2sls':st.caption('第一阶段显著性不能证明强工具；当前无弱工具稳健AR/CLR区间。')
    fields={**fields,'independent_units_reviewed':'已核对独立分析单位或独立簇','no_interference_reviewed':'已实质评估无跨单位干扰假设'}
    if cfg.get('covariates'):fields['covariates_pre_reviewed']='控制变量在处理前确定，未含处理后结果'
    for k,label in fields.items():f[k]=st.checkbox(label,key=key(k))
    f['allow_complete_case']=st.checkbox('允许必要字段缺失时完整案例排除并记录数量（面板缺失仍暂停）',key=key('missing'))
    return f

def builder(a,sid,frame):
    import streamlit as st
    st.subheader('扩展研究设计：IV / RDD / 交错DID')
    st.write('先映射已有字段，生成待审计划。这里不替你确认识别条件；随后回到“任务与对话”接受并核对。')
    method=st.selectbox('研究方法',list(LABELS),format_func=lambda x:LABELS[x],key='advanced_method_'+sid)
    options=list(frame.columns);numeric=[c for c in options if pd.api.types.is_numeric_dtype(frame[c])]
    key=lambda x:'advanced_builder_'+sid+'_'+method+'_'+x
    def choice(label,k,opts=options,optional=False):
        values=([None] if optional else [])+opts
        return st.selectbox(label,values,format_func=lambda v:'未选择' if v is None else str(v),key=key(k)) if values else None
    with st.form(key('mapping_form')):
        q=st.text_area('研究目标与变量含义',key=key('question'),placeholder='说明要评估什么、单位、时序及现有制度依据')
        cfg={'method':method,'question':q,'outcome':choice('数值结果字段','outcome',numeric),'unit':st.text_input('结果单位',value='结果指标原单位',key=key('unit'))}
        cfg['entity']=choice('分析实体ID（可选；DID必选）','entity',optional=True)
        if method=='iv_2sls':
            cfg['treatment']=choice('内生处理（一个）','treatment',numeric);cfg['instruments']=st.multiselect('排除工具变量（不能选择处理或结果）',numeric,key=key('instruments'),placeholder='请选择工具变量');cfg['cluster']=choice('聚类字段（可选）','cluster',optional=True)
        elif method=='rd_sharp':
            cfg['running']=choice('运行变量','running',numeric);cfg['cutoff']=st.number_input('事先存在的阈值',value=0.,key=key('cutoff'));cfg['treatment']=choice('实际0/1处理（若有，程序检查与阈值一致）','treatment',numeric,True);cfg['cluster']=choice('聚类字段（可选）','cluster',optional=True)
        else:
            cfg['time']=choice('连续整数期序（如1至10，不是日期字符串）','time',numeric);cfg['cohort']=choice('首次处理期（从未处理为空值）','cohort',numeric);cfg['control_group']=st.selectbox('对照规则',['never_treated','not_yet_treated'],format_func=lambda v:'从未处理' if v=='never_treated' else '尚未处理（含从未处理）',key=key('control'))
            st.caption('当前要求平衡面板、至少两个批次、每批和从未处理组至少20实体；上层聚类和时变控制尚未开放。')
        cfg['covariates']=st.multiselect('处理前数值控制变量（可留空）',numeric,key=key('covariates'),placeholder='可留空；勿选标识、处理或结果')
        if st.form_submit_button('生成扩展方法候选计划'):
            try:
                d=AdvancedDesign.model_validate(cfg);hit=a.library.search(method,method=method);ids=[h['card_id'] for h in hit['hits']]
                p={'objective':q,'dataset_notes':['扩展设计由使用者本地映射；尚未确认识别条件。'],'steps':[{'tool':'advanced','config':cfg,'reason':'采用明确的官方方法实现，执行前登记设计依据并检查数据支持。'}],'required_questions':['请核对结果、分析单位、真实制度与识别依据；方法不会自动证明假设。'],'citations':ids}
                a.store_plan(sid,p,'使用者本地映射',q,hit);st.success('候选已保存；请切换到“任务与对话”查看并接受。');st.rerun()
            except (ValueError,RuntimeError) as exc:st.error(str(exc))
