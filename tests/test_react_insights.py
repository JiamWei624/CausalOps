"""React diagnostics use real native evidence and never grant statistical execution."""
import pytest
from test_react_execution import co, prepared
from test_configurable_diagnostics import guards
from causalops.application.research_insights import ResearchInsights
from causalops.application.diagnostics.workbench import DiagnosticWorkbench
from causalops.assistant.service import digest
from causalops.general.service import DesignError


def ready(co, unknown=False):
    c,cid,t,_=prepared(co,unknown)
    co.approve(t['id'],expected_plan_sha=t['plan_sha'],human_confirmed=True)
    co.run(t['id'])
    return c,cid,t,ResearchInsights(c)


def operation(w,cid,key):
    v=w.context(cid)
    return dict(expected_binding_id=v['binding_id'],expected_context_sha=v['context_sha'],human_confirmed=True,request_key=key)


def generated(w,cid):
    result=w.generate(cid,**operation(w,cid,'generate'))
    return w.view(cid,result['report_id'])


def test_read_does_not_generate_report_and_whole_flow_preserves_execution(co):
    c,cid,t,w=ready(co);before=guards(co)
    assert w.view(cid)['report'] is None
    assert w.context(cid)['history']==[]
    v=generated(w,cid);r=v['report']
    assert r['results']['status']=='available' and len(r['results']['runs'])==2
    assert len(r['quality']['findings'])==6 and len(r['quality']['unimplemented_rules'])==8
    assert not r['suggestions'] and guards(co)==before
    request=operation(w,cid,'note')
    d=w.save_decision(cid,r['report_id'],decision_type='note',reason='仅解释当前窗口，不外推长期收益',expected_report_sha=digest(r),**request)
    assert w.save_decision(cid,r['report_id'],decision_type='note',reason='仅解释当前窗口，不外推长期收益',expected_report_sha=digest(r),**request)==d
    assert w.receipt(cid,'note')['decision_id']==d['decision_id']
    rows=w.view(cid,r['report_id'])['decisions']
    assert len(rows)==1 and not rows[0]['decision']['execution_authorized']
    assert guards(co)==before


def test_unknown_design_real_descriptive_report_and_append_revision(co):
    c,cid,t,w=ready(co,True);v=generated(w,cid);r=v['report'];before=guards(co)
    f={x['rule']['id']:x['status']for x in r['quality']['findings']}
    assert f['PD-02']=='unknown' and f['PD-07']=='not_applicable'
    assert r['results']['effect'] is None and len(r['results']['runs'])==1
    assert r['results']['descriptive']['interval'] is None
    s=next(s for s in r['suggestions'] if s['rule_id']=='PD-02')
    body=dict(suggestion_id=s['suggestion_id'],expected_report_sha=digest(r))
    d=w.save_decision(cid,r['report_id'],decision_type='deferred',reason='先补充分配资料',**body,**operation(w,cid,'defer'))
    new=w.save_decision(cid,r['report_id'],decision_type='rejected',reason='本轮不扩展因果结论',supersedes_id=d['decision_id'],**body,**operation(w,cid,'revise'))
    rows=w.view(cid,r['report_id'])['decisions']
    assert len(rows)==2 and rows[0]['superseded_by']==new['decision_id']
    assert rows[0]['decision']['reason']=='先补充分配资料' and guards(co)==before
    with pytest.raises(DesignError):w.save_decision(cid,r['report_id'],decision_type='accepted',reason='',**body,**operation(w,cid,'fork'))


def test_foreign_stale_report_and_duplicate_content_are_rejected(co):
    c,cid,t,w=ready(co,True);r=generated(w,cid)['report'];req=operation(w,cid,'old')
    other=c.create('other');c.bind(other.id,'automation_v2',t['id'])
    with pytest.raises(DesignError):w.generate(other.id,**req)
    report_id=r['report_id'];cfg=co.s.contracts.latest(t['session_id'])
    co.s.contracts.save(t['session_id'],{**cfg['body'],'notes':'新增来源版本'},expected_sha=cfg['sha'],human_confirmed=True)
    assert not w.view(cid,report_id)['source_current']
    with pytest.raises(DesignError):w.save_decision(cid,report_id,decision_type='note',reason='旧报告',expected_report_sha=digest(r),**operation(w,cid,'stale'))
    with pytest.raises(DesignError):w.generate(cid,**req)


def test_integrity_conflict_diagnostic_does_not_borrow_success(co):
    c,cid,t,w=ready(co);r=generated(w,cid)['report']
    with co.ws.connection() as db:db.execute("UPDATE automation_v2_steps SET output_sha=? WHERE task_id=? AND step_id='S05'",('0'*64,t['id']))
    v=w.generate(cid,**operation(w,cid,'conflict'))
    v=w.view(cid,v['report_id']);assert v['report']['results']['status']=='restricted'
    assert v['report']['results']['effect'] is None and not w.view(cid,r['report_id'])['source_current']


def test_preflight_without_run_and_real_historical_reminder(co):
    from causalops.application.chat_sessions import ChatService
    # Create an independent registered data session; no statistics or approval.
    sid=co.s.create_task(payload=b'arm,visited,person\n0,0,a\n0,1,b\n1,1,c\n1,0,d\n',name='pre.csv')
    body=dict(purpose='causal',metric_kind='binary');body.update(analysis_unit='参与者',entity='person',treatment='arm',outcome='visited',control_value='0',treated_value='1',metric_label='访问比例',metric_unit='概率',metric_window='一次观察')
    co.s.contracts.save(sid,body,human_confirmed=True)
    c=ChatService(co.s);chat=c.create();c.bind(chat.id,'assistant',sid);w=ResearchInsights(c);r=generated(w,chat.id)['report']
    sg=next(s for s in r['suggestions']if s['rule_id']=='PD-02')
    w.save_decision(chat.id,r['report_id'],decision_type='deferred',reason='等待设计依据',suggestion_id=sg['suggestion_id'],expected_report_sha=digest(r),**operation(w,chat.id,'decision'))
    latest=co.s.contracts.latest(sid);co.s.contracts.save(sid,{**latest['body'],'notes':'补充说明，分配事实仍未知'},expected_sha=latest['sha'],human_confirmed=True)
    v=w.generate(chat.id,**operation(w,chat.id,'next'));current=w.view(chat.id,v['report_id'])
    assert current['reminders'][0]['kind']=='still_open' and current['report']['results']['status']=='not_run'
