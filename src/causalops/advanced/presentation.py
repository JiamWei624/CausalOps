"""Chinese presentation of advanced estimates, diagnostics, and research limitations."""
from html import escape
import json
import pandas as pd
import plotly.graph_objects as go
from causalops.advanced.service import LABELS,AdvancedDesign

CLAIMS={'iv_under_declared_assumptions':'基于已声明假设的IV解释','local_rd_under_declared_assumptions':'基于已声明假设的局部断点解释','local_fuzzy_rd_under_declared_assumptions':'基于已声明假设的局部处理效应','staggered_att_under_declared_assumptions':'基于已声明假设的批次平均处理效应','associational':'关联性解释','reduced_form':'受限的准实验解释'}
TABLES=[('first_stage','工具变量第一阶段诊断'),('bandwidth_sensitivity','预定带宽敏感性分析'),('group_time','批次与时期的平均处理效应'),('event_study','事件期效应与逐点置信区间')]
COLUMN_LABELS={'term':'内生变量','rsquared':'第一阶段R²','partial.rsquared':'部分R²','shea.rsquared':'Shea部分R²','f.stat':'Wald统计量','f.pval':'P值','f.dist':'参考分布','bandwidth_scale':'带宽倍数','h_left':'左侧主带宽','h_right':'右侧主带宽','b_left':'左侧偏差带宽','b_right':'右侧偏差带宽','estimate':'估计值','std_error':'标准误','p_value':'P值','ci95_low':'区间下限','ci95_high':'区间上限','n_left':'左侧有效样本','n_right':'右侧有效样本','status':'计算状态','reason':'说明','error_type':'异常类型','cohort':'处理批次','time':'时期','relative_period':'距首次处理期数','ATT':'平均处理效应','lower':'区间下限','upper':'区间上限','name':'检查事项','note':'说明','value':'数值'}

def number(x):
    return '未计算' if x is None else format(x,'.4g') if isinstance(x,(int,float)) else str(x)

def table(rows):
    f=pd.DataFrame(rows).rename(columns=COLUMN_LABELS)
    if '计算状态' in f:f['计算状态']=f['计算状态'].replace({'computed':'已计算','unavailable':'无法计算','informative_only':'仅供诊断','diagnostic_only':'仅供诊断','warning':'需关注'})
    for c in f.select_dtypes(include='number'):f[c]=f[c].map(number)
    return f

def interval_figure(b):
    fig=go.Figure(go.Scatter(x=[b['estimate']],y=['主估计'],mode='markers',marker=dict(size=11,color='#22576c'),error_x=dict(type='data',array=[b['ci95'][1]-b['estimate']],arrayminus=[b['estimate']-b['ci95'][0]])))
    fig.add_vline(x=0,line_dash='dash',line_color='#8c969e');fig.update_layout(template='plotly_white',height=260,xaxis_title=b['unit']+'；横线表示95%置信区间',margin=dict(l=25,r=30,t=25,b=50))
    return fig

def extra_figures(b):
    figs=[]
    if 'event_study' in b:
        e=pd.DataFrame(b['event_study']);f=go.Figure(go.Scatter(x=e['relative_period'],y=e['ATT'],mode='lines+markers',error_y=dict(type='data',array=e['upper']-e['ATT'],arrayminus=e['ATT']-e['lower'])));f.add_hline(y=0,line_dash='dash');f.update_layout(template='plotly_white',xaxis_title='距首次处理的期数',yaxis_title='平均处理效应（逐点95%置信区间）');figs.append(('动态效应',f))
    if 'bandwidth_sensitivity' in b:
        rows=[x for x in b['bandwidth_sensitivity'] if x['status']=='computed']
        if rows:
            f=pd.DataFrame(rows);g=go.Figure(go.Scatter(x=f['bandwidth_scale'],y=f['estimate'],mode='markers',error_y=dict(type='data',array=f['ci95_high']-f['estimate'],arrayminus=f['estimate']-f['ci95_low'])));g.add_hline(y=0,line_dash='dash');g.update_layout(template='plotly_white',xaxis_title='相对主带宽的倍数（同时缩放偏差带宽）',yaxis_title='估计值与95%置信区间');figs.append(('带宽敏感性',g))
    if 'plot' in b:
        p=pd.DataFrame(b['plot']);f=go.Figure(go.Scatter(x=p.x,y=p.y,mode='markers'));f.add_vline(x=b['design']['cutoff'],line_dash='dash');f.update_layout(template='plotly_white',xaxis_title='运行变量分箱均值',yaxis_title='结果变量分箱均值');figs.append(('阈值附近的描述性分布（非拟合曲线）',f))
    return figs

