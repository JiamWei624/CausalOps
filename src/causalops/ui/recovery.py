"""Explicit next actions; never alters research facts or executes a saved plan."""
import streamlit as st

def render_recovery(service,jobs,sid,flow,active,has_error=False):
    if active or (flow['status'] not in ('failed','blocked','needs_clarification') and not has_error):return
    key='recover_'+sid+'_'+flow['id']
    with st.container(border=True):
        st.markdown('**本轮处理尚未完成**')
        st.write('本任务已保存 '+str(len(service.a.completed_runs(sid)))+' 次统计运行，仍可在历史结果中查看。原始数据未修改，失败流程和原计划保留；以下操作不代表研究条件已满足。')
        first,second=st.columns(2)
        def edit_context():st.session_state['_open_contract_'+sid]=True
        first.button('补充字段与研究口径',key=key+'_context',on_click=edit_context)
        from causalops.ui.model_setup import use_local_mode,memory
        if not memory().get('local_only'):
            second.button('后续请求改用本地模式',key=key+'_local',on_click=use_local_mode)
        else:second.caption('后续请求已使用本地模式；当前保存的模型流程不会被自动改写。')
        st.caption('口径入口位于本任务上方。补充并保存后，请重新制定计划；不要勾选尚不清楚的研究事实。')
        if st.button('按当前口径重新制定待审计划',key=key+'_plan'):
            try:
                job=jobs.submit_start(sid,flow['request']['question'],mode='plan',parent_flow_id=flow['id'])
                st.session_state['_graph_pending_'+sid]=job['flow_id'];st.rerun()
            except (ValueError,RuntimeError,OSError):st.error('新计划未能提交。当前记录保留，请查看系统状态和队列后再试。')
        st.caption('重新制定只创建待审方案，不能继承旧批准；需再次核对。已批准但中断的原流程，可使用下方“检查批准并继续流程”单独恢复。')
