"""Plain-language entry actions and optional human-supplied context."""
from __future__ import annotations
import copy
import streamlit as st
from causalops.application.onboarding import start_basic_report

def render_first_look(frame, sid, preset, brief):
    import numpy as np
    import pandas as pd
    fields = [f for f in brief['fields'] if not f['likely_identifier'] and f['numeric']]
    st.write(f"全表 {len(frame):,} 行；缺失单元格 {sum(f['missing_n'] for f in brief['fields']):,} 个，完全重复记录 {brief['exact_duplicate_rows']:,} 条。重复记录保留在样本中。")
    if not fields:
        categories = [f['field'] for f in brief['fields']
                      if not f['likely_identifier'] and 1 <= f['distinct_n'] <= min(20, max(1, len(frame)//2))]
        if categories:
            category = st.selectbox('查看类别分布', categories, key='preview_category_'+sid)
            freq = frame[category].dropna().value_counts().rename('记录数')
            st.dataframe(freq.to_frame(), width='stretch')
            st.caption('频数仅计入该字段非缺失的记录；未合并相似类别。')
        else:
            st.caption('缺少可预览的数值或低基数类别字段。可生成完整报告，查看字段完整性。')
        return
    names = {f['field']: f['meaning'] for f in preset.get('fields', [])}
    choices = [f['field'] for f in fields]
    target = preset.get('target')
    col = st.selectbox('查看指标分布', choices, index=choices.index(target) if target in choices else 0,
        format_func=lambda x: names.get(x, x), key='preview_field_'+sid)
    values = frame[col].replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        st.info('所选指标没有有限数值，可切换字段。')
        return
    unit = preset.get('metric_unit', '') if col == target else ''
    st.write(f"{names.get(col,col)}有 {len(values):,} 个有效值，中位数 {values.median():.4g}{unit}，范围 {values.min():.4g} 至 {values.max():.4g}{unit}。")
    if values.nunique() <= 20:
        counts = values.value_counts().sort_index()
        labels = [f'{v:g}' for v in counts.index]
    else:
        counts = pd.cut(values, bins=12, duplicates='drop').value_counts().sort_index()
        labels = [str(v) for v in counts.index]
    chart = pd.DataFrame({'取值或区间':labels, '记录数':counts.to_numpy()})
    import plotly.express as px
    fig = px.bar(chart, x='取值或区间', y='记录数')
    fig.update_xaxes(type='category')
    fig.update_layout(height=250, margin=dict(t=10,b=30))
    st.plotly_chart(fig, key='preview_chart_'+sid, width='stretch')
    st.caption('横轴为取值或分组区间，纵轴为原始记录数。图中只使用当前字段的有限数值。')

def basic_report_button(a,sid, *, sample_service=None):
    use_sample = sample_service is not None and not sample_service.contracts.latest(sid)
    if use_sample:
        st.caption('生成报告时采用此示例的公开定义，以质量评分为主要指标。')
    if st.button('生成完整描述统计报告',type='primary',key='basic_report_'+sid,help='在本地计算并保存描述统计，可继续追问或导出。'):
        try:
            if use_sample:
                from causalops.application.guided_intake import GuidedIntake
                GuidedIntake(sample_service).use_example(sid,expected_sha=None,human_confirmed=True)
            result=start_basic_report(a,sid,user_requested=True)
            st.session_state['_graph_pending_'+sid]=result['flow_id']
            st.rerun()
        except (ValueError,RuntimeError,OSError) as exc:
            st.error(str(exc))

def render_start_actions(service,jobs,sid,frame):
    a=service.a
    from causalops.sample_data import example_context
    example=example_context(a,sid)
    from causalops.assistant.service import profile
    first_look=st.radio('选择分析起点',['先了解数据','已有明确问题'],horizontal=True,key='start_path_'+sid)
    if first_look=='先了解数据':
        preset=example['onboarding'] if example else {}
        if preset:
            st.write(preset['description'])
            st.caption(preset['analysis_unit']+'。'+preset['target_definition'])
        render_first_look(frame,sid,preset,profile(frame))
        basic_report_button(a,sid,sample_service=service if example else None)
        if example:
            st.caption('可继续研究：质量评分集中在哪些分值？酒精含量与评分是否相关？这些样本仅支持描述和关联解释。')
        else:
            st.caption('可继续研究：哪个指标分布最集中？是否存在缺失或分组差异？')
        st.caption('已有业务或研究问题时，可切换到“已有明确问题”，或直接在下方提问。')
        return
    if example and not service.flows(sid):
        preset=example['onboarding'];latest=service.contracts.latest(sid);body=latest['body'] if latest else {}
        with st.container(border=True):
            st.markdown('**示例说明 · 葡萄酒质量**');st.write(preset['description']);st.write('每行代表：'+preset['analysis_unit']);st.write(preset['target_definition']);st.markdown('**本例建议问题：** '+preset['question'])
            st.markdown('[官方数据说明与许可]('+example['landing_url']+')');st.caption('示例含义依据官方数据说明提供；不自动确认独立性、随机化或因果识别条件。')
            if not body.get('method_facts') and not body.get('predictors') and not body.get('covariates') and not body.get('treatment') and body.get('outcome') in (None,preset['target']):
                if st.button('使用示例说明并生成分析计划',type='primary',key='example_defaults_'+sid):
                    try:
                        from causalops.application.guided_intake import GuidedIntake
                        jobs.capacity();req=GuidedIntake(service).use_example(sid,expected_sha=latest['sha'] if latest else None,human_confirmed=True)
                        job=jobs.submit_start(sid,req['question'],mode=req['mode']);st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
                    except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
            with st.expander('字段含义与使用边界'):
                st.dataframe([{'字段':f['field'],'含义':f['meaning'],'单位':f['unit'] or '未在此处登记'} for f in preset['fields']],hide_index=True,width='stretch')
                for line in preset['limitations']:st.write(line)
    if not service.flows(sid) and not example:
        from causalops.assistant.service import profile
        from causalops.application.question_discovery import local_suggestions
        brief=profile(frame);safe=[x for x in brief['fields'] if not x['likely_identifier']]
        with st.container(border=True):
            st.markdown('**数据概览与初步建议**')
            st.write('已导入 '+format(brief['rows'],',')+' 条记录、'+str(brief['columns'])+' 个字段。其中可统计数值字段 '+str(sum(x['numeric'] for x in safe))+' 个。')
            missing=sum(x['missing_n'] for x in brief['fields'])
            st.write('缺失单元格 '+format(missing,',')+' 个；完全重复记录 '+format(brief['exact_duplicate_rows'],',')+' 条。原始记录保持不变。')
            names={v['field']:v['meaning'] for v in example['onboarding']['fields']} if example else {}
            st.caption('主要字段：'+'、'.join(names.get(x['field'],x['field']) for x in safe[:6]))
            st.caption('字段类型不等于业务含义；分析单位、指标单位与观测时点尚需按实际情况确认。')
            st.caption('以上为本地数据结构检查，未调用外部模型，尚未执行分析计划。')
    from causalops.ui.guided_intake import render_guided_intake
    if example and not service.flows(sid):
        with st.expander('逐项核对或修改示例设置'):
            with st.container(border=True):render_guided_intake(service,jobs,sid,frame)
    else:
        with st.container(border=True):render_guided_intake(service,jobs,sid,frame)
    with st.expander('其他分析起点'):
        render_alternative_actions(service,jobs,sid,frame)

def render_alternative_actions(service,jobs,sid,frame):
    a=service.a
    st.markdown('**分析起点**')
    left,right=st.columns(2)
    with left:basic_report_button(a,sid)
    if right.button('推荐分析方向',key='find_questions_'+sid,width='stretch'):
        try:
            job=jobs.submit_start(sid,'我可以根据这张表做什么研究？请推荐可回答的问题。',mode='explore');st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
        except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
    st.caption('基础报告用于样本特征分析；分析建议用于明确研究目标。也可直接输入分析要求。')
    latest=service.contracts.latest(sid)
    with st.expander('分析口径（可选）'):
        st.write('未明确的信息可保留为空。以下内容作为使用者声明保存，不自动确认研究条件。')
        with st.form('simple_context_'+sid):
            body=copy.deepcopy(latest['body']) if latest else __import__('causalops.application.data_contracts',fromlist=['DataContract']).DataContract().model_dump()
            unit=st.text_input('分析单位',value=body['analysis_unit'],placeholder='例如：一瓶酒的一次检测、一位客户、一天的门店记录')
            columns=[None]+list(frame)
            outcome=st.selectbox('目标指标',columns,index=columns.index(body['outcome']) if body['outcome'] in columns else 0,format_func=lambda x:'尚未明确' if x is None else x)
            metric_unit=st.text_input('指标单位',value=body['metric_unit'],placeholder='例如：分、元、次；不知道请留空')
            if st.form_submit_button('保存分析口径'):
                try:
                    body.update(analysis_unit=unit,outcome=outcome,metric_unit=metric_unit)
                    service.contracts.save(sid,body,human_confirmed=True,expected_sha=latest['sha'] if latest else None)
                    st.rerun()
                except (ValueError,RuntimeError) as exc:st.error(str(exc))
