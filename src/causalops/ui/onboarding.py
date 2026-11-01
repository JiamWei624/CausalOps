"""Plain-language entry actions and optional human-supplied context."""
from __future__ import annotations
import copy
import streamlit as st
from causalops.application.onboarding import start_basic_report

def render_start_actions(service,jobs,sid,frame):
    a=service.a
    if not service.flows(sid):
        from causalops.assistant.service import profile
        from causalops.application.question_discovery import local_suggestions
        brief=profile(frame);safe=[x for x in brief['fields'] if not x['likely_identifier']]
        with st.container(border=True):
            st.markdown('**数据概览与初步建议**')
            st.write('已导入 '+format(brief['rows'],',')+' 条记录、'+str(brief['columns'])+' 个字段。其中可统计数值字段 '+str(sum(x['numeric'] for x in safe))+' 个。')
            missing=sum(x['missing_n'] for x in brief['fields'])
            st.write('缺失单元格 '+format(missing,',')+' 个；完全重复记录 '+format(brief['exact_duplicate_rows'],',')+' 条。原始记录保持不变。')
            st.caption('主要字段：'+'、'.join(x['field'] for x in safe[:6]))
            st.caption('字段类型不等于业务含义；分析单位、指标单位与观测时点尚需按实际情况确认。')
            st.caption('以上仅为本地数据结构检查，未调用模型、未执行统计。')
    from causalops.ui.guided_intake import render_guided_intake
    with st.container(border=True):render_guided_intake(service,jobs,sid,frame)
    with st.expander('其他分析起点'):
        render_alternative_actions(service,jobs,sid,frame)

def render_alternative_actions(service,jobs,sid,frame):
    a=service.a
    st.markdown('**分析起点**')
    left,right=st.columns(2)
    if left.button('生成基础报告',type='primary',key='basic_report_'+sid,width='stretch',help='点击即同意在本地计算缺失、分布、频数与图表；不运行回归或因果分析。'):
        try:
            result=start_basic_report(a,sid,user_requested=True);st.session_state['_graph_pending_'+sid]=result['flow_id'];st.rerun()
        except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
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
