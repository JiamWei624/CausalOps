"""Small, resumable questions for first use, before any scientific claims."""
import streamlit as st
from causalops.application.guided_intake import GuidedIntake,INTENTS
from causalops.assistant.service import profile


def render_guided_intake(service,jobs,sid,frame):
    flow=GuidedIntake(service);state=flow.state(sid);latest=service.contracts.latest(sid)
    body=latest['body'] if latest else {};sha=latest['sha'] if latest else None;version=latest['version'] if latest else 0
    prefix='intake_'+sid+'_'+str(version)+'_'+str(state['step'])
    active=any(j['status'] in ('queued','running','cancel_requested') for j in jobs.jobs(sid))
    if state['step']==4:
        st.success('分析目标已确认：'+INTENTS[state['intention']]+'；关注指标：'+str(body.get('metric_label') or body.get('outcome') or '整体数据特征')+'。')
        st.caption('目标设置不代表已验证研究假设；计算计划仍需单独审核。')
        if st.button('调整分析目标',key=prefix+'_reset',disabled=active):flow.reset(sid,human_confirmed=True);st.rerun()
        if not service.flows(sid) and st.button('继续生成分析计划',key=prefix+'_retry',disabled=active):
            request=flow.question(sid,state['intention']);job=jobs.submit_start(sid,request['question'],mode=request['mode']);st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
        return
    st.markdown('**明确本次分析 · '+str(state['step'])+'/3**')
    st.caption('每次只需回答当前问题。不确定的信息可以留空，系统不会据此确认独立性或随机分配。')
    try:
        if state['step']==1:
            with st.form(prefix+'_unit'):
                st.write('这张表的一行代表什么？')
                unit=st.text_input('每行代表的对象（不确定可留空）',value=body.get('analysis_unit',''),placeholder='例如：一条检测样本、一位客户、某门店的一天')
                st.caption('这个描述不等于“每行相互独立”。重复观测需要在后续方法中另行处理。')
                if st.form_submit_button('保存并继续',disabled=active):flow.save_unit(sid,unit.strip(),expected_sha=sha,human_confirmed=True);st.rerun()
        elif state['step']==2:
            with st.form(prefix+'_target'):
                st.write('你最关心哪个指标？')
                choices=['']+[v['field'] for v in profile(frame)['fields'] if not v['likely_identifier']]
                field=st.selectbox('本次关注的指标',choices,index=choices.index(body.get('outcome')) if body.get('outcome') in choices else 0,format_func=lambda x:'尚不确定，先了解整体数据' if x == '' else x)
                label=st.text_input('指标名称（可选）',value=body.get('metric_label',''),placeholder='例如：质量评分、访问率、订单金额')
                unit=st.text_input('指标单位（不确定可留空）',value=body.get('metric_unit',''),placeholder='例如：分、元、次；不要猜测单位')
                st.caption('更换目标后，新计划需重新审核研究条件；历史结果仍按原目标解释。')
                if st.form_submit_button('确认指标并继续',disabled=active):flow.save_target(sid,field or None,label,unit,expected_sha=sha,human_confirmed=True);st.rerun()
        else:
            st.write('本次希望回答哪类问题？')
            intention=st.radio('选择分析目标',list(INTENTS),format_func=lambda x:INTENTS[x],key=prefix+'_goal')
            st.caption('分布分析将形成待审计划；关联探索先推荐具体问题；效果评估先核对必要信息，不把普通表自动作为实验。')
            if st.button('确认目标并制定下一步',type='primary',key=prefix+'_finish',disabled=active):
                jobs.capacity()
                request=flow.finish(sid,intention,human_confirmed=True)
                job=jobs.submit_start(sid,request['question'],mode=request['mode']);st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
    except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc));st.info('已保存的记录保留，可核对当前问题后重试。')
