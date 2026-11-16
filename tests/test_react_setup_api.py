"""Real HTTP-to-domain configuration; never bypass approval or run tools."""
import pytest
from fastapi.testclient import TestClient
from test_configurable_research import co,data,config
from test_research_setup import counts
from causalops.react_api import create_app

ORIGIN='http://127.0.0.1:8790'

@pytest.fixture
def api(co):
    with TestClient(create_app(co.s),base_url=ORIGIN) as c:
        token=c.get('/api/bootstrap').json()['csrf_token'];h={'Origin':ORIGIN,'X-CausalOps-CSRF':token}
        cid=c.post('/api/chats',headers=h,json={'title':'React合同接口','request_key':'chat'}).json()['id']
        assert c.post(f'/api/chats/{cid}/attachment',headers={**h,'Content-Type':'application/octet-stream','X-Filename':'research.csv','X-Expected-Binding':'none','X-Request-Key':'file'},content=data().to_csv(index=False).encode()).status_code==200
        yield c,h,cid,co

def confirm(c,h,cid,cfg=None,key='contract'):
    v=c.get(f'/api/chats/{cid}/setup').json()
    body=dict(configuration=cfg or config(),expected_binding_id=v['binding_id'],expected_data_sha=v['data']['frame_sha'],expected_contract_sha=(v['contract'] or {}).get('sha'),human_confirmed=True,request_key=key)
    r=c.post(f'/api/chats/{cid}/contract',headers=h,json=body);assert r.status_code==200,r.text
    return r.json(),body

def compile(c,h,cid):
    v=c.get(f'/api/chats/{cid}/setup').json();body=dict(configuration_ref=v['configuration']['id'],expected_binding_id=v['binding_id'],request_key='candidate')
    r=c.post(f'/api/chats/{cid}/candidates',headers=h,json=body);assert r.status_code==200,r.text
    return r.json(),body

def test_http_contract_proposal_adoption_no_approval_or_run(api):
    c,h,cid,co=api;before=counts(co);r,body=confirm(c,h,cid)
    assert counts(co)==before
    assert c.post(f'/api/chats/{cid}/contract',headers=h,json=body).json()==r
    p,body=compile(c,h,cid)
    assert c.post(f'/api/chats/{cid}/candidates',headers=h,json=body).json()==p
    assert len(p['candidate']['candidate']['steps'])==5
    view=c.get(f'/api/chats/{cid}/setup').json();accept={'expected_binding_id':view['binding_id'],'human_confirmed':True,'request_key':'adoption'}
    a=c.post(f'/api/chats/{cid}/candidates/{p["id"]}/adopt',headers=h,json=accept);assert a.status_code==200,a.text
    assert c.post(f'/api/chats/{cid}/candidates/{p["id"]}/adopt',headers=h,json=accept).json()==a.json()
    assert c.get(f'/api/chats/{cid}/setup').json()['phase']=='adopted'
    study=c.get(f'/api/chats/{cid}').json()['study'];assert study['approval'] is None and study['run_ids']==[] and study['status']=='candidate'
    assert 'route=review' in study['links']['review']
    after=counts(co)
    assert all(before[t]==after[t] for t in ('analysis_runs','exploration_runs','automation_v2_approvals'))

def test_unknown_design_uses_only_description(api):
    c,h,cid,co=api
    confirm(c,h,cid,config(assignment='unknown',source_url='',design_evidence='',source_confirmed=False))
    p,_=compile(c,h,cid);value=p['candidate']['candidate']
    assert value['research_type']=='descriptive_binary' and len(value['steps'])==4
    assert all(x['method']!='ab_test' for x in value['steps'])
    assert counts(co)['analysis_runs']==counts(co)['exploration_runs']==0

@pytest.mark.parametrize('change',[{'approved':True},{'human_confirmed':False},{'configuration':config(source_confirmed=False)},{'configuration':config(treatment='__missing__')}])
def test_unconfirmed_illegal_authority_and_bad_fields_rejected(api,change):
    c,h,cid,co=api;v=c.get(f'/api/chats/{cid}/setup').json();before=counts(co)
    body=dict(configuration=config(),expected_binding_id=v['binding_id'],expected_data_sha=v['data']['frame_sha'],expected_contract_sha=None,human_confirmed=True,request_key='illegal')
    body.update(change);r=c.post(f'/api/chats/{cid}/contract',headers=h,json=body)
    assert r.status_code in (409,422),r.text
    assert counts(co)==before and co.s.contracts.latest(v['session_id']) is None

def test_stale_contract_candidate_and_foreign_chat_are_rejected(api):
    c,h,cid,co=api;r,_=confirm(c,h,cid);p,_=compile(c,h,cid)
    other=c.post('/api/chats',headers=h,json={'title':'其他会话','request_key':'other'}).json()['id']
    assert c.get(f'/api/chats/{other}/candidates/{p["id"]}').status_code==409
    newer,_=confirm(c,h,cid,config(window='重新确认的观察窗口'),key='newer');assert newer['contract_ref']['version']==2
    assert c.get(f'/api/chats/{cid}/candidates/{p["id"]}').json()['source_current'] is False
    v=c.get(f'/api/chats/{cid}/setup').json()
    assert c.post(f'/api/chats/{cid}/candidates/{p["id"]}/adopt',headers=h,json={'expected_binding_id':v['binding_id'],'human_confirmed':True,'request_key':'stale'}).status_code==409
    assert counts(co)['automation_v2_approvals']==0

def test_request_source_hash_and_receipt_integrity(api):
    c,h,cid,co=api;v=c.get(f'/api/chats/{cid}/setup').json();body=dict(configuration=config(),expected_binding_id=v['binding_id'],expected_data_sha='0'*64,expected_contract_sha=None,human_confirmed=True,request_key='hash')
    assert c.post(f'/api/chats/{cid}/contract',headers=h,json=body).status_code==409
    body['expected_data_sha']=v['data']['frame_sha']
    assert c.post(f'/api/chats/{cid}/contract',headers={**h,'Origin':'https://evil.example'},json=body).status_code==403
    r,_=confirm(c,h,cid)
    with co.ws.connection() as db:db.execute("UPDATE assistant_events SET body=json_set(body,'$.checksum',?) WHERE id=?",('0'*64,r['id']))
    assert c.get(f'/api/chats/{cid}/setup').status_code==409
    assert counts(co)['analysis_runs']==counts(co)['automation_v2_approvals']==0

def test_invalid_candidate_identity_has_structured_rejection(api):
    c,h,cid,co=api
    assert c.get(f'/api/chats/{cid}/candidates/not-an-identity').status_code==422
    assert c.post(f'/api/chats/{cid}/candidates/not-an-identity/adopt',headers=h,json={'expected_binding_id':c.get(f'/api/chats/{cid}/setup').json()['binding_id'],'human_confirmed':True,'request_key':'invalid-id'}).status_code==422
    assert counts(co)['automation_v2_tasks']==0
