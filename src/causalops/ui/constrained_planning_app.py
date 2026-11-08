"""Optional contract-only planning UI. Explicit choices, no execution or silent fallback."""
import streamlit as st
from causalops.application.constrained_planning import CandidatePlanning,REASONS
from causalops.application.configurable_research import ConfigurablePlan2,parse_plan
from causalops.general.service import DesignError
from causalops.llm.providers import StructuredModelClient

def render(co,t):
    p=parse_plan(t['plan'])
    if not isinstance(p,ConfigurablePlan2):return True
    svc=CandidatePlanning(co);tid=t['id']
    st.subheader('候选研究计划生成')
    if p.candidate_ref:
        r=svc.get(p.candidate_ref['task_id'],p.candidate_ref['id'])
        st.info('已显式采纳'+({'model_assisted':'模型候选','simulated_model':'模拟候选（测试）','deterministic':'受限模板候选'}[r['source']])+'，形成当前独立待审计划；尚未批准执行。')
        st.write(REASONS[r['candidate']['rationale']])
        st.caption('候选来源任务：'+p.candidate_ref['task_id']+'；候选：'+p.candidate_ref['id'])
        with st.expander('规划来源的模型预算与真实调用记录'):st.json(co.budget(p.candidate_ref['task_id']))
        return True
    if t['status']=='paused':
        st.warning('规划因资源检查停止；原合同、候选与账本保留。可明确转为无模型模板的新候选，仍需重新审核。')
        ck=st.checkbox('我选择确定性模板回退，不恢复或增加模型请求',key='planning_fallback_ack_'+tid)
        if st.button('转为确定性模板新候选',disabled=not ck,key='planning_fallback_'+tid):
            try:
                newer=svc.fallback(tid,human_confirmed=ck);st.query_params['automation']=newer['id'];st.rerun()
            except (ValueError,RuntimeError) as exc:st.error(str(exc))
        return False
    mode=st.radio('计划生成方式',['使用受限研究模板','使用模型辅助生成候选计划'],key='planning_mode_'+tid)
    st.caption('模型只可在描述性路径与符合登记设计条件的A/B路径中提出候选。条件未知不改写为已确认；采纳不等于统计批准。')
    if mode=='使用受限研究模板':
        st.write('当前待审路径：'+('双组二元A/B，执行前仍需证据门禁' if p.research_path=='randomized_two_arm_binary' else '描述统计与证据核验，不执行A/B'))
        if st.button('生成受限模板候选',key='planning_template_'+tid):
            r=svc.template(tid);st.session_state['planning_selected_'+tid]=r['id'];st.rerun()
    else:
        from causalops.ui.model_setup import current_connection,memory
        cfg,key=current_connection();configured=bool(cfg and key and not memory().get('local_only'))
        if not configured:st.info('模型未配置或当前为本地模式。可在侧边栏“模型与隐私”配置；也可明确选择受限模板继续，不影响历史结果。')
        payload=svc.payload(tid);sha=svc.payload_sha(tid)
        st.write('仅发送当前合同摘要与版本指纹，不发送原始记录、标识值、文件路径或历史聊天。字段名和目标仍可能敏感，请先核对。')
        if cfg:st.caption('目标服务：'+cfg.provider+' / '+cfg.model+' / '+cfg.base_url)
        with st.expander('核对本次完整待发送内容'):st.json(payload)
        ack=st.checkbox('我已检查合同摘要不含敏感信息，授权本次发送给指定模型',key='planning_external_'+tid+'_'+sha)
        if st.button('生成模型候选',disabled=not configured or not ack,key='planning_generate_'+tid):
            client=None
            try:
                co.a.consent(t['session_id'],True,cfg)
                client=StructuredModelClient(cfg,key)
                with st.spinner('仅生成候选；不批准或运行统计…'):
                    r=svc.model_candidate(tid,client,payload_sha=sha,human_confirmed=ack)
                st.session_state['planning_selected_'+tid]=r['id'];st.rerun()
            except (ValueError,RuntimeError) as exc:st.error(str(exc))
            finally:
                if client is not None:client.close()
    history=svc.history(tid)
    if history:
        by={r['id']:r for r in history};ids=list(by);selected=st.session_state.get('planning_selected_'+tid,ids[0])
        cid=st.selectbox('已保存的候选研究计划',ids,index=ids.index(selected) if selected in ids else 0,
                         format_func=lambda x:('模型' if by[x]['source']=='model_assisted' else '模拟' if by[x]['source']=='simulated_model' else '模板')+' · '+by[x]['status']+' · '+x[:12],key='planning_history_'+tid+'_'+ids[0])
        r=by[cid]
        if r['status']!='validated':st.warning('该候选未通过：'+((r['raw'].get('message') or str(r['error_code'])) if r['status']=='failed' else '字段、设计声明、方法或依赖未满足当前合同')+'。没有应用到当前计划或获得执行权限；可查看记录，明确选择模板或重新配置。')
        else:
            st.write('建议依据：'+REASONS[r['candidate']['rationale']])
            st.json(r['candidate'])
            if st.button('采纳候选并生成正式待审计划',key='planning_adopt_'+tid+'_'+cid):
                try:
                    newer=svc.adopt(tid,cid,human_confirmed=True);st.query_params['automation']=newer['id'];st.rerun()
                except (ValueError,RuntimeError) as exc:st.error(str(exc))
        with st.expander('候选原始响应与确定性校验记录'):st.json(r)
    return mode=='使用受限研究模板'
