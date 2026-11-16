"""Owned React facade over existing diagnostics and append-only user decisions.

This adapter never calls approval, dispatch, or statistical tools. A frozen chat
binding identifies the subject even when statistical-source validation fails:
diagnostics must be able to explain that conflict rather than borrow a result.
"""
from dataclasses import asdict
import json
from causalops.assistant.service import digest
from causalops.general.service import DesignError
from .locking import flow_lock
from .diagnostics.workbench import DiagnosticWorkbench
from .diagnostics.decisions import ResearchDecisionService
from .diagnostics.decision_contracts import TYPE_LABELS


class ResearchInsights:
    KIND = 'react_insight_receipt'

    def __init__(self, chats):
        self.c = chats
        self.s = chats.s
        self.w = DiagnosticWorkbench(self.s)
        self.m = ResearchDecisionService(self.w)

    def context(self, cid):
        self.c.session(cid)
        b = self.c.binding(cid)
        if not b:
            raise DesignError('请先明确关联已登记的数据或研究任务。')
        mode = 'post_run' if b.domain == 'automation_v2' else 'preflight'
        item = self.w.subject(mode, b.subject_id)
        if item['session_id'] != b.assistant_session_id:
            raise DesignError('会话与研究任务归属冲突，未关联其他任务。')
        native = dict(binding_sha=b.sha, data=self.s.data_binding(item['session_id']),
                      contract=self.s.contracts.ref(item['session_id']))
        if mode == 'post_run':
            co = self.s.automation_v2()
            task = co.task(item['id'])
            native.update(plan=task['plan'], plan_sha=task['plan_sha'],
                          steps=[{k:row[k] for k in ('step_id','status','output_sha')}
                                 for row in co.steps(item['id'])])
        return dict(chat_id=cid,binding_id=b.id, context_sha=digest(native), mode=mode,
                    subject_id=item['id'], session_id=item['session_id'],
                    title=b.metadata['title'], history=self.w.history(mode,item['id']),
                    capabilities=self.w.reports.diagnostics.capabilities(),
                    decision_types=TYPE_LABELS)

    def view(self, cid, report_id=None):
        ctx = self.context(cid)
        mode, subject = ctx['mode'], ctx['subject_id']
        rows = self.m.history(mode, subject)
        identifier = report_id or (ctx['history'][0]['id'] if ctx['history'] else None)
        view = self.w.load(mode,subject,identifier) if identifier else None
        report = view.report if view else None
        return dict(**ctx, report=report.model_dump(mode='json') if report else None,
                    report_sha=digest(report.model_dump(mode='json')) if report else None,
                    source_current=view.source_current if view else None,
                    source_error=view.source_error if view else None,
                    decisions=[dict(decision=x.decision.model_dump(mode='json'),
                                    origin_verified=x.origin_verified,origin_error=x.origin_error,
                                    superseded_by=x.superseded_by,
                                    revisable_for=([s.suggestion_id for s in report.suggestions
                                                    if self.m.can_supersede(x,report,s.suggestion_id)]
                                                   + ([None] if self.m.can_supersede(x,report,None) else []))
                                                   if report and view.source_current else []) for x in rows],
                    reminders=[asdict(x) for x in self.m.reminders(mode,subject,identifier)] if report else [])

    def evidence(self,cid,report_id,finding_id):
        ctx=self.context(cid)
        return self.w.evidence(ctx['mode'],ctx['subject_id'],report_id,finding_id)

    def _receipt(self,cid,key,request=None):
        self.c.validate_request_key(key)
        with self.s.ws.connection() as db:
            rows=db.execute("SELECT id,body FROM assistant_events WHERE kind=? AND json_extract(body,'$.chat_id')=? AND json_extract(body,'$.request_key')=?",
                            (self.KIND,cid,key)).fetchall()
        if len(rows)>1:raise DesignError('诊断操作收据不唯一，请核查历史，未重复写入。')
        if not rows:return None
        identifier,raw=rows[0]
        try:r=json.loads(raw)
        except ValueError:raise DesignError('诊断操作收据损坏。')
        if r.get('schema')!='react-insight-receipt-v1' or r.get('sha')!=digest({k:v for k,v in r.items() if k!='sha'}):
            raise DesignError('诊断操作收据内容哈希冲突。')
        if request is not None and digest(request)!=r['request_sha']:
            raise DesignError('相同请求标识已绑定其他内容，未覆盖或重放操作。')
        return dict(**r['result'],receipt_ref=identifier)

    def receipt(self,cid,key):
        ctx=self.context(cid);r=self._receipt(cid,key)
        if r and r['subject_id']!=ctx['subject_id']:
            raise DesignError('原操作收据不属于当前关联研究。')
        return r

    def _operate(self,cid,action,fields,*,expected_binding_id,expected_context_sha,human_confirmed,request_key):
        if human_confirmed is not True:raise DesignError('需要用户明确提交；聊天文字不会保存诊断或研究决定。')
        request=dict(action=action,**fields,expected_binding_id=expected_binding_id,
                     expected_context_sha=expected_context_sha,human_confirmed=True)
        self.c.validate_request_key(request_key)
        with flow_lock(self.s.ws.root,'react-insights-'+cid):
            ctx=self.context(cid)
            old=self._receipt(cid,request_key,request)
            if old:
                if old['subject_id']!=ctx['subject_id']:raise DesignError('操作收据与当前研究不一致。')
                return old
            if ctx['binding_id']!=expected_binding_id or ctx['context_sha']!=expected_context_sha:
                raise DesignError('数据、合同、计划、运行或会话绑定已变化；请重新核查后明确提交。')
            mode,subject=ctx['mode'],ctx['subject_id']
            if action=='generate':
                r=self.w.create(mode,subject)
                result=dict(report_id=r.report_id,subject_id=subject)
            else:
                v=self.w.load(mode,subject,fields['report_id'])
                if digest(v.report.model_dump(mode='json'))!=fields['expected_report_sha']:
                    raise DesignError('已查看的诊断报告版本或内容哈希不一致。')
                d=self.m.save(mode,subject,fields['report_id'],fields['decision_type'],fields['reason'],
                              suggestion_id=fields['suggestion_id'],supersedes_id=fields['supersedes_id'],human_confirmed=True)
                result=dict(report_id=d.report_id,decision_id=d.decision_id,subject_id=subject,execution_authorized=False)
            record=dict(schema='react-insight-receipt-v1',chat_id=cid,request_key=request_key,request_sha=digest(request),result=result)
            record['sha']=digest(record)
            self.c.a.event(ctx['session_id'],self.KIND,record)
            return self._receipt(cid,request_key,request)

    def generate(self,cid,**request):
        return self._operate(cid,'generate',{},**request)

    def save_decision(self,cid,report_id,*,decision_type,reason,expected_report_sha,suggestion_id=None,supersedes_id=None,**request):
        fields=dict(report_id=report_id,decision_type=decision_type,reason=reason,
                    expected_report_sha=expected_report_sha,suggestion_id=suggestion_id,supersedes_id=supersedes_id)
        return self._operate(cid,'decision',fields,**request)
