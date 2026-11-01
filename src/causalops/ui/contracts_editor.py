"""Local human data dictionary editor. No model is allowed to register facts."""
import pandas as pd
import streamlit as st
from causalops.application.data_contracts import DataContract
from causalops.assistant.contracts import REGISTRY
from causalops.orchestration.method_research import FACTS

FACT_LABELS={'assignment':'处理分配机制','independent_rows_reviewed':'已核对独立行推断条件','independent_units_reviewed':'已核对独立分析单位','allow_complete_case':'允许完整案例分析并保留排除数','comparable_exposure_reviewed':'计数暴露时长和口径可比','covariates_reviewed':'协变量已核对为处理前测量','exchangeability_declared':'有依据声明条件可交换性','overlap_declared':'已声明共同支撑的合理性，仍需诊断','panel_confirmed':'已确认适用的面板与对照结构','parallel_declared':'已提供平行趋势论证','no_anticipation_declared':'已论证无预期效应','design_evidence':'具体研究设计依据','instrument_exogeneity_reviewed':'已论证工具外生性','exclusion_reviewed':'已论证排除限制','monotonicity_reviewed':'已论证单调性','continuity_reviewed':'已论证阈值附近连续性','no_manipulation_reviewed':'已论证无精确操纵','threshold_rule_reviewed':'已核对阈值分配规则','parallel_reviewed':'已论证平行趋势','no_anticipation_reviewed':'已论证无预期效应','no_interference_reviewed':'已评估干扰假设'}

def render_fact_fields(method,saved,prefix):
    fields=list(dict.fromkeys(FACTS.get(method,[])+(['allow_complete_case'] if method not in ('descriptive','correlation') else [])))
    result={}
    for field in fields:
        label=FACT_LABELS.get(field,field);key=prefix+'_'+field
        if field=='assignment':
            options=['unknown','observational','randomized'];value=saved.get(field,'unknown')
            result[field]=st.selectbox(label,options,index=options.index(value),format_func=lambda x:{'unknown':'尚不清楚','observational':'观察性/非随机','randomized':'有真实随机分配依据'}[x],key=key)
        elif field=='design_evidence':result[field]=st.text_area(label,value=saved.get(field,''),key=key,help='填写具体来源、设计与适用条件，不能由模型代确认。')
        else:result[field]=st.checkbox(label,value=saved.get(field,False),key=key)
    return result

