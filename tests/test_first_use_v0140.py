import pandas as pd
import pytest
from causalops.assistant.service import AssistantWorkspace,Plan
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.application.research_service import ResearchService
from causalops.application.guided_intake import GuidedIntake
from causalops.application.data_contracts import DataContract
from causalops.application.task_conclusions import build_task_conclusion,attach_task_conclusion
from causalops.application.answer_evidence import select_answer_facts
from causalops.application.conversation import previous_plan,plan_differences
from causalops.general.exploration_report import figures

@pytest.fixture
def app(tmp_path):
    a=AssistantWorkspace(GeneralWorkspace(tmp_path));s=ResearchService(a)
    frame=pd.DataFrame({'x':[1.,2.,3.,4.]*15,'quality':[5.,6.,6.,7.]*15,'segment':['a','b','a','b']*15})
    sid=s.create_task(payload=frame.to_csv(index=False).encode(),name='outside.csv',title='陌生数据')
    return s,sid

def setup_target(s,sid,field='quality'):
    g=GuidedIntake(s);row=s.contracts.latest(sid)
    g.save_unit(sid,'一条检测记录',expected_sha=row['sha'] if row else None,human_confirmed=True)
    row=s.contracts.latest(sid);g.save_target(sid,field,'质量评分' if field=='quality' else field,'分' if field=='quality' else '',expected_sha=row['sha'],human_confirmed=True)
    return g

def execute(s,sid):
    f=s.start(sid,'请分析目标指标的缺失和分布并生成报告',mode='plan');p=s.a.get_plan(f['plan_id'])
    s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True)
    return f,s.a.completed_runs(sid)[0]['run_id']

def test_progress_persists_and_never_grants_execution_or_consent(app):
    s,sid=app;g=setup_target(s,sid)
    fresh=GuidedIntake(ResearchService(AssistantWorkspace(GeneralWorkspace(s.ws.root))))
    assert fresh.state(sid)['step']==3
    request=g.finish(sid,'describe',human_confirmed=True)
    assert 'quality' in request['question'] and request['mode']=='plan'
    assert fresh.state(sid)['step']==4
    assert not s.a.consent_enabled(sid) and not s.a.plans(sid) and not s.a.completed_runs(sid)
    assert s.contracts.latest(sid)['body']['method_facts']=={}

def test_unknown_information_is_allowed_without_scientific_declaration(app):
    s,sid=app;g=GuidedIntake(s);g.save_unit(sid,'',human_confirmed=True)
    row=s.contracts.latest(sid);g.save_target(sid,None,expected_sha=row['sha'],human_confirmed=True)
    body=s.contracts.latest(sid)['body']
    assert body['outcome'] is None and body['analysis_unit']=='' and body['structure']=='unknown' and not body['method_facts']
    assert g.finish(sid,'effect',human_confirmed=True)['mode']=='method'

@pytest.mark.parametrize('operation',['unit','target','finish','reset'])
def test_intake_actions_require_human_confirmation(app,operation):
    s,sid=app;g=GuidedIntake(s)
    with pytest.raises(DesignError):
        if operation=='unit':g.save_unit(sid,'样本')
        elif operation=='target':g.save_target(sid,'quality')
        elif operation=='finish':g.finish(sid,'describe')
        else:g.reset(sid)

def test_concurrent_context_change_is_not_overwritten(app):
    s,sid=app;g=setup_target(s,sid)
    with pytest.raises(DesignError):g.save_target(sid,'x',expected_sha='old-sha',human_confirmed=True)
    assert s.contracts.latest(sid)['body']['outcome']=='quality'

def test_context_change_requires_new_method_review(app):
    s,sid=app;g=setup_target(s,sid);row=s.contracts.latest(sid);body=row['body'];body['method_facts']={'ols':{'independent_rows_reviewed':True}}
    row=s.contracts.save(sid,body,expected_sha=row['sha'],human_confirmed=True)
    g.save_target(sid,'x',expected_sha=row['sha'],human_confirmed=True)
    assert s.contracts.latest(sid)['body']['method_facts']=={}

def test_target_drives_frozen_conclusion_evidence_and_chart(app):
    s,sid=app;g=setup_target(s,sid);f,rid=execute(s,sid);before=s.a.completed_runs(sid)
    out=build_task_conclusion(s.a,sid,rid)
    assert out['focus']['field']=='quality' and out['focus']['available']
    assert '均值6分' in out['sections']['magnitude'] and '中位数6分' in out['sections']['magnitude']
    assert any(v['text'].startswith('quality / mean') and v['value']==6 for v in out['evidence'])
    assert next(iter(figures(s.a.ex.load(rid),focus='quality')))=='分布_quality'
    row=s.contracts.latest(sid);g.save_target(sid,'x',expected_sha=row['sha'],human_confirmed=True)
    assert build_task_conclusion(s.a,sid,rid)['focus']['field']=='quality'
    assert s.a.completed_runs(sid)==before
    report=attach_task_conclusion('<html><body><h1>报告</h1><p>详细内容</p></body></html>',out)
    assert report.index('均值6分')<report.index('详细内容')

