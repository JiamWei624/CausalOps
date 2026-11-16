"""UI return tokens over existing services; tokens never authorize research execution."""
import streamlit as st
from causalops.application.chat_sessions import ChatService
from causalops.application.chat_workflow import ChatWorkflow
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace


def current():
    cid=st.query_params.get('chat');handoff=st.query_params.get('chat_flow')
    if not cid or not handoff:return None
    service=ChatService(ResearchService(AssistantWorkspace()));flow=ChatWorkflow(service)
    flow.get(cid,handoff)
    return service,flow,cid,handoff


def publish(task_id):
    bridge=current()
    if bridge:
        _,flow,cid,handoff=bridge
        flow.publish(cid,handoff,task_id)


def registered_file():
    bridge=current()
    if not bridge:return None
    _,flow,cid,handoff=bridge
    root=flow.get(cid,handoff)
    return flow.input_file(cid,handoff) if root['origin']['domain']=='assistant' else None


def return_to_chat():
    try:
        bridge=current()
        if bridge:
            service,flow,cid,handoff=bridge
            source=flow.refresh(cid,handoff)
            if st.query_params.get('route') in ('evidence','decisions'):
                meta=source['metadata'];expected=meta['subject_id'] if meta['domain']=='automation_v2' else meta['assistant_session_id']
                if st.query_params.get('diagnostic_task')!=expected:raise ValueError('诊断任务来源与会话不一致。')
                from causalops.application.chat_artifacts import artifacts
                artifacts(service,cid,report_id=st.query_params.get('diagnostic_report'))
            flow.answer_goal(cid,handoff)
    except (ValueError,RuntimeError,OSError):
        st.session_state['chat_return_error']='正式研究来源发生变化，未自动替换当前绑定。请核对数据、方案或研究身份后明确关联。'
    st.query_params['route']='home'


def notice():
    bridge=current()
    if not bridge:return
    _,flow,cid,handoff=bridge
    link=flow.latest(cid,handoff)
    selected=st.query_params.get('automation')
    root=flow.get(cid,handoff)
    expected=link['task_id'] if link else root['origin']['subject_id'] if root['origin']['domain']=='automation_v2' else None
    if selected and selected!=expected:
        raise ValueError('当前研究与会话正式流程来源不一致。请返回原会话重新进入，不自动关联其他任务。')
    st.caption('来自研究对话 · '+cid[:8]+'。本工作区完成正式确认与审核；返回后读取真实保存状态。')
