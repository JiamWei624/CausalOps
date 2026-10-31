"""Plain-language entry actions and optional human-supplied context."""
from __future__ import annotations
import copy
import streamlit as st
from causalops.application.onboarding import start_basic_report

def render_start_actions(service,jobs,sid,frame):
    a=service.a
    st.markdown('**现在想先做什么？**')
    left,right=st.columns(2)
    if left.button('生成基础报告',type='primary',key='basic_report_'+sid,width='stretch',help='点击即同意在本地计算缺失、分布、频数与图表；不运行回归或因果分析。'):
        try:
            result=start_basic_report(a,sid,user_requested=True);st.session_state['_graph_pending_'+sid]=result['flow_id'];st.rerun()
        except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
    if right.button('推荐分析方向',key='find_questions_'+sid,width='stretch'):
        try:
            job=jobs.submit_start(sid,'我可以根据这张表做什么研究？请推荐可回答的问题。',mode='explore');st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
        except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
    st.caption('基础报告：直接查看样本特征。分析方向：先得到问题建议，不会自动计算。已有目标时可在下方直接提问。')
    latest=service.contracts.latest(sid)
    with st.expander('补充两项信息，让建议更贴合业务（可选）'):
        st.write('不知道可以留空。这里保存的是你提供的含义，不会自动确认随机分组、独立性或因果条件。')
        with st.form('simple_context_'+sid):
            body=copy.deepcopy(latest['body']) if latest else __import__('causalops.application.data_contracts',fromlist=['DataContract']).DataContract().model_dump()
            unit=st.text_input('每一行代表什么？',value=body['analysis_unit'],placeholder='例如：一瓶酒的一次检测、一位客户、一天的门店记录')
            columns=[None]+list(frame)
            outcome=st.selectbox('最关心哪个字段？',columns,index=columns.index(body['outcome']) if body['outcome'] in columns else 0,format_func=lambda x:'暂时不确定' if x is None else x)
            metric_unit=st.text_input('这个字段的单位是什么？',value=body['metric_unit'],placeholder='例如：分、元、次；不知道请留空')
            if st.form_submit_button('保存我提供的信息'):
                try:
                    body.update(analysis_unit=unit,outcome=outcome,metric_unit=metric_unit)
                    service.contracts.save(sid,body,human_confirmed=True,expected_sha=latest['sha'] if latest else None)
                    st.rerun()
                except (ValueError,RuntimeError) as exc:st.error(str(exc))
