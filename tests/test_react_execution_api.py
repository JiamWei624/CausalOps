import pytest
from fastapi.testclient import TestClient
from test_react_execution import co,prepared,wait
from causalops.react_api import create_app
ORIGIN='http://127.0.0.1:8790'
@pytest.fixture
def api(co):
    chats,cid,t,w=prepared(co)
    with TestClient(create_app(co.s),base_url=ORIGIN) as c:
        h={'Origin':ORIGIN,'X-CausalOps-CSRF':c.get('/api/bootstrap').json()['csrf_token']}
        yield c,h,cid,co,t
def request(c,cid,key):
    v=c.get(f'/api/chats/{cid}/research');assert v.status_code==200,v.text
    r=v.json();return dict(expected_binding_id=r['binding_id'],task_id=r['task']['id'],expected_plan_sha=r['task']['plan_sha'],expected_review_sha=r['review_sha'],human_confirmed=True,request_key=key)

def test_http_approval_separate_dispatch_current_binding_and_report(api):
    c,h,cid,co,t=api;p=f'/api/chats/{cid}';b=request(c,cid,'approve')
    a=c.post(p+'/research/approve',headers=h,json=b);assert a.status_code==200,a.text
    assert co.task(t['id'])['status']=='approved' and all(x['status']=='pending' for x in co.steps(t['id']))
    assert c.post(p+'/research/approve',headers=h,json=b).json()==a.json()
    start=request(c,cid,'start');r=c.post(p+'/research/start',headers=h,json=start);assert r.status_code==200,r.text
    assert wait(co,t)['status']=='completed'
    view=c.get(p);assert view.status_code==200,view.text
    assert len(view.json()['study']['run_ids'])==2
    assert c.get(p+'/report').json()['manifest']['source_runs']==view.json()['study']['run_ids']
    assert c.post(p+'/research/start',headers=h,json=start).json()==r.json()

@pytest.mark.parametrize('bad',[{'human_confirmed':False},{'skip_gate':True},{'expected_review_sha':'0'*64},{'task_id':'f'*32}])
def test_illegal_operation_cannot_authorize(api,bad):
    c,h,cid,co,t=api;b=request(c,cid,'bad');b.update(bad)
    r=c.post(f'/api/chats/{cid}/research/approve',headers=h,json=b)
    assert r.status_code in (409,422),r.text
    assert co.task(t['id'])['status']=='candidate'

def test_operation_csrf_dedup_and_unapproved_dispatch(api):
    c,h,cid,co,t=api;b=request(c,cid,'start')
    assert c.post(f'/api/chats/{cid}/research/start',headers=h,json=b).status_code==409
    assert c.post(f'/api/chats/{cid}/research/approve',headers={**h,'Origin':'https://evil.example'},json=b).status_code==403
    b['request_key']='approved';assert c.post(f'/api/chats/{cid}/research/approve',headers=h,json=b).status_code==200
    b['expected_review_sha']='0'*64
    assert c.post(f'/api/chats/{cid}/research/approve',headers=h,json=b).status_code==409

def test_foreign_chat_and_cancel_terminal(api):
    c,h,cid,co,t=api;b=request(c,cid,'cancel')
    other=c.post('/api/chats',headers=h,json={'title':'其他会话','request_key':'other'}).json()['id']
    assert c.post(f'/api/chats/{other}/research/cancel',headers=h,json=b).status_code==409
    assert c.post(f'/api/chats/{cid}/research/cancel',headers=h,json=b).status_code==200
    assert c.post(f'/api/chats/{cid}/research/resume',headers=h,json=request(c,cid,'resume')).status_code==409

def test_publishing_is_distinct_from_damaged_evidence(api,monkeypatch):
    from causalops.application import automation_results
    c,h,cid,co,t=api
    def busy(*args):raise automation_results.SnapshotUpdating('受控发布中，未返回混合快照')
    monkeypatch.setattr(automation_results,'snapshot',busy)
    r=c.get(f'/api/chats/{cid}/research')
    assert r.status_code==503 and r.json()['error']['code']=='research_updating'
    assert 'report' not in r.json() and co.task(t['id'])['status']=='candidate'
