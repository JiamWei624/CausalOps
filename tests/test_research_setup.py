"""Configuration/adoption uses real contracts/compiler, without approval or runs."""
import copy
import pytest
from test_configurable_research import co, data, config
from causalops.application.chat_sessions import ChatService
from causalops.assistant.service import digest

def start(co):
    from causalops.application.research_setup import ResearchSetup
    chats=ChatService(co.s);c=chats.create();chats.import_data(c.id,data().to_csv(index=False).encode(),name='research.csv',request_key='file')
    return chats,c.id,ResearchSetup(chats)

def counts(co):
    with co.ws.connection() as db:return {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('analysis_runs','exploration_runs','automation_v2_approvals','automation_v2_tasks')}

def confirm(w,cid,cfg=None,key='confirm'):
    p=w.preview(cid)
    return w.confirm(cid,configuration=cfg or config(),expected_binding_id=p['binding_id'],expected_data_sha=p['data']['frame_sha'],expected_contract_sha=(p['contract'] or {}).get('sha'),human_confirmed=True,request_key=key)

def test_raw_contract_then_candidate_then_explicit_adoption(co):
    chats,cid,w=start(co);before=counts(co);r=confirm(w,cid)
    assert co.s.contracts.ref(r['session_id'])==r['contract_ref']
    assert w.preview(cid)['contract']['version']==1 and counts(co)==before
    assert not w.preview(cid)['candidate']
    p=w.compile(cid,r['id'],expected_binding_id=chats.binding(cid).id,request_key='compile')
    assert p['candidate']['source']=='deterministic' and p['candidate']['status']=='validated'
    assert p['candidate']['execution_authorized'] is False and len(p['candidate']['candidate']['steps'])==5
    assert chats.binding(cid).domain=='assistant'
    accepted=w.adopt(cid,p['id'],expected_binding_id=chats.binding(cid).id,human_confirmed=True,request_key='adopt')
    task=co.task(accepted['task_id']);assert task['status']=='candidate' and task['plan']['candidate_ref']
    assert chats.binding(cid).subject_id==task['id']
    after=counts(co);assert after['analysis_runs']==before['analysis_runs'] and after['exploration_runs']==before['exploration_runs'] and after['automation_v2_approvals']==0
    assert all(x['status']=='pending' for x in co.steps(task['id']))

def test_unknown_assignment_remains_description(co):
    chats,cid,w=start(co);r=confirm(w,cid,config(assignment='unknown',source_url='',design_evidence='',source_confirmed=False))
    p=w.compile(cid,r['id'],expected_binding_id=chats.binding(cid).id,request_key='compile')
    cand=p['candidate']['candidate'];assert cand['research_type']=='descriptive_binary'
    assert len(cand['steps'])==4 and not any(x['method']=='ab_test' for x in cand['steps'])
    assert cand['declared_assignment']=='unknown'

def test_version_changes_invalidate_old_candidate_and_keep_history(co):
    chats,cid,w=start(co);r=confirm(w,cid);p=w.compile(cid,r['id'],expected_binding_id=chats.binding(cid).id,request_key='plan')
    newer=confirm(w,cid,config(metric='重新确认的完成比例'),key='second')
    assert newer['contract_ref']['version']==2
    with pytest.raises(ValueError):w.adopt(cid,p['id'],expected_binding_id=chats.binding(cid).id,human_confirmed=True,request_key='old')
    assert w.candidate(cid,p['id'])['source_current'] is False
    assert len(co.s.contracts.versions(r['session_id']))==2 and co.task(p['task_id'])['status']=='candidate'

def test_duplicate_confirm_compile_and_adopt_are_idempotent(co):
    chats,cid,w=start(co);p=w.preview(cid);kwargs=dict(configuration=config(),expected_binding_id=p['binding_id'],expected_data_sha=p['data']['frame_sha'],expected_contract_sha=None,human_confirmed=True,request_key='confirm')
    a=w.confirm(cid,**kwargs);assert w.confirm(cid,**kwargs)==a
    bid=chats.binding(cid).id;proposal=w.compile(cid,a['id'],expected_binding_id=bid,request_key='plan');assert w.compile(cid,a['id'],expected_binding_id=bid,request_key='plan')==proposal
    adopted=w.adopt(cid,proposal['id'],expected_binding_id=bid,human_confirmed=True,request_key='adopt');assert w.adopt(cid,proposal['id'],expected_binding_id=bid,human_confirmed=True,request_key='adopt')==adopted
    assert w.preview(cid)['phase']=='adopted'

def test_cross_chat_receipt_and_unconfirmed_request_rejected(co):
    chats,cid,w=start(co);r=confirm(w,cid);other=chats.create()
    with pytest.raises(ValueError):w.compile(other.id,r['id'],expected_binding_id=None,request_key='cross')
    with pytest.raises(ValueError):w.confirm(cid,configuration=config(),expected_binding_id=chats.binding(cid).id,expected_data_sha=r['data']['frame_sha'],expected_contract_sha=r['contract_ref']['sha'],human_confirmed=False,request_key='false')

def test_raw_contract_without_entity_does_not_invent_identity(co):
    chats,cid,w=start(co);r=confirm(w,cid,config(entity=None))
    body=co.s.contracts.latest(r['session_id'])['body'];assert body['entity'] is None
    assert '__causalops_record_id' not in co.ws.load_upload(r['data']['upload_id']).columns
    p=w.compile(cid,r['id'],expected_binding_id=chats.binding(cid).id,request_key='plan')
    assert co.task(p['task_id'])['plan']['scope']['entity']=='__causalops_record_id'

def test_window_revision_uses_original_data_guard(co):
    chats,cid,w=start(co);r=confirm(w,cid);first=w.compile(cid,r['id'],expected_binding_id=chats.binding(cid).id,request_key='first')
    newer=confirm(w,cid,config(window='改变后的观察窗口'),key='window-change')
    before=counts(co)
    with pytest.raises(ValueError,match='观察窗口变化必须上传'):
        w.compile(cid,newer['id'],expected_binding_id=chats.binding(cid).id,request_key='second')
    assert counts(co)==before and co.task(first['task_id'])['status']=='candidate'

def test_metric_revision_uses_original_versioned_successor(co):
    chats,cid,w=start(co);r=confirm(w,cid);first=w.compile(cid,r['id'],expected_binding_id=chats.binding(cid).id,request_key='first')
    newer=confirm(w,cid,config(metric='重新确认的完成比例'),key='metric-change')
    successor=w.compile(cid,newer['id'],expected_binding_id=chats.binding(cid).id,request_key='second')
    assert co.task(successor['task_id'])['plan']['version']==2
    assert co.task(first['task_id'])['status']=='cancelled'
    assert counts(co)['analysis_runs']==counts(co)['automation_v2_approvals']==0
