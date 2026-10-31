"""A2A 1.0 local reviewer: real SDK transport, no estimator/approval permission."""
from __future__ import annotations
import argparse,json,re,uuid,asyncio
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from starlette.applications import Starlette
from a2a.server.agent_execution import AgentExecutor,RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater,InMemoryTaskStore
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_jsonrpc_routes,create_agent_card_routes
from a2a.types import AgentCard,AgentCapabilities,AgentSkill,AgentInterface,Part,Task,TaskStatus,TaskState
from causalops.knowledge.retrieval import MethodLibrary
from causalops.protocols.readonly_server import read_exported_facts

class ReviewerExecutor(AgentExecutor):
    def __init__(self,workspace):self.workspace=Path(workspace);self.library=MethodLibrary()
    async def cancel(self,context,event_queue):
        if context.task_id and context.context_id:await TaskUpdater(event_queue,context.task_id,context.context_id).cancel()
    async def execute(self,context:RequestContext,event_queue:EventQueue):
        if not context.task_id or not context.context_id:return
        await event_queue.enqueue_event(Task(id=context.task_id,context_id=context.context_id,status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),history=[context.message] if context.message else []))
        u=TaskUpdater(event_queue,context.task_id,context.context_id);await u.start_work()
        try:
            raw=context.get_user_input()
            if len(raw)>5000:raise ValueError('请求过长')
            p=json.loads(raw)
            if not isinstance(p,dict):raise ValueError('必须为对象')
            action=p.get('action')
            if action=='review_method':
                if set(p)-{'action','method','question'}:raise ValueError('不接收原始行、任意设计事实或额外字段')
                q=p.get('question','');m=p.get('method')
                if not isinstance(q,str) or re.search(r'sk-|@|\b\d{11,}\b|https?://',q):raise ValueError('请求疑似包含敏感信息或外部地址')
                evidence=self.library.search(q,method=m,k=3)
                result={'role':'independent_deterministic_method_reviewer','execution_performed':False,'approval_performed':False,'assumptions_verified':False,'retrieved':evidence,'next_action':'请将检查项与原设计对照，由使用者决定是否创建修订；此审阅不接受或批准草案。'}
            elif action=='read_evidence':
                if set(p)!={'action','run_id'}:raise ValueError('仅接受运行编号')
                result=read_exported_facts(self.workspace,p['run_id'])
            else:raise ValueError('仅开放review_method/read_evidence；不执行分析、修改或批准')
            await u.add_artifact(parts=[Part(text=json.dumps(result,ensure_ascii=False))],name='method-review-and-evidence',last_chunk=True);await u.complete()
        except (ValueError,TypeError) as exc:
            await u.reject(message=u.new_agent_message(parts=[Part(text=str(exc))]))

def create_app(workspace,port=8512):
    card=AgentCard(name='CausalOps Method Reviewer',description='Read-only, deterministic method review and explicit run evidence handoff; never executes or approves.',version='0.5.1',capabilities=AgentCapabilities(streaming=True,push_notifications=False),default_input_modes=['text/plain'],default_output_modes=['text/plain'],skills=[AgentSkill(id='review-method-evidence',name='方法依据与证据审阅',description='Curated source-backed method review only',tags=['causal-inference','read-only'])],supported_interfaces=[AgentInterface(protocol_binding='JSONRPC',protocol_version='1.0',url=f'http://127.0.0.1:{port}/a2a/jsonrpc')])
    handler=DefaultRequestHandler(agent_executor=ReviewerExecutor(workspace),task_store=InMemoryTaskStore(),agent_card=card)
    return Starlette(routes=create_agent_card_routes(card)+create_jsonrpc_routes(handler,rpc_url='/a2a/jsonrpc'))

async def request_review(payload,*,port=8512):
    """Whitelist loopback peer. No arbitrary URL or automatic model provider handoff."""
    import httpx
    from a2a.client import ClientFactory,ClientConfig
    from a2a.client.card_resolver import A2ACardResolver
    from a2a.types import SendMessageRequest,Message,Role
    if not isinstance(port,int) or port<1024 or port>65535:raise ValueError('非法本地端口')
    async with httpx.AsyncClient(timeout=30,trust_env=False) as http:
        card=await A2ACardResolver(http,f'http://127.0.0.1:{port}').get_agent_card()
        for interface in card.supported_interfaces:
            if interface.url!=f'http://127.0.0.1:{port}/a2a/jsonrpc':raise ValueError('拒绝不匹配的Agent端点')
        client=ClientFactory(ClientConfig(httpx_client=http,streaming=True,supported_protocol_bindings=['JSONRPC'])).create(card)
        events=[]
        async for event in client.send_message(SendMessageRequest(message=Message(message_id=str(uuid.uuid4()),role=Role.ROLE_USER,parts=[Part(text=json.dumps(payload,ensure_ascii=False))]))):
            events.append(MessageToDict(event,preserving_proto_field_name=True))
        return events

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--port',type=int,default=8512);a=p.parse_args()
    import uvicorn
    uvicorn.run(create_app(a.workspace,a.port),host='127.0.0.1',port=a.port,log_level='warning')
if __name__=='__main__':main()
