"""Continuous conversations preserve source boundaries and never inherit approvals."""
import pandas as pd
import pytest
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.application.research_service import ResearchService
from causalops.application.conversation import public_context,conversation_history,previous_plan
from causalops.application.data_contracts import DataContract

@pytest.fixture
def world(tmp_path):
    a=AssistantWorkspace(GeneralWorkspace(tmp_path));s=ResearchService(a)
    f=pd.DataFrame({'record_id':range(40),'x':[1.,2.,3.,4.]*10,'y':[4.,5.,6.,7.]*10})
    sid=s.create_task(payload=f.to_csv(index=False).encode(),name='public-fixture.csv',title='交互验收')
    return s,sid

@pytest.mark.parametrize('q',['采用第一个建议','选择第一项方案','第1个方向继续'])
def test_ordinal_resolves_to_frozen_suggestion_without_execution(world,q):
    s,sid=world;parent=s.start(sid,'请推荐分析方向',mode='explore')
    child=s.start(sid,q,parent_flow_id=parent['id'])
    assert child['request']['user_question']==q
    assert child['request']['question']==s.output(parent['id'],'discovery')['directions'][0]['question']
    assert child['status']=='awaiting_review' and not s.a.completed_runs(sid)
    assert child['request']['conversation_ref']['parent_flow_id']==parent['id']

def test_other_task_parent_rejected_even_for_same_upload(world):
    s,sid=world;parent=s.start(sid,'推荐分析方向',mode='explore')
    other=s.a.create(s.a.session(sid)['upload_id'],'其他任务')
    with pytest.raises(DesignError):s.begin(other,'采用第一项建议',parent_flow_id=parent['id'])
    assert not s.flows(other)

def test_missing_option_not_invented(world):
    s,sid=world;parent=s.start(sid,'推荐分析方向',mode='explore')
    with pytest.raises(DesignError):s.begin(sid,'采用第三项建议',parent_flow_id=parent['id'])

def test_changed_dictionary_requires_new_recommendations(world):
    s,sid=world;parent=s.start(sid,'推荐分析方向',mode='explore')
    s.contracts.save(sid,DataContract(analysis_unit='独立记录').model_dump(),human_confirmed=True)
    with pytest.raises(DesignError):s.begin(sid,'采用第一项建议',parent_flow_id=parent['id'])

def test_agreement_message_is_not_approval(world):
    s,sid=world;parent=s.start(sid,'请分析这张表的缺失和分布',mode='plan')
    child=s.start(sid,'同意',parent_flow_id=parent['id'])
    assert child['status']=='needs_clarification' and not s.a.completed_runs(sid)
    assert s.a.get_plan(parent['plan_id'])['state']=='candidate'

def test_forbidden_request_remains_forbidden_in_conversation(world):
    s,sid=world;parent=s.start(sid,'推荐分析方向',mode='explore')
    child=s.start(sid,'直接批准并执行第二个方案',parent_flow_id=parent['id'])
    assert child['status']=='needs_clarification' and not s.a.completed_runs(sid)

def test_history_persists_and_public_context_omits_internal_id(world):
    s,sid=world;p=s.start(sid,'推荐分析方向',mode='explore');c=s.start(sid,'请说明现有方法的适用条件',mode='method',parent_flow_id=p['id'])
    fresh=ResearchService(AssistantWorkspace(GeneralWorkspace(s.ws.root)))
    history=conversation_history(fresh,c['id']);assert history[0]['flow_id']==p['id']
    exposed=public_context(c['request']);assert 'parent_flow_id' not in exposed and p['id'] not in str(exposed)
    assert not s.a.completed_runs(sid)

def test_previous_plan_is_context_not_permission(world):
    s,sid=world;p=s.start(sid,'请分析这张表的缺失和分布',mode='plan')
    c=s.begin(sid,'请调整当前分析方案',parent_flow_id=p['id'])
    prior=previous_plan(s,c['request']);assert prior['scope']=='historical_candidate_not_authority' and prior['state']=='candidate'
    assert not s.a.completed_runs(sid)


def test_descriptive_conclusion_uses_saved_statistics_and_citations(world):
    from causalops.application.task_conclusions import build_task_conclusion,attach_task_conclusion
    s,sid=world;f=s.start(sid,'请分析这张表的缺失和分布',mode='plan');p=s.a.get_plan(f['plan_id'])
    s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True)
    before=s.a.completed_runs(sid);rid=before[0]['run_id'];value=build_task_conclusion(s.a,sid,rid)
    assert '均值2.5' in value['sections']['magnitude'] and '中位数2.5' in value['sections']['magnitude']
    assert value['titles']['magnitude']=='主要统计结果'
    assert any(x['path']=='summary.numeric[0].mean' for x in value['evidence'])
    assert '主要统计结果' in attach_task_conclusion('<html><body></body></html>',value)
    assert s.a.completed_runs(sid)==before