def render_contract(service,sid,frame):
    latest=service.contracts.latest(sid);body=DataContract.model_validate(latest['body'] if latest else {}).model_dump();version=latest['version'] if latest else 0
    with st.expander('数据字典与研究口径'+(' · V'+str(version) if version else ' · 尚未登记')):
        st.caption('字段口径和人工声明按数据与版本保存，后续计划可预填。声明不等于经验验证；修改后，旧候选和旧批准不能直接用于新版本。自由文字仅在本地保存。')
        basic,details,facts,history=st.tabs(['关键口径','字段说明','研究声明','版本记录'])
        prefix='dict_'+sid+'_'+str(version);options=['']+list(frame)
        def choose(label,field):
            value=body.get(field) or '';return st.selectbox(label,options,index=options.index(value) if value in options else 0,format_func=lambda x:'未登记' if x == '' else x,key=prefix+'_'+field) or None
        with basic:
            body['analysis_unit']=st.text_input('一行代表什么',value=body['analysis_unit'],key=prefix+'_unit',placeholder='例如：客户、会话、用户每天')
            structures=['unknown','cross_section','panel'];body['structure']=st.selectbox('数据结构',structures,index=structures.index(body['structure']),format_func=lambda x:{'unknown':'尚未确认','cross_section':'截面/每单位一行','panel':'面板/重复观测'}[x],key=prefix+'_structure')
            purposes=['exploratory','predictive','causal'];body['purpose']=st.selectbox('研究用途',purposes,index=purposes.index(body['purpose']),format_func=lambda x:{'exploratory':'探索与关联解释','predictive':'预测（需另行验证时点与样本外效果）','causal':'干预或策略效果评估'}[x],key=prefix+'_purpose')
            a,b=st.columns(2)
            with a:body['outcome']=choose('结果字段','outcome');body['entity']=choose('实体/随机化单位标识','entity');body['time']=choose('观测时间字段','time')
            with b:body['treatment']=choose('处理/分组字段','treatment');body['treatment_time']=choose('首次处理时间字段','treatment_time')
            body['predictors']=st.multiselect('关联模型自变量',list(frame),default=body['predictors'],key=prefix+'_predictors',placeholder='请选择自变量')
            body['covariates']=st.multiselect('处理前协变量',list(frame),default=body['covariates'],key=prefix+'_covariates',placeholder='请选择处理前协变量')
            a,b=st.columns(2)
            with a:body['control_value']=st.text_input('对照值（按原始数据文本填写）',value=body['control_value'] or '',key=prefix+'_control') or None
            with b:body['treated_value']=st.text_input('处理值（按原始数据文本填写）',value=body['treated_value'] or '',key=prefix+'_treated') or None
            body['metric_label']=st.text_input('指标名称',value=body['metric_label'],key=prefix+'_metriclabel')
            body['metric_unit']=st.text_input('指标单位',value=body['metric_unit'],key=prefix+'_metricunit')
            kinds=['unknown','continuous','binary','count'];body['metric_kind']=st.selectbox('指标类型',kinds,index=kinds.index(body['metric_kind']),format_func=lambda x:{'unknown':'尚未确认','continuous':'连续指标','binary':'二元指标','count':'计数指标'}[x],key=prefix+'_kind')
            body['metric_window']=st.text_input('指标观察窗口',value=body['metric_window'],key=prefix+'_window')
            with st.expander('进阶设计字段（仅在使用IV/RD/交错DID时填写）'):
                body['instruments']=st.multiselect('工具变量',list(frame),default=body['instruments'],key=prefix+'_iv',placeholder='请选择工具变量');body['running']=choose('断点运行变量','running');body['cohort']=choose('首次处理期/批次','cohort')
                known=st.checkbox('已明确登记断点阈值',value=body['cutoff'] is not None,key=prefix+'_cutoff_known')
                body['cutoff']=st.number_input('断点阈值',value=float(body['cutoff'] or 0),key=prefix+'_cutoff') if known else None
        with details:
            existing={v['field']:v for v in body['fields']}
            rows=[existing.get(c,{'field':c,'meaning':'','unit':'','role':'unspecified','timing':'unknown'}) for c in frame]
            edited=st.data_editor(pd.DataFrame(rows).rename(columns={'field':'字段','meaning':'含义','unit':'单位','role':'角色','timing':'测量时点'}),disabled=['字段'],hide_index=True,width='stretch',key=prefix+'_fields',column_config={'角色':st.column_config.SelectboxColumn(options=['unspecified','identifier','time','treatment','outcome','covariate','measure','category']),'测量时点':st.column_config.SelectboxColumn(options=['unknown','pre_treatment','post_treatment','future','time_invariant'])})
            body['fields']=[]
            for row in edited.fillna('').rename(columns={'字段':'field','含义':'meaning','单位':'unit','角色':'role','测量时点':'timing'}).to_dict('records'):
                if row['meaning'] or row['unit'] or row['role']!='unspecified' or row['timing']!='unknown':body['fields'].append(row)
            st.caption('pre_treatment=处理前；post_treatment=处理后；future=未来；unknown=待确认。程序不会按字段名自动确认时序。')
        with facts:
            methods=st.multiselect('需要保存声明的方法',list(REGISTRY),default=list(body['method_facts']),format_func=lambda m:REGISTRY[m].label,key=prefix+'_methods',placeholder='请选择需要登记声明的方法')
            values={}
            for method in methods:
                st.markdown('**'+REGISTRY[method].label+'**');values[method]=render_fact_fields(method,body['method_facts'].get(method,{}),prefix+'_'+method)
            body['method_facts']=values
            st.caption('只登记有依据的声明；不要为了启用按钮而全部勾选。执行时仍进行原方法检查。')
        with history:
            versions=service.contracts.versions(sid)
            if versions:st.dataframe([{'版本':v['version'],'登记时间':v['created'],'指纹':v['sha'][:12],'证据类型':'人工声明（未由程序证明）'} for v in versions],hide_index=True,width='stretch')
            else:st.info('尚无数据字典版本。')
        body['notes']=st.text_area('本地口径备注',value=body['notes'],key=prefix+'_notes')
        checked=st.checkbox('我确认以上内容为本人提供的口径与声明，并理解它们不等于识别假设已被验证。',key=prefix+'_confirm')
        if st.button('保存数据字典新版本',disabled=not checked,key=prefix+'_save'):
            try:service.contracts.save(sid,body,expected_sha=latest['sha'] if latest else None,human_confirmed=True);st.rerun()
            except (ValueError,RuntimeError) as exc:st.error(str(exc))
