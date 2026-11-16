"""Owned React adapter over original approval, worker, control and report services."""
from __future__ import annotations
import json
from causalops.assistant.service import digest
from causalops.general.service import DesignError
from .chat_sessions import ChatService
from .background import AutomationJobs
from .automation_budget import BudgetLedger
from .locking import flow_lock
from .automation_results import SnapshotUpdating

class ResearchExecution:
    KIND='react_execution_receipt'
    ANCHOR=('domain','subject_id','assistant_session_id','title','data','contract_ref','plan_refs','scope')
    def __init__(self,chats:ChatService):
        self.c=chats;self.s=chats.s;self.co=self.s.automation_v2();self.jobs=AutomationJobs(self.s)

    def resolve(self,cid):
        """Append a current binding ONLY for monotonic results of the same plan."""
        for _ in range(5):
            b=self.c.binding(cid)
            if not b or b.domain!='automation_v2':return self.c.view(cid)
            source=self.c.resolve_research(b.domain,b.subject_id);m=source['metadata'];old=b.metadata
            if any(old[k]!=m[k] for k in self.ANCHOR):raise DesignError('当前研究数据、合同或计划已经变化；旧批准不能用于新范围。')
            if m['run_ids'][:len(old['run_ids'])]!=old['run_ids'] or (old['report_sha'] and old['report_sha']!=m['report_sha']):
                raise DesignError('运行来源不再兼容原绑定；未用其他研究补齐。')
            if digest(m)==b.sha:return source
            # Publication can advance between these reads. Append only, then
            # re-read a coherent projection; never force the old run list onto it.
            newer=self.c.bind(cid,b.domain,b.subject_id)
            if any(newer.metadata[k]!=old[k] for k in self.ANCHOR):raise DesignError('读取期间研究范围变化，请重新核对。')
        raise SnapshotUpdating('研究结果正在发布，请稍后刷新；没有展示混合快照。')

    def view(self,cid):
        source=self.resolve(cid);v=source['view']
        if not v:raise DesignError('当前关联的是数据任务；请先生成并采纳正式待审方案。')
        t=v['task'];p=t['plan'];jobs=self.jobs.reconcile(t['id']);active=any(j['status'] in ('queued','running') for j in jobs)
        approval=None
        try:approval=self.co.approval(t['id'])
        except DesignError:pass
        review_sha=digest(dict(task=t['id'],plan_sha=t['plan_sha'],data=p['data'],contract=p['contract_ref'],scope=p['scope'],source=p['source_sha'],policy=BudgetLedger.POLICY))
        adopted=p.get('schema_version')!='configurable-research-stage2' or bool(p.get('candidate_ref'))
        valid=not v['binding_error'] and not v['errors']
        # Candidate snapshots have no approval, as required; later states require it.
        permissions=dict(approve=valid and adopted and t['status']=='candidate',start=valid and bool(approval) and t['status']=='approved' and not active,
            pause=t['status'] in ('approved','running'),cancel=t['status'] not in ('completed','cancelled'),
            resume=bool(approval) and not active and t['status'] in ('paused','interrupted','running','pause_requested'))
        return dict(schema_version='react-research-execution-v1',binding_id=self.c.binding(cid).id,review_sha=review_sha,source=source,
            **v,jobs=jobs,active=active,approval=approval,permissions=permissions,review_requirement=None if adopted else '先显式采纳候选，再进行正式人工审核。')

    def _receipt(self,cid,key,request):
        with self.s.ws.connection() as db:rows=db.execute("SELECT id,body FROM assistant_events WHERE kind=? AND json_extract(body,'$.chat_id')=? AND json_extract(body,'$.request_key')=?",(self.KIND,cid,key)).fetchall()
        if len(rows)>1:raise DesignError('操作收据不唯一，未重复派发。')
        if not rows:return None
        ref,raw=rows[0]
        try:r=json.loads(raw)
        except ValueError:raise DesignError('操作收据损坏，未重复派发。')
        if r.get('schema')!='react-execution-1' or r.get('sha')!=digest({k:v for k,v in r.items() if k!='sha'}):raise DesignError('操作收据哈希不一致。')
        if r['request_sha']!=digest(request):raise DesignError('相同操作标识已绑定其他内容，未覆盖或重复处理。')
        return dict(**r['result'],receipt_ref=ref)

    def operate(self,cid,action,*,expected_binding_id,task_id,expected_plan_sha,expected_review_sha,human_confirmed,request_key):
        if action not in ('approve','start','pause','cancel','resume') or human_confirmed is not True:raise DesignError('需要独立的明确操作；聊天文字不授予研究执行权限。')
        self.c.validate_identity(task_id);self.c.validate_request_key(request_key);self.c.session(cid)
        request=dict(action=action,expected_binding_id=expected_binding_id,task_id=task_id,expected_plan_sha=expected_plan_sha,expected_review_sha=expected_review_sha,human_confirmed=True)
        with flow_lock(self.s.ws.root,'react-execution-'+cid):
            old=self._receipt(cid,request_key,request)
            if old:return old
            b=self.c.binding(cid)
            expected=self.c.binding(cid,expected_binding_id)
            if (not b or not expected or b.domain!='automation_v2' or b.subject_id!=task_id
                or any(expected.metadata[k]!=b.metadata[k] for k in self.ANCHOR)):
                raise DesignError('操作不属于当前明确关联的研究或研究范围已变化。')
            t=self.co.task(task_id)
            if t['plan_sha']!=expected_plan_sha:raise DesignError('已查看的计划版本发生变化。')
            v=self.view(cid)
            if v['review_sha']!=expected_review_sha:raise DesignError('数据、研究合同、计划或预算政策与审核快照不一致。')
            result=dict(action=action,task_id=task_id,plan_sha=t['plan_sha'])
            if action=='approve':
                if not v['permissions']['approve'] and not v['approval']:raise DesignError(v['review_requirement'] or v['binding_error'] or '当前状态不能批准。')
                r=self.co.approve(task_id,expected_plan_sha=expected_plan_sha,human_confirmed=True);result['approval_id']=r['approval_id']
            elif action in ('start','resume'):
                self.co.approval(task_id)
                if t['status']=='completed':result['already_completed']=True
                else:
                    if action=='resume':self.co.user_event(task_id,'user_restore')
                    j=self.jobs.submit_task(task_id,resume=action=='resume');result['job_id']=j['id']
            else:
                stopped=getattr(self.co,action)(task_id,human_confirmed=True);result['status']=stopped['status']
            record=dict(schema='react-execution-1',chat_id=cid,request_key=request_key,request_sha=digest(request),result=result)
            record['sha']=digest(record);self.c.a.event(t['session_id'],self.KIND,record)
            return self._receipt(cid,request_key,request)
