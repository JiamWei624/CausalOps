"""User-facing research scope and immutable checks; no approval side effects."""
import streamlit as st

def render_research_quality(service,flow,jobs=None):
    value=service.output(flow['id'],'research_quality')
    if not value:
        st.caption('该历史流程没有研究质量快照；不会用当前口径补写旧记录。新建计划后可使用新版摘要。')
        return
    brief=value['brief'];audit=value['audit']
    question=resolved_research_question(service,flow,brief)
    with st.expander('研究摘要与待确认事项',expanded=flow['status'] in ('awaiting_review','needs_clarification')):
        st.markdown('**本次研究问题**');st.write(question)
        st.write(brief['question_type']+'；每行代表：'+brief['unit']+'；目标指标：'+brief['metric'])
        st.markdown('**依据与适用范围**');st.write('数据来源：'+brief['source']);st.write('结论对象：'+brief['population']);st.write('比较对象：'+brief['comparison']);st.write('估计目标：'+brief['estimand']);st.write('观察期间：'+brief['window'])
        st.caption('本摘要对应本轮的数据和口径版本。这里的声明不是识别假设的验证结果。')
        st.markdown('**待核对事项**')
        if brief['next_questions']:
            for q in brief['next_questions']:st.write('• '+q)
        else:st.write('当前结构检查未发现需补充项；仍须核对具体方法条件。')
        if st.button('补充研究范围与字段口径',key='quality_edit_'+flow['id']):
            st.session_state['_open_contract_'+flow['session_id']]=True;st.rerun()
        with st.expander('完整质量检查 · 结构、统计、关系、研究'):
            names={'pass':'结构检查通过','review':'待核对','block':'有阻断风险','declared':'已登记，未验证'}
            st.dataframe([{'层次':x['layer'],'状态':names[x['status']],'检查结果':x['detail'],'下一步':x['action']} for x in audit['checks']],hide_index=True,width='stretch')
            st.caption('这里只做局部数据审计；具体方法是否可执行由原审核与执行器决定。未改动原始数据。')
            st.download_button('下载本轮研究质量清单',__import__('json').dumps(value,ensure_ascii=False,indent=2),'research-quality.json','application/json',key='quality_download_'+flow['id'])

        if jobs is not None and flow['status'] in ('completed','needs_clarification','blocked','failed'):
            from causalops.application.research_quality import next_research_steps
            bound=service.contracts.bound(flow)
            options=next_research_steps(bound['body'] if bound else {},audit)
            with st.expander('可继续开展的研究'):
                for i,item in enumerate(options):
                    st.markdown('**'+item['title']+'**');st.caption(item['reason'])
                    if st.button('查看所需信息' if item['route']=='metadata' else '提出下一步方案',key='quality_next_'+flow['id']+'_'+str(i)):
                        try:
                            if item['route']=='metadata':st.session_state['_open_contract_'+flow['session_id']]=True
                            else:
                                job=jobs.submit_start(flow['session_id'],item['question'],mode=item['route'],parent_flow_id=flow['id'])
                                st.session_state['_graph_pending_'+flow['session_id']]=job['flow_id']
                            st.rerun()
                        except (ValueError,RuntimeError,OSError) as exc:st.error(str(exc))
                st.caption('只提出新方案或方法咨询；原运行保持不变，新计算仍需单独审核。')


def resolved_research_question(service,flow,brief):
    """Use the saved plan objective, never rewrite the original request snapshot."""
    if flow.get('plan_id'):
        plan=service.a.get_plan(flow['plan_id'])
        objective=plan['plan'].get('objective','').strip()
        if objective:return objective
    return brief['question']
