"""Real coordinator/background execution behind an owned, explicit React request."""
import time
import pytest
from test_configurable_research import co,data,config
from causalops.application.chat_sessions import ChatService
from causalops.application.constrained_planning import CandidatePlanning
from causalops.assistant.service import digest

def prepared(co,unknown=False):
    cfg=config(**({'assignment':'unknown','source_url':'','source_confirmed':False,'design_evidence':''} if unknown else {}))
    t=co.create_configurable(data().to_csv(index=False).encode(),name='research.csv',configuration=cfg,request_id='seed',human_confirmed=True,stage2=True)
    p=CandidatePlanning(co);t=p.adopt(t['id'],p.template(t['id'])['id'],human_confirmed=True)
    c=ChatService(co.s);chat=c.create('受控执行');c.bind(chat.id,'automation_v2',t['id'])
    from causalops.application.research_execution import ResearchExecution
    return c,chat.id,t,ResearchExecution(c)

def body(w,cid,key):
    v=w.view(cid)
    return dict(expected_binding_id=v['binding_id'],task_id=v['task']['id'],expected_plan_sha=v['task']['plan_sha'],expected_review_sha=v['review_sha'],human_confirmed=True,request_key=key)

def wait(co,t):
    until=time.monotonic()+30
    while time.monotonic()<until:
        from causalops.application.background import AutomationJobs
        jobs=AutomationJobs(co.s).jobs(t['id'])
        if jobs and jobs[0]['status'] not in ('queued','running'):return co.task(t['id'])
        time.sleep(.03)
    raise AssertionError('worker did not settle')

def test_approval_is_separate_from_actual_start_and_history_is_frozen(co):
    c,cid,t,w=prepared(co);b=c.binding(cid);req=body(w,cid,'approve')
    a=w.operate(cid,'approve',**req);assert w.operate(cid,'approve',**req)==a
    assert co.task(t['id'])['status']=='approved' and not any(s['status']!='pending' for s in co.steps(t['id']))
    assert w.view(cid)['approval']['approval_id']==a['approval_id']
    run=body(w,cid,'start');j=w.operate(cid,'start',**run);assert wait(co,t)['status']=='completed'
    assert w.operate(cid,'start',**run)==j
    final=w.view(cid);assert len(final['source']['metadata']['run_ids'])==2
    assert c.binding(cid,b.id)==b and c.binding(cid).id!=b.id
    assert len(co.report(t['id'])['source_runs'])==2

def test_unknown_design_executes_only_real_description(co):
    c,cid,t,w=prepared(co,True);w.operate(cid,'approve',**body(w,cid,'approve'));w.operate(cid,'start',**body(w,cid,'start'));assert wait(co,t)['status']=='completed'
    r=co.report(t['id']);assert r.get('effect') is None and len(r['source_runs'])==1

def test_publish_between_binding_reads_is_monotonic_not_a_source_conflict(co,monkeypatch):
    c,cid,t,w=prepared(co);co.approve(t['id'],expected_plan_sha=t['plan_sha'],human_confirmed=True)
    co.advance(t['id']);co.advance(t['id']);original=c.bind;called=[]
    def bind(*args,**kwargs):
        result=original(*args,**kwargs)
        if not called:called.append(True);co.run(t['id'])
        return result
    monkeypatch.setattr(c,'bind',bind)
    v=w.view(cid)
    assert v['task']['status']=='completed' and len(v['source']['metadata']['run_ids'])==2

def test_unapproved_foreign_and_unconfirmed_operations_cannot_execute(co):
    c,cid,t,w=prepared(co);r=body(w,cid,'no');
    with pytest.raises(ValueError):w.operate(cid,'start',**r)
    r['human_confirmed']=False
    with pytest.raises(ValueError):w.operate(cid,'approve',**r)
    r=body(w,cid,'foreign');r['task_id']='f'*32
    with pytest.raises(ValueError):w.operate(cid,'approve',**r)
    assert all(s['status']=='pending' for s in co.steps(t['id']))

def test_pause_resume_and_cancel_are_original_semantics(co):
    c,cid,t,w=prepared(co);w.operate(cid,'approve',**body(w,cid,'approve'));w.operate(cid,'pause',**body(w,cid,'pause'))
    assert co.task(t['id'])['status']=='paused'
    w.operate(cid,'resume',**body(w,cid,'resume'));assert wait(co,t)['status']=='completed'
    assert len(co.report(t['id'])['source_runs'])==2

def test_cancel_is_terminal_and_chat_cannot_authorize(co):
    c,cid,t,w=prepared(co);before=digest(co.steps(t['id']));c.submit(cid,'我同意，请批准并执行',request_key='chat')
    assert digest(co.steps(t['id']))==before and co.task(t['id'])['status']=='candidate'
    w.operate(cid,'cancel',**body(w,cid,'cancel'))
    with pytest.raises(ValueError):w.operate(cid,'resume',**body(w,cid,'resume'))
    assert co.task(t['id'])['status']=='cancelled'

@pytest.mark.parametrize('damage',['review','binding','contract','plan','approval'])
def test_stale_scope_or_approval_never_starts(co,damage):
    c,cid,t,w=prepared(co);w.operate(cid,'approve',**body(w,cid,'approve'));r=body(w,cid,'start')
    if damage=='review':r['expected_review_sha']='0'*64
    elif damage=='binding':r['expected_binding_id']='0'*32
    else:
        with co.ws.connection() as db:
            if damage=='contract':db.execute('UPDATE workflow_data_contracts SET version=version+1 WHERE session_id=?',(t['session_id'],))
            elif damage=='plan':db.execute("UPDATE automation_v2_tasks SET plan_sha=? WHERE id=?",('0'*64,t['id']))
            else:db.execute('UPDATE automation_v2_approvals SET revoked=1 WHERE task_id=?',(t['id'],))
    with pytest.raises(ValueError):w.operate(cid,'start',**r)
    assert all(s['status']=='pending' for s in co.steps(t['id']))