def ar_text(b):
    a=b['ar_test']
    if a['status']!='computed':return a['reason']
    return '原假设：处理效应为'+number(a['null_effect'])+'。联合统计量为'+number(a['statistic'])+'，P值为'+number(a['p_value'])+'。'+('在5%水平拒绝该指定值。' if a['reject_at_5_percent'] else '在5%水平未拒绝该指定值。')+'使用'+('单向聚类' if a['covariance']=='cluster' else 'HC1异方差稳健')+'协方差及渐近卡方参照分布。'+a['interpretation']

def report(b):
    body='<header><p class="kicker">CAUSALOPS / RESEARCH REPORT</p><h1>'+escape(LABELS[b['method']])+'</h1><p>运行编号：'+escape(b['run_id'])+'</p></header>'
    body+='<h2>一、主要结论</h2><p>'+escape(b['conclusion'])+'</p><p>解释等级：'+escape(CLAIMS.get(b['claim'],b['claim']))+'。该等级依据已登记设计与本次诊断，不表示识别假设已获验证。</p>'
    body+='<table><tr><th>估计值</th><th>标准误</th><th>P值</th><th>分析样本</th><th>排除记录</th></tr><tr>'+''.join('<td>'+number(x)+'</td>' for x in [b['estimate'],b['std_error'],b['p_value'],b['analysis_rows'],b['excluded_rows']])+'</tr></table>'
    body+='<h2>二、估计幅度与不确定性</h2>'+interval_figure(b).to_html(full_html=False,include_plotlyjs=True)
    body+='<p>估计按登记单位解释。未登记业务基线、成本与适用人群时，不换算相对增幅、总体收益或投资回报率。P值若因数值精度显示为0，不表示真实概率严格等于0。</p>'
    body+='<h2>三、识别诊断与稳健性</h2>'
    if 'ar_test' in b:body+='<h3>指定效应值的AR型检验</h3><p>'+escape(ar_text(b))+'</p>'
    if 'treatment_jump' in b:
        x=b['treatment_jump'];body+='<p>阈值处实际处理概率的估计跳跃为'+number(x['estimate'])+'，95%置信区间为'+escape(str(x['ci95']))+'。该结果使用主估计的带宽；显著跳跃不能单独证明强第一阶段。</p>'
    for k,label in TABLES:
        if k in b:body+='<h3>'+label+'</h3>'+table(b[k]).to_html(index=False,escape=True)
    for title,fig in extra_figures(b):body+='<h3>'+title+'</h3>'+fig.to_html(full_html=False,include_plotlyjs=False)
    if 'diagnostics' in b:body+='<h3>其他诊断</h3>'+table(b['diagnostics']).to_html(index=False,escape=True)
    body+='<h2>四、解释范围与后续工作</h2><ul>'+''.join('<li>'+escape(w)+'</li>' for w in b['warnings'])+'</ul>'
    if 'boundary_register' in b:body+=pd.DataFrame(b['boundary_register']).to_html(index=False,escape=True)
    body+='<p>建议依次核对识别依据、异常样本与敏感性结果，再判断是否需要补充数据、开展独立验证或设计后续实验。执行失败的诊断应保留为限制，不以其他结果替代。</p>'
    body+='<h2>五、设计与复现记录</h2><p>估计实现：'+escape(b['implementation'])+'；包版本：'+escape(b['package_version'])+'</p><details><summary>展开完整运行证据</summary><pre>'+escape(json.dumps(b,ensure_ascii=False,indent=2))+'</pre></details>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(LABELS[b['method']])+' · CausalOps研究报告</title><style>body{font:16px/1.85 Microsoft YaHei,Arial;max-width:1080px;margin:40px auto;padding:0 24px;color:#24323d}header{border-bottom:2px solid #34566a;padding-bottom:15px}h1{font-size:30px}h2{font-size:22px;margin-top:34px}h3{font-size:18px}.kicker{font-size:12px;letter-spacing:.1em;color:#627584}table{border-collapse:collapse;width:100%;font-size:13px;display:block;overflow-x:auto}td,th{padding:9px;border:1px solid #d3dce3;text-align:left}th{background:#f3f6f8}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{padding:12px;border:1px solid #d3dce3}@page{size:A4;margin:16mm}@media print{h2,h3{break-after:avoid}tr{break-inside:avoid}}</style>'+body+'</html>'

def display(b):
    import streamlit as st
    st.subheader(LABELS[b['method']]);st.write(b['conclusion'])
    st.caption('解释等级：'+CLAIMS.get(b['claim'],b['claim']))
    cols=st.columns(4)
    for c,title,v in zip(cols,['估计值','标准误','P值','分析样本量'],[b['estimate'],b['std_error'],b['p_value'],b['analysis_rows']]):c.metric(title,number(v) if v else ('数值舍入为0' if title=='P值' else number(v)))
    st.plotly_chart(interval_figure(b),width='stretch')
    if 'ar_test' in b:
        st.markdown('**指定效应值的AR型检验**');st.write(ar_text(b))
    if 'treatment_jump' in b:
        x=b['treatment_jump'];st.info('处理概率跳跃：'+number(x['estimate'])+'；95%区间 '+str([round(v,4) for v in x['ci95']])+'。与主估计使用相同带宽，不能单独据此排除弱第一阶段。')
    for k,title in TABLES:
        if k in b:
            with st.expander(title,expanded=k=='bandwidth_sensitivity'):st.dataframe(table(b[k]),hide_index=True,width='stretch')
    for title,fig in extra_figures(b):
        st.markdown('**'+title+'**');st.plotly_chart(fig,width='stretch')
    with st.container(border=True):
        st.markdown('**解释范围与待完成检查**')
        for w in b['warnings']:st.write('• '+w)
        if 'boundary_register' in b:st.dataframe(pd.DataFrame(b['boundary_register']),hide_index=True,width='stretch')
    with st.expander('方法版本与完整运行证据'):
        st.caption('估计实现：'+b['implementation']+'；包版本：'+b['package_version']+'；运行编号：'+b['run_id']);st.json(b)

def confirmations(cfg,key):
    import streamlit as st
    f={};m=cfg['method'];f['design_evidence']=st.text_area('研究设计依据',key=key('evidence'),help='至少12字。请说明制度安排、变量时序、样本构成及主要局限。该内容须由研究者核对。')
    fields={'iv_2sls':{'instrument_exogeneity_reviewed':'有工具外生性的设计依据','exclusion_reviewed':'有排除限制的实质论证','monotonicity_reviewed':'二元处理的局部解释有单调性论证'},'rd_fuzzy':{'continuity_reviewed':'已核对阈值处潜在结果连续性的设计依据','no_manipulation_reviewed':'已评估阈值附近的排序与操纵风险','threshold_rule_reviewed':'阈值与分配规则在分析前已确定','exclusion_reviewed':'有阈值规则仅通过实际处理影响结果的依据','monotonicity_reviewed':'有处理接受行为单调性的设计依据'},'rd_sharp':{'continuity_reviewed':'阈值处潜在结果与其他因素连续的依据','no_manipulation_reviewed':'已评估阈值排序/操纵风险（不等于密度检验通过）','threshold_rule_reviewed':'阈值及清晰处理规则事先存在，非按结果挑选'},'staggered_did':{'parallel_reviewed':'有批次条件平行趋势的设计论证','no_anticipation_reviewed':'有无预期效应依据，当前anticipation固定为0'}}[m]
    if m=='iv_2sls':st.caption('同时报告指定效应值的AR型检验；常规2SLS区间不具备弱工具稳健性。')
    fields={**fields,'independent_units_reviewed':'已核对独立分析单位或独立簇','no_interference_reviewed':'已实质评估无跨单位干扰假设'}
    if cfg.get('covariates'):fields['covariates_pre_reviewed']='控制变量在处理前确定，未含处理后结果'
    for k,label in fields.items():f[k]=st.checkbox(label,key=key(k))
    f['allow_complete_case']=st.checkbox('允许必要字段缺失时完整案例排除并记录数量（面板缺失仍暂停）',key=key('missing'))
    return f

def builder(a,sid,frame):
    import streamlit as st
    st.subheader('研究设计与变量映射')
    st.write('选择方法并登记变量角色。提交后生成待审计划；在“研究计划与讨论”中审核设计依据后执行。')
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
            cfg['treatment']=choice('内生处理变量','treatment',numeric);cfg['instruments']=st.multiselect('排除工具变量',numeric,key=key('instruments'),placeholder='请选择工具变量');cfg['cluster']=choice('聚类字段（可选）','cluster',optional=True)
            cfg['ar_null']=st.number_input('AR型检验的原假设效应值',value=0.,key=key('ar_null'),help='按结果/处理单位填写。仅检验这个指定值，不生成弱工具稳健置信区间。')
        elif method in ('rd_sharp','rd_fuzzy'):
            cfg['running']=choice('运行变量','running',numeric);cfg['cutoff']=st.number_input('事先存在的阈值',value=0.,key=key('cutoff'));cfg['treatment']=choice('实际处理变量（0/1）','treatment',numeric,method=='rd_sharp');cfg['cluster']=choice('聚类字段（可选）','cluster',optional=True)
        else:
            cfg['time']=choice('连续整数期序（如1至10，不是日期字符串）','time',numeric);cfg['cohort']=choice('首次处理期（从未处理为空值）','cohort',numeric);cfg['control_group']=st.selectbox('对照规则',['never_treated','not_yet_treated'],format_func=lambda v:'从未处理' if v=='never_treated' else '尚未处理（含从未处理）',key=key('control'))
            st.caption('当前要求平衡面板、至少两个批次、每批和从未处理组至少20实体；上层聚类和时变控制尚未开放。')
        cfg['covariates']=st.multiselect('处理前数值控制变量（可留空）',numeric,key=key('covariates'),placeholder='可留空。不得包含标识、处理或结果字段。')
        if st.form_submit_button('提交研究设计'):
            try:
                d=AdvancedDesign.model_validate(cfg);hit=a.library.search(method,method=method);ids=[h['card_id'] for h in hit['hits']]
                p={'objective':q,'dataset_notes':['扩展设计由本地变量映射；尚未确认识别条件。'],'steps':[{'tool':'advanced','config':cfg,'reason':'采用明确的官方方法实现，执行前登记设计依据并检查数据支持。'}],'required_questions':['请核对结果、分析单位、真实制度与识别依据；方法不会自动证明假设。'],'citations':ids}
                a.store_plan(sid,p,'本地变量映射',q,hit);st.success('待审计划已保存。请在“研究计划与讨论”中审核并接受。');st.rerun()
            except (ValueError,RuntimeError) as exc:st.error(str(exc))
