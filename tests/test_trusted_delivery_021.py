"""Regression cases for observed 0.21 trusted-delivery defects; real registered tools."""
import copy,json
import pytest
from test_chat_answer_delivery import studies
from test_react_setup_api import api,confirm,compile
from test_configurable_research import co
from causalops.application.automation_results import snapshot,export_json,report_html
from causalops.application.automation_answer import answer
from causalops.application.chat_sessions import ChatService
from causalops.assistant.service import digest

def test_descriptive_risks_match_actual_method_and_no_interval(studies):
    coordinator,_,t=studies;before=digest(coordinator.steps(t['id']));v=snapshot(coordinator,t['id'])
    limits=' '.join(r['detail'] for r in v['risks'])
    assert '正态近似区间' not in limits
    assert '没有执行推断区间' in limits
    assert v['report']['method']=='descriptive' and v['report']['descriptive']['interval'] is None
    assert '正态近似区间' not in export_json(v).decode()
    assert '没有因果效应估计或区间' in report_html(v)
    assert digest(coordinator.steps(t['id']))==before

def test_actual_AB_retains_estimator_interval_and_saved_numbers(studies):
    coordinator,t,_=studies;v=snapshot(coordinator,t['id']);before=copy.deepcopy(v['report'])
    limits=' '.join(r['detail'] for r in v['risks'])
    assert '独立组均值差' in limits and '1.96' in limits and '正态近似' in limits
    r=answer(coordinator.a,t['session_id'],v,'请给出两组样本量和比例、差异、95%区间、方法、窗口、限制与来源。')
    assert '效应估计方法' in r['text'] and '独立组均值差' in r['text']
    assert '区间估计方法' in r['text'] and '1.96' in r['text']
    assert r['coverage']['method']=='available'
    assert v['report']==before and r['run_ids']==before['source_runs']

def test_unknown_method_metadata_is_explicit_not_guessed(studies):
    coordinator,t,_=studies;v=copy.deepcopy(snapshot(coordinator,t['id']));v['report']['method']='unregistered'
    v['report']['interval_method']=None
    r=answer(coordinator.a,t['session_id'],v,'请说明估计方法和区间方法。')
    assert '方法未提供' in r['text'] and '独立组均值差' not in r['text'] and r['coverage']['method']=='unavailable'

def test_adopted_projection_is_distinct_from_stale_unadopted(api):
    c,h,cid,coordinator=api;confirm(c,h,cid);p,_=compile(c,h,cid);view=c.get(f'/api/chats/{cid}/setup').json();body=dict(expected_binding_id=view['binding_id'],human_confirmed=True,request_key='accept')
    url=f'/api/chats/{cid}/candidates/{p["id"]}/adopt';response=c.post(url,headers=h,json=body);assert response.status_code==200
    assert c.post(url,headers=h,json=body).json()==response.json()
    for _ in range(2):
        value=c.get(f'/api/chats/{cid}/setup').json();assert value['phase']=='adopted'
        assert value['candidate'].get('source_state')=='adopted' and value['candidate']['source_error'] is None
        assert value['candidate']['source_current'] is False
    repeat=c.post(url,headers=h,json={**body,'request_key':'different-repeat'});assert repeat.status_code==409 and '已转为待审方案' in repeat.text
    assert coordinator.ws.connection

@pytest.mark.parametrize('suffix',['csv','parquet'])
def test_large_import_reports_row_limit_without_new_binding(tmp_path,suffix):
    import pandas as pd,io
    from causalops.general.service import GeneralWorkspace
    from causalops.assistant.service import AssistantWorkspace
    from causalops.application.research_service import ResearchService
    c=ChatService(ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path))));chat=c.create()
    frame=pd.DataFrame({'id':range(100001),'arm':[i%2 for i in range(100001)],'outcome':[i%3==0 for i in range(100001)]})
    if suffix=='csv':payload=frame.to_csv(index=False).encode()
    else:
        b=io.BytesIO();frame.to_parquet(b,index=False);payload=b.getvalue()
    c.import_data(chat.id,payload,name='limit.'+suffix,request_key='oversized')
    final=c.messages(chat.id)[-1];assert '100,000' in final['answer']['text']
    assert '未删样本' in final['answer']['text'] and c.binding(chat.id) is None
    with c.ws.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM analysis_runs').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM general_uploads').fetchone()[0]==0

