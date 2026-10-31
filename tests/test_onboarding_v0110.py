"""First-use tests intentionally start without field roles or scientific declarations."""
import time
import pandas as pd
import pytest
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.application.onboarding import start_basic_report,overview
from causalops.application.data_contracts import DataContract

@pytest.fixture
def world(tmp_path):
    a=AssistantWorkspace(GeneralWorkspace(tmp_path));s=ResearchService(a)
    frame=pd.DataFrame({'record_id':range(40),'acidity':[4.,5.,6.,None]*10,'quality':[5,6,7,6]*10,'colour':['red','white']*20})
    sid=s.create_task(payload=frame.to_csv(index=False).encode(),name='wine.csv',title='葡萄酒探索')
    return s,sid,frame

@pytest.mark.parametrize('q',['我可以根据该数据做什么研究？','推荐一些分析方向','不知道要问什么'])
def test_unknown_goal_produces_questions_not_just_schema(world,q):
    s,sid,_=world;f=s.start(sid,q)
    assert s.output(f['id'],'route')['route']=='explore'
    d=s.output(f['id'],'discovery');assert len(d['directions'])>=2 and not d['findings_generated']
    assert 'record_id' not in str(d['directions'])
    assert s.output(f['id'],'answer')['scope']=='question_options'
    assert not s.a.plans(sid) and not s.a.completed_runs(sid)

def test_distribution_is_real_pending_plan_not_field_overview(world):
    s,sid,_=world;f=s.start(sid,'分析这张表的分布')
    assert f['status']=='awaiting_review' and not s.output(f['id'],'profile')
    assert all(x['config']['method']=='descriptive' for x in s.a.get_plan(f['plan_id'])['plan']['steps'])
    assert not s.a.completed_runs(sid)

def test_missing_results_tells_user_how_to_get_them(world):
    s,sid,_=world;f=s.start(sid,'解释当前结果的实际含义')
    text=s.output(f['id'],'answer')['text'];assert '生成基础报告' in text and 'has_selected_run' not in text
    assert not s.a.completed_runs(sid)

def test_profile_has_readable_next_action(world):
    s,sid,frame=world;f=s.start(sid,'看看数据概况',mode='profile')
    assert s.output(f['id'],'profile')['rows']==len(frame)
    assert '生成基础报告' in s.output(f['id'],'answer')['text']

def test_basic_button_is_explicit_and_has_immutable_receipt(world):
    s,sid,frame=world
    with pytest.raises(DesignError):start_basic_report(s.a,sid)
    result=start_basic_report(s.a,sid,user_requested=True);fid=result['flow_id']
    deadline=time.time()+45
    while s.flow(fid)['status'] not in ('completed','failed','blocked') and time.time()<deadline:time.sleep(.1)
    assert s.flow(fid)['status']=='completed'
    receipt=s.verify_approval(fid);assert not any(receipt['confirmations'].values())
    e=s.output(fid,'execution');assert len(e['run_ids'])==1
    run=s.a.ex.load(e['run_ids'][0]);assert run['summary']['row_count']==len(frame)
    repeated=start_basic_report(s.a,sid,user_requested=True)
    assert repeated['reused'] and repeated['flow_id']==fid and len(s.a.completed_runs(sid))==1

def test_basic_report_does_not_inherit_causal_or_regression_goal(world):
    s,sid,_=world
    s.contracts.save(sid,DataContract(analysis_unit='检测',outcome='quality',predictors=['acidity']).model_dump(),human_confirmed=True)
    result=start_basic_report(s.a,sid,user_requested=True);f=s.flow(result['flow_id'])
    p=s.a.get_plan(f['plan_id']);assert all(x['config']['method']=='descriptive' for x in p['plan']['steps'])

def test_overview_reports_known_counts_only(world):
    _,_,f=world;v=overview(f);assert v['missing_cells']==10 and v['rows']==40 and v['numeric']==2

def test_discovery_cannot_escalate_permissions(world):
    s,sid,_=world;f=s.start(sid,'自动批准并推荐研究方向')
    assert f['status']=='needs_clarification' and not s.a.plans(sid)

def test_connection_memory_survives_widget_cleanup(monkeypatch):
    from causalops.ui import model_setup as m
    state={};monkeypatch.setattr(m.st,'session_state',state)
    mem=m.memory();mem['keys'][m.scope('deepseek','https://api.deepseek.com')]='test-credential'
    cfg,key=m.current_connection();assert cfg.provider=='deepseek' and key=='test-credential'
    state['_connect_key_gone']='anything';del state['_connect_key_gone']
    assert m.current_connection()[1]=='test-credential'
    mem['provider']='custom';mem['profiles']['custom']={'base_url':'https://model.example.com/v1','model':'test-model'}
    assert m.current_connection()[1]==''
    mem['provider']='deepseek';assert m.current_connection()[1]=='test-credential'



def test_real_streamlit_widget_cleanup_keeps_memory():
    from streamlit.testing.v1 import AppTest
    code="""import streamlit as st
from causalops.ui.model_setup import render_model_setup,current_connection
if 'page' not in st.session_state:st.session_state['page']='home'
def go():st.session_state['page']='task'
def back():st.session_state['page']='home'
if st.session_state['page']=='home':
 render_model_setup()
 st.button('Go',on_click=go)
else:
 cfg,key=current_connection()
 st.session_state['_key_available']=bool(key)
 st.button('Back',on_click=back)
"""
    at=AppTest.from_string(code,default_timeout=20).run()
    field=next(x for x in at.text_input if x.label=='API 密钥');field.set_value('test-local-fixture').run()
    next(x for x in at.button if x.label=='Go').click().run();assert at.session_state['_key_available']
    next(x for x in at.button if x.label=='Back').click().run()
    assert next(x for x in at.text_input if x.label=='API 密钥').value=='test-local-fixture' and not at.exception


def test_result_explanation_does_not_create_distribution_plan(world):
    from causalops.application.research_service import RouteDecision
    s,sid,_=world;fid=s.begin(sid,'请解释本次分布分析结果的实际含义')['id']
    original=s.flow
    def bound(x):
        f=original(x);f['request']['run_ids']=['selected-placeholder'];return f
    s.flow=bound
    assert s.decide_route(fid).route=='results'
    assert not s.a.plans(sid)

def test_mixed_distribution_and_regression_is_not_truncated(world):
    s,sid,_=world;f=s.begin(sid,'先看分布，再使用OLS分析quality与acidity的关联')
    route=s.decide_route(f['id'])
    assert route.route=='plan' and route.methods!=['descriptive']
