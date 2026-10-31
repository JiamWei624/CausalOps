"""User-run usability study instrument, not synthetic human evaluation."""
import json
import streamlit as st
from causalops.evaluation.user_trials import UserTrials

def render_user_trial(ws):
    trials=UserTrials(ws);st.subheader('使用效果与任务效率评测')
    st.write('请邀请未参与开发的人独立完成：导入表格→确定字段与方法→解释结论和边界→导出报告。相同任务分别用原有工具和本助手完成，交替安排先后顺序。由另一人核对答案，不能把程序测试当作人的评测。')
    participant=st.text_input('匿名参与者编号（不要真实姓名）',key='ut_participant');pair=st.text_input('配对任务编号',value='T1',key='ut_pair');task=st.text_area('统一验收目标与判分规则',value='计算指定字段的有效样本数、均值、缺失率；解释分母和非因果边界；导出可追溯报告。',key='ut_task')
    mode=st.radio('本次使用方式',['manual','assistant'],format_func=lambda v:'原有人工工具流程' if v=='manual' else 'CausalOps助手流程',horizontal=True,key='ut_mode')
    if st.button('开始本次真实任务计时',key='ut_start'):
        try:st.session_state['ut_active']=trials.start(participant,pair,mode,task);st.success('计时已开始，包含阅读、操作与思考。')
        except ValueError as e:st.error(str(e))
    if st.session_state.get('ut_active'):
        st.caption('正在计时：'+st.session_state['ut_active'][:12]);correct=st.checkbox('评审已核对结果正确且口径完整',key='ut_correct');exported=st.checkbox('报告已经实际导出并可打开',key='ut_export');x,y=st.columns(2);errors=int(x.number_input('错误次数',min_value=0,key='ut_errors'));rework=int(y.number_input('返工次数',min_value=0,key='ut_rework'))
        if st.button('结束并记录本次任务',key='ut_finish'):
            try:trials.finish(st.session_state.pop('ut_active'),reviewed_correct=correct,error_count=errors,rework_count=rework,report_exported=exported);st.success('已记录。本次记录尚不是总体提效结论。')
            except ValueError as e:st.error(str(e))
    report=trials.report();st.caption('已完成真实任务：'+str(report['completed_tasks'])+'；满足正确且导出条件的配对：'+str(len(report['valid_correct_exported_pairs'])))
    if not report['completed_tasks']:st.info('尚无独立参与者的完成记录，暂不报告使用效率差异。')
    st.download_button('下载真实任务评测记录',json.dumps(report,ensure_ascii=False,indent=2),file_name='CausalOps-user-trials.json',key='ut_download')