def test_qa_prefers_bound_target_but_explicit_field_request_wins(app):
    s,sid=app;setup_target(s,sid);_,rid=execute(s,sid);facts,runs=s.a.facts(sid,run_ids=[rid])
    chosen=select_answer_facts(facts,runs,'解释本次结果',target_by_run={rid:'quality'})
    assert chosen[0][1]['text'].startswith('quality /')
    chosen=select_answer_facts(facts,runs,'解释x的均值',target_by_run={rid:'quality'})
    assert chosen[0][1]['text'].startswith('x /')

def test_target_outside_default_column_limit_is_included(tmp_path):
    a=AssistantWorkspace(GeneralWorkspace(tmp_path));s=ResearchService(a)
    frame=pd.DataFrame({f'value_{i}':[1.,2.,3.,4.]*8 for i in range(18)})
    sid=s.create_task(payload=frame.to_csv(index=False).encode(),name='wide.csv')
    setup_target(s,sid,'value_17');f,rid=execute(s,sid)
    assert build_task_conclusion(a,sid,rid)['focus']['available']

def test_categorical_target_uses_stored_share_without_category_values(app):
    s,sid=app;setup_target(s,sid,'segment');_,rid=execute(s,sid);out=build_task_conclusion(s.a,sid,rid)
    assert '50%' in out['sections']['magnitude'] and out['focus']['available']
    assert any(v['path'].startswith('summary.categorical') for v in out['evidence'])

def test_previous_plan_can_be_reached_through_explanation(app):
    s,sid=app;p=s.start(sid,'请分析缺失和分布并生成报告',mode='plan')
    middle=s.start(sid,'请说明适用条件，不进行计算',mode='method',parent_flow_id=p['id'])
    child=s.begin(sid,'调整当前方案',mode='plan',parent_flow_id=middle['id'])
    old=previous_plan(s,child['request']);assert old['scope']=='historical_candidate_not_authority'
    changed={**s.a.get_plan(p['plan_id'])['plan'],'objective':'新的分析问题'}
    assert plan_differences(old,changed)[0]['项目']=='分析问题'
    assert not s.a.completed_runs(sid)


def test_local_followup_explains_actual_target_and_limits_without_reestimate(app):
    s,sid=app;setup_target(s,sid);_,rid=execute(s,sid);before=s.a.completed_runs(sid)
    answer=s.a.ask(sid,'解释本次结果')
    assert '均值6分' in answer['text'] and answer['conclusion_ref']['run_id']==rid
    limits=s.a.ask(sid,'解释限制与下一步')
    assert '当前没有估计干预效果' in limits['text'] and '关联分析计划' in limits['text']
    assert limits['source']=='本地结果解释（未调用模型）' and not limits['facts']
    assert s.a.completed_runs(sid)==before


@pytest.mark.parametrize('method',['descriptive','correlation'])
def test_invalid_descriptive_roles_rejected_before_review(app,method):
    s,sid=app
    plan={'objective':'检查候选字段角色是否合法','citations':['descriptive'],'steps':[{'tool':'exploration','config':{'question':'检查数值与分类角色重复','method':method,'numeric':['x','quality'],'categorical':['quality']},'reason':'应在模型修复阶段被拒绝'}]}
    with pytest.raises(DesignError,match='数值和分类字段不能重复'):
        s.a.validate_plan(s.a.session(sid)['upload_id'],plan)
    assert not s.a.plans(sid) and not s.a.completed_runs(sid)


def test_model_repair_receives_exact_rejected_candidate(app,monkeypatch):
    import copy
    s,sid=app;setup_target(s,sid);seen=[]
    def fake_call(sid,model,system,payload,schema):
        seen.append(copy.deepcopy(payload))
        card=payload['retrieved_methods']['hits'][0]['card_id']
        config={'question':'检查目标指标的缺失与分布','method':'descriptive','numeric':['quality'],'categorical':['quality'] if len(seen)==1 else []}
        return {'objective':'了解质量评分分布','steps':[{'tool':'exploration','config':config,'reason':'本地计算保存统计'}],'citations':[card]}
    monkeypatch.setattr(s.a,'_call',fake_call)
    plan=s.a.propose(sid,'请分析质量评分的缺失与分布',model=__import__('types').SimpleNamespace(provider_config=__import__('causalops.llm.providers',fromlist=['ProviderConfig']).ProviderConfig()))
    assert len(seen)==2 and seen[1]['rejected_candidate']['steps'][0]['config']['categorical']==['quality']
    assert '数值和分类字段不能重复' in seen[1]['repair_required']
    assert plan['state']=='candidate' and not s.a.completed_runs(sid)
