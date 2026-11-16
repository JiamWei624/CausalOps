"""Read-only, task-scoped diagnostic/decision projections. Never creates either."""
from .diagnostics.workbench import DiagnosticWorkbench
from .diagnostics.decisions import ResearchDecisionService
from .diagnostics.decision_contracts import TYPE_LABELS


def artifacts(chats,chat_id,*,report_id=None):
    source=chats.view(chat_id);meta=source['metadata']
    result=dict(diagnostic=None,decisions=dict(count=0,history_count=0,execution_authorized=False))
    if not meta:return result
    mode='post_run' if meta['domain']=='automation_v2' else 'preflight'
    subject=meta['subject_id'] if mode=='post_run' else meta['assistant_session_id']
    w=DiagnosticWorkbench(chats.s);history=w.history(mode,subject)
    if report_id and report_id not in {x['id'] for x in history}:
        raise ValueError('所选诊断报告不属于当前研究，未使用其他版本替代。')
    if not history:return result
    selected=report_id or history[0]['id'];view=w.load(mode,subject,selected);r=view.report
    result['diagnostic']=dict(id=r.report_id,version=r.version,assessment_id=r.assessment_id,
        source_current=view.source_current,error=view.source_error,suggestions=len(r.suggestions),
        states=[dict(rule=x.rule.id,status=x.status) for x in r.quality.findings])
    rows=ResearchDecisionService(w).history(mode,subject)
    valid=[x for x in rows if x.origin_verified]
    current=[x for x in valid if x.decision.report_id==selected and not x.superseded_by]
    result['decisions'].update(count=len(current),history_count=len(valid))
    if current:
        d=current[-1].decision
        result['decisions'].update(latest_id=d.decision_id,kind=TYPE_LABELS[d.decision_type],report_id=d.report_id)
    return result
