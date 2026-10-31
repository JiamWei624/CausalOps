"""Actual LangGraph StateGraph; checkpoints contain references, never data rows or clients."""
from __future__ import annotations
from typing import TypedDict
from pydantic import BaseModel,ConfigDict,Field
from langgraph.graph import StateGraph,START,END
from langgraph.types import interrupt
from langgraph.errors import GraphInterrupt
from causalops.general.service import DesignError
from causalops.assistant.service import profile

class ResearchState(TypedDict,total=False):
    flow_id: str
    route: str
    plan_id: str
    status: str

class MethodExplanation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    explanation: str=Field(min_length=1,max_length=3000)
    citations: list[str]=Field(min_length=1,max_length=8)

def build_graph(service):
    s=service
    def node(name,func):
        def run(state):
            fid=state['flow_id'];s.emit(fid,name,'started')
            try:
                result=func(state)
            except GraphInterrupt:raise
            except Exception as exc:
                s.emit(fid,name,'failed',{'exception_type':type(exc).__name__});s.update(fid,status='failed');raise
            s.emit(fid,name,'completed');return result
        return run
    def load(state):
        f=s.flow(state['flow_id'])
        if f['request']['data']!=s.data_binding(f['session_id']):raise DesignError('数据已变化，不能复用原流程。')
        return {'status':'ready'}
    def route(state):
        decision=s.decide_route(state['flow_id']);s.save_output(state['flow_id'],'route',decision.model_dump())
        return {'route':decision.route}
    def retrieve(state):
        fid=state['flow_id']
        if not s.output(fid,'retrieval'):s.save_output(fid,'retrieval',s.gateway.methods(fid))
        return {}
    def draft(state):
        fid=state['flow_id'];f=s.flow(fid)
        if f['plan_id']:p=s.a.get_plan(f['plan_id'])
        else:p=s.a.propose(f['session_id'],f['request']['question'],s.model,request_key=fid,retrieval=s.output(fid,'retrieval'))
        s.update(fid,plan_id=p['id'],status='awaiting_review')
        return {'plan_id':p['id'],'status':'awaiting_review'}
    def review(state):
        fid=state['flow_id'];f=s.flow(fid);p=s.a.get_plan(f['plan_id'])
        # Returning any value from interrupt wakes the node; it is never taken as an approval.
        interrupt({'kind':'research_review','flow_id':fid,'plan_id':p['id'],'plan_sha':p['sha'],
                   'data_sha':f['request']['data']['frame_sha'],'message':'请核对候选计划和必要事实，再通过研究服务批准或放弃。'})
        if s.flow(fid)['status']=='rejected':return {'status':'rejected'}
        s.verify_approval(fid)
        return {'status':'approved'}
    def execute(state):
        fid=state['flow_id'];s.update(fid,status='executing')
        tasks=s.gateway.execute(fid)
        refs=[t['result']['run_id'] for t in tasks if t['state']=='completed']
        done=all(t['state']=='completed' for t in tasks)
        s.save_output(fid,'execution',{'tasks':tasks,'run_ids':refs,'completed':done})
        status='executed' if done else 'blocked';s.update(fid,status=status)
        return {'status':status}
    def answer(state):
        fid=state['flow_id'];f=s.flow(fid)
        if not s.output(fid,'answer'):
            execution=s.output(fid,'execution')
            ids=execution['run_ids'][-1:] if execution else f['request']['run_ids']
            q='请解释本次结果的关键发现、实际含义、限制和下一步。' if execution else f['request']['question']
            s.save_output(fid,'answer',s.gateway.answer(fid,ids,q))
        s.update(fid,status='completed');return {'status':'completed'}
    def method(state):
        fid=state['flow_id'];f=s.flow(fid);hits=s.output(fid,'retrieval')
        if not s.output(fid,'answer'):
            if not hits['hits']:body={'source':'本地方法目录','text':'现有已核对资料不足以回答该问题，未生成替代引用。','facts':[],'citations':[]}
            elif s.model:
                raw=s.a._call(f['session_id'],s.model,'仅解释提供的方法资料：适用问题、数据要求、识别条件、诊断、失败情形。不要报告当前表的数值结果，不声称执行、批准或验证假设。引用只使用本轮card_id。',{'question':f['request']['question'],'retrieved_methods':hits},MethodExplanation.model_json_schema())
                reply=MethodExplanation.model_validate(raw);s.a.library.validate_citations(reply.citations,hits['hits'])
                body={'source':'模型方法解释＋本地来源校验','text':reply.explanation,'facts':[],'citations':reply.citations}
            else:
                lines=[]
                for h in hits['hits'][:3]:
                    lines.append(h['title']+'\n'+'\n'.join(k+'：'+v for k,v in h['sections'].items()))
                body={'source':'本地方法资料（未调用模型）','text':'\n\n'.join(lines),'facts':[],'citations':[h['card_id'] for h in hits['hits'][:3]]}
            body.update(run_ids=[],scope='method_only',knowledge_sha256=s.a.library.digest)
            s.save_output(fid,'answer',body)
        s.update(fid,status='completed');return {'status':'completed'}
    def data_profile(state):
        fid=state['flow_id'];f=s.flow(fid)
        s.save_output(fid,'profile',profile(s.ws.load_upload(f['request']['data']['upload_id'])))
        s.update(fid,status='completed');return {'status':'completed'}
    def clarify(state):
        fid=state['flow_id'];decision=s.output(fid,'route')
        s.save_output(fid,'answer',{'source':'本地流程检查','text':decision['reason'],'facts':[],'citations':[],'run_ids':[]})
        s.update(fid,status='needs_clarification');return {'status':'needs_clarification'}
    graph=StateGraph(ResearchState)
    funcs={'load_context':load,'route_intent':route,'retrieve_methods':retrieve,'draft_plan':draft,'await_review':review,'execute_plan':execute,'answer_results':answer,'answer_method':method,'profile_data':data_profile,'clarify':clarify}
    for name,func in funcs.items():graph.add_node(name,node(name,func))
    graph.add_edge(START,'load_context');graph.add_edge('load_context','route_intent')
    graph.add_conditional_edges('route_intent',lambda st:st['route'],{'plan':'retrieve_methods','method':'retrieve_methods','results':'retrieve_methods','profile':'profile_data','clarify':'clarify'})
    graph.add_conditional_edges('retrieve_methods',lambda st:st['route'],{'plan':'draft_plan','method':'answer_method','results':'answer_results'})
    graph.add_edge('draft_plan','await_review')
    graph.add_conditional_edges('await_review',lambda st:st['status'],{'approved':'execute_plan','rejected':END})
    graph.add_conditional_edges('execute_plan',lambda st:'answer' if st['status']=='executed' else 'end',{'answer':'answer_results','end':END})
    for name in ['answer_results','answer_method','profile_data','clarify']:graph.add_edge(name,END)
    return graph
