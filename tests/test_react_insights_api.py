"""HTTP boundary tests use original deterministic tools, never fake Run JSON."""
import pytest
from fastapi.testclient import TestClient
from test_react_insights import co,ready
from test_configurable_diagnostics import guards
from causalops.assistant.service import digest
from causalops.react_api import create_app
ORIGIN='http://127.0.0.1:8790'

@pytest.fixture
def api(co):
    chats,cid,t,w=ready(co,True)
    with TestClient(create_app(co.s),base_url=ORIGIN) as c:
        headers={'Origin':ORIGIN,'X-CausalOps-CSRF':c.get('/api/bootstrap').json()['csrf_token']}
        yield c,headers,cid,t,co,chats

def body(c,cid,key):
    r=c.get(f'/api/chats/{cid}/insights');assert r.status_code==200,r.text
    v=r.json();return dict(expected_binding_id=v['binding_id'],expected_context_sha=v['context_sha'],human_confirmed=True,request_key=key)

def generate(c,h,cid,key='generate'):
    r=c.post(f'/api/chats/{cid}/insights/generate',headers=h,json=body(c,cid,key));assert r.status_code==200,r.text
    return c.get(f'/api/chats/{cid}/insights/reports/'+r.json()['report_id']).json()

def test_explicit_creation_save_receipt_revision_and_execution_unchanged(api):
    c,h,cid,t,co,chats=api;prefix=f'/api/chats/{cid}/insights';before=guards(co)
    assert c.get(prefix).json()['report'] is None
    req=body(c,cid,'create');r=c.post(prefix+'/generate',headers=h,json=req)
    assert r.status_code==200 and c.post(prefix+'/generate',headers=h,json=req).json()==r.json()
    v=c.get(prefix).json();sg=next(x for x in v['report']['suggestions']if x['rule_id']=='PD-02')
    b={**body(c,cid,'defer'), 'report_id':v['report']['report_id'],'expected_report_sha':v['report_sha'],
       'decision_type':'deferred','reason':'仅解释描述性差异','suggestion_id':sg['suggestion_id'],'supersedes_id':None}
    saved=c.post(prefix+'/decisions',headers=h,json=b);assert saved.status_code==200,saved.text
    assert c.post(prefix+'/decisions',headers=h,json=b).json()==saved.json()
    assert c.get(prefix+'/receipts/defer').json()['receipt']['decision_id']==saved.json()['decision_id']
    b['reason']='相同key不同内容';assert c.post(prefix+'/decisions',headers=h,json=b).status_code==409
    v=c.get(prefix).json();assert len(v['decisions'])==1 and guards(co)==before
    assert not v['decisions'][0]['decision']['execution_authorized']
    assert c.get(prefix+'/reports/'+v['report']['report_id']+'/evidence/'+v['report']['quality']['findings'][0]['finding_id']).status_code==200

@pytest.mark.parametrize('change',[{'human_confirmed':False},{'execution_authorized':True},{'expected_context_sha':'0'*64},{'expected_binding_id':'0'*32}])
def test_forged_permissions_and_stale_scope_are_rejected(api,change):
    c,h,cid,t,co,_=api;b=body(c,cid,'bad');b.update(change)
    assert c.post(f'/api/chats/{cid}/insights/generate',headers=h,json=b).status_code in (409,422)
    assert c.get(f'/api/chats/{cid}/insights').json()['report'] is None

def test_origin_csrf_nonexistent_and_foreign_report(api):
    c,h,cid,t,co,chats=api;b=body(c,cid,'csrf')
    assert c.post(f'/api/chats/{cid}/insights/generate',headers={'Origin':ORIGIN},json=b).status_code==403
    assert c.post(f'/api/chats/{cid}/insights/generate',headers={**h,'Origin':'https://evil.example'},json=b).status_code==403
    assert c.get('/api/chats/'+'0'*32+'/insights').status_code==404
    v=generate(c,h,cid)
    other=chats.create('其他数据');sid=co.s.create_task(payload=b'x\n1\n2\n',name='other.csv');chats.bind(other.id,'assistant',sid)
    assert c.get(f'/api/chats/{other.id}/insights/reports/'+v['report']['report_id']).status_code==409
    bad={**body(c,other.id,'foreign'),'report_id':v['report']['report_id'],'expected_report_sha':v['report_sha'],'decision_type':'note','reason':'错误关联'}
    assert c.post(f'/api/chats/{other.id}/insights/decisions',headers=h,json=bad).status_code==409

def test_stale_report_cannot_save_even_with_current_context(api):
    c,h,cid,t,co,_=api;v=generate(c,h,cid)
    old=co.s.contracts.latest(t['session_id']);co.s.contracts.save(t['session_id'],{**old['body'],'notes':'后继合同'},expected_sha=old['sha'],human_confirmed=True)
    current=c.get(f'/api/chats/{cid}/insights/reports/'+v['report']['report_id']).json();assert not current['source_current']
    b={**body(c,cid,'stale'),'report_id':v['report']['report_id'],'expected_report_sha':v['report_sha'],'decision_type':'note','reason':'陈旧来源不能保存'}
    assert c.post(f'/api/chats/{cid}/insights/decisions',headers=h,json=b).status_code==409
    assert not c.get(f'/api/chats/{cid}/insights').json()['decisions']
