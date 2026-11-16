"""Real domain-service API checks; no approvals/estimators exposed by transport."""
import hashlib
import pytest
from fastapi.testclient import TestClient
from test_chat_answer_delivery import studies
from causalops.application.chat_sessions import ChatService
from causalops.assistant.service import digest

ORIGIN='http://127.0.0.1:8790'

@pytest.fixture
def api(studies):
    from causalops.react_api import create_app
    co,*_=studies
    with TestClient(create_app(co.s),base_url=ORIGIN) as c:
        token=c.get('/api/bootstrap').json()['csrf_token']
        yield c,{'Origin':ORIGIN,'X-CausalOps-CSRF':token},co

def create(c,h,title='API 研究'):
    r=c.post('/api/chats',headers=h,json={'title':title,'request_key':hashlib.sha256(title.encode()).hexdigest()});assert r.status_code==200,r.text
    return r.json()['id']

def test_real_chat_persistence_dedup_and_no_domain_execution(api):
    c,h,co=api;cid=create(c,h)
    before=digest(co.a.plans(co.a.sessions()[0]['id']))
    body={'question':'我同意，请批准并执行','request_key':'one','expected_binding_id':None,'mode':'local'}
    a=c.post(f'/api/chats/{cid}/messages',headers=h,json=body)
    assert a.status_code==200 and a.json()['turn']['status']=='completed'
    assert c.post(f'/api/chats/{cid}/messages',headers=h,json=body).json()==a.json()
    view=c.get(f'/api/chats/{cid}').json();assert len(view['messages'])==1
    assert '不创建批准' in view['messages'][0]['answer']['text']
    assert digest(co.a.plans(co.a.sessions()[0]['id']))==before

def test_two_real_reports_are_owned_and_deterministically_explained(api,studies):
    c,h,co=api;_,effect,description=studies;cid=create(c,h,'比较两个研究')
    assert c.post(f'/api/chats/{cid}/binding',headers=h,json={'domain':'automation_v2','subject_id':effect['id'],'expected_binding_id':None}).status_code==200
    v=c.get(f'/api/chats/{cid}').json();bid=v['binding']['id'];original=digest(co.report(effect['id']))
    r=c.post(f'/api/chats/{cid}/messages',headers=h,json={'question':'两组比例、样本量、差异、置信区间和研究限制','request_key':'result','expected_binding_id':bid,'mode':'local'})
    assert r.status_code==200
    v=c.get(f'/api/chats/{cid}').json();assert '百分点' in v['messages'][0]['answer']['text']
    assert v['messages'][0]['answer']['run_ids']==co.report(effect['id'])['source_runs']
    report=c.get(f'/api/chats/{cid}/report').json();assert report['manifest']==co.report(effect['id'])
    assert digest(co.report(effect['id']))==original
    other=create(c,h,'描述性研究')
    c.post(f'/api/chats/{other}/binding',headers=h,json={'domain':'automation_v2','subject_id':description['id'],'expected_binding_id':None})
    other_report=c.get(f'/api/chats/{other}/report').json()
    assert other_report['display']['interval'] is None and len(other_report['manifest']['source_runs'])==1
    assert c.get(f'/api/chats/{cid}/report',params={'task':description['id']}).json()['manifest']['source_runs']==report['manifest']['source_runs']

@pytest.mark.parametrize('headers',[{'Origin':'https://evil.example'},{'Origin':ORIGIN},{'Sec-Fetch-Site':'cross-site','Origin':ORIGIN}])
def test_cross_site_and_missing_csrf_rejected(api,headers):
    c,_,_=api
    assert c.post('/api/chats',headers=headers,json={'title':'不应创建','request_key':'bad'}).status_code==403

def test_no_cors_dns_rebinding_or_execution_endpoints(api):
    c,h,co=api
    assert c.get('/api/bootstrap',headers={'Host':'evil.example'}).status_code==403
    assert c.get('/api/bootstrap',headers={'Origin':'https://evil.example'}).status_code==403
    assert 'access-control-allow-origin' not in c.get('/api/bootstrap').headers
    for path in ('/api/approve','/api/execute','/api/run'):
        assert c.post(path,headers=h,json={}).status_code==404