def test_missing_interval_metadata_does_not_claim_normal_approximation(studies):
    coordinator,t,_=studies;v=copy.deepcopy(snapshot(coordinator,t['id']));v['report']['interval_method']='unrecognized saved metadata'
    r=answer(coordinator.a,t['session_id'],v,'请说明效应估计方法和区间方法。')
    assert '独立组均值差' in r['text'] and '区间估计方法未提供' in r['text']
    assert '1.96' not in r['text'] and '正态近似' not in r['text']


def test_actual_stale_and_cross_task_candidate_still_rejected(api):
    c,h,cid,coordinator=api;confirm(c,h,cid);proposal,_=compile(c,h,cid)
    from test_configurable_research import config
    confirm(c,h,cid,config(window='重新确认的合法观察窗口'),key='new-contract')
    old=c.get(f'/api/chats/{cid}/candidates/{proposal["id"]}').json()
    assert old['source_state']=='stale' and old['source_current'] is False and old['source_error']
    other=c.post('/api/chats',headers=h,json={'request_key':'foreign-new','title':'other'}).json()['id']
    assert c.get(f'/api/chats/{other}/candidates/{proposal["id"]}').status_code==409


def test_completed_control_rejected_without_rewriting_runs(studies):
    coordinator,t,_=studies;before=digest(coordinator.steps(t['id']))
    for operation in ('pause','cancel'):
        with pytest.raises(ValueError,match='已完成'):
            getattr(coordinator,operation)(t['id'],human_confirmed=True)
    assert coordinator.task(t['id'])['status']=='completed' and digest(coordinator.steps(t['id']))==before


def test_reader_accepts_exact_boundary_and_never_silently_truncates():
    import pandas as pd
    from causalops.general.service import read_table,TableLimitError
    payload=pd.DataFrame({'id':range(100000),'arm':[0,1]*50000}).to_csv(index=False).encode()
    assert len(read_table(payload,'within.csv'))==100000
    with pytest.raises(TableLimitError,match='100,000'):
        read_table(payload+b'100001,0\n','over.csv')

@pytest.mark.parametrize('control',['pause','cancel'])
def test_real_S02_saved_then_safe_boundary_control(co,monkeypatch,control):
    import threading
    from test_react_execution import prepared,body,wait
    from causalops.application.automation_coordinator import BoundedCoordinator
    reached=threading.Event();release=threading.Event();original=BoundedCoordinator._fault
    def gate(self,point,tid,step):
        original(self,point,tid,step)
        if point=='before_publish' and step=='S02' and not reached.is_set():
            reached.set()
            if not release.wait(30):raise TimeoutError('QA test barrier not released')
    monkeypatch.setattr(BoundedCoordinator,'_fault',gate)
    chats,cid,t,w=prepared(co);w.operate(cid,'approve',**body(w,cid,'approve'));approval=co.approval(t['id'])
    try:
        w.operate(cid,'start',**body(w,cid,'start'));assert reached.wait(20)
        with co.ws.connection() as db:
            saved=[x[0] for x in db.execute('select run_id from exploration_runs')]
            assert len(saved)==1 and db.execute('select count(*) from analysis_runs').fetchone()[0]==0
        w.operate(cid,control,**body(w,cid,control));assert co.task(t['id'])['status']==('pause_requested' if control=='pause' else 'cancel_requested')
    finally:release.set()
    assert wait(co,t)['status']==('paused' if control=='pause' else 'cancelled')
    assert co.evidence(t['id'],'S02')['body']['run_id']==saved[0]
    assert co.approval(t['id'])==approval
    if control=='pause':
        w.operate(cid,'resume',**body(w,cid,'resume'));assert wait(co,t)['status']=='completed'
        assert co.report(t['id'])['source_runs'][0]==saved[0]
    else:
        with pytest.raises(ValueError):w.operate(cid,'resume',**body(w,cid,'forbidden-resume'))
        assert next(s for s in co.steps(t['id']) if s['step_id']=='S04')['status']=='pending'
    with co.ws.connection() as db:
        assert db.execute('select count(*) from exploration_runs').fetchone()[0]==1
        assert db.execute('select count(*) from analysis_runs').fetchone()[0]==(1 if control=='pause' else 0)