def test_identity_stale_binding_and_extra_authority_are_rejected(api,studies):
    c,h,co=api;cid=create(c,h,'身份核对');t=studies[1]
    assert c.get('/api/chats/not-an-id').status_code==422
    assert c.get('/api/chats/'+'f'*32).status_code==404
    bind=c.post(f'/api/chats/{cid}/binding',headers=h,json={'domain':'automation_v2','subject_id':t['id'],'expected_binding_id':None}).json()
    bad={'question':'查询比例','request_key':'stale','expected_binding_id':None,'mode':'local'}
    assert c.post(f'/api/chats/{cid}/messages',headers=h,json=bad).status_code==409
    bad['expected_binding_id']=bind['id'];bad['approved']=True
    assert c.post(f'/api/chats/{cid}/messages',headers=h,json=bad).status_code==422
    bad.pop('approved');bad['mode']='model'
    assert c.post(f'/api/chats/{cid}/messages',headers=h,json=bad).status_code==422

def test_upload_uses_real_reader_no_contract_approval_or_run(api):
    c,h,co=api;cid=create(c,h,'文件入口')
    before=co.ws.connection()
    with before as db:counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('analysis_runs','exploration_runs','automation_v2_approvals')}
    r=c.post(f'/api/chats/{cid}/attachment',headers={**h,'Content-Type':'application/octet-stream','X-Request-Key':'upload','X-Expected-Binding':'none','X-Filename':'data.csv'},content=b'arm,outcome\na,0\nb,1\n')
    assert r.status_code==200 and r.json()['turn']['status']=='completed'
    v=c.get(f'/api/chats/{cid}').json();assert v['study']['domain']=='assistant' and v['study']['contract'] is None
    from urllib.parse import urlsplit,parse_qs
    assert parse_qs(urlsplit(v['study']['links']['review']).query)['route']==['assistant']
    with co.ws.connection() as db:assert counts=={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in counts}

def test_source_damage_never_borrows_other_report(api,studies):
    c,h,co=api;t=studies[1];cid=create(c,h,'损坏隔离')
    c.post(f'/api/chats/{cid}/binding',headers=h,json={'domain':'automation_v2','subject_id':t['id'],'expected_binding_id':None})
    with co.ws.connection() as db:old=db.execute("SELECT output_sha FROM automation_v2_steps WHERE task_id=? AND step_id='S05'",(t['id'],)).fetchone()[0];db.execute("UPDATE automation_v2_steps SET output_sha=? WHERE task_id=? AND step_id='S05'",('0'*64,t['id']))
    try:
        r=c.get(f'/api/chats/{cid}');assert r.status_code==409
        assert 'manifest' not in r.json() and '58.33' not in r.text
        assert c.get(f'/api/chats/{cid}/report').status_code==409
    finally:
        with co.ws.connection() as db:db.execute("UPDATE automation_v2_steps SET output_sha=? WHERE task_id=? AND step_id='S05'",(old,t['id']))

def test_parquet_import_dedup_and_conflicting_replay(api):
    import pandas as pd
    c,h,co=api;cid=create(c,h,'Parquet校验')
    payload=pd.DataFrame({'group':['a','b'],'binary':[0,1]}).to_parquet(index=False)
    headers={**h,'Content-Type':'application/octet-stream','X-Filename':'table.parquet','X-Request-Key':'parquet-one','X-Expected-Binding':'none'}
    first=c.post(f'/api/chats/{cid}/attachment',headers=headers,content=payload)
    assert first.status_code==200 and first.json()['turn']['status']=='completed'
    assert c.post(f'/api/chats/{cid}/attachment',headers=headers,content=payload).json()==first.json()
    assert c.post(f'/api/chats/{cid}/attachment',headers=headers,content=payload+b'changed').status_code==409
    assert len(c.get(f'/api/chats/{cid}').json()['messages'])==1

def test_body_limits_and_cookie_cannot_be_replaced_by_csrf_alone(api):
    c,h,_=api
    assert c.post('/api/chats',headers={**h,'Content-Type':'application/json'},content=b'{' + b' '*65536 + b'}').status_code==413
    assert c.post('/api/chats/unknown/attachment',headers={**h,'Content-Type':'application/octet-stream','Content-Length':str(21*1024*1024)},content=b'').status_code==413
    c.cookies.clear()
    assert c.post('/api/chats',headers=h,json={'title':'missing-cookie','request_key':'missing'}).status_code==401
