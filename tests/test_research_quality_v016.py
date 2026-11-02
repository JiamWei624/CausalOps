"""Research-quality acceptance: local scope, frozen evidence, and inference boundaries."""
import copy,json
import numpy as np
import pandas as pd
import pytest
from causalops.application.research_quality import audit_research,research_brief,method_contract,next_research_steps
from causalops.application.data_contracts import DataContract
from causalops.application.research_service import ResearchService
from causalops.application.task_readiness import public_contract_context
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.assistant.contracts import REGISTRY
from causalops.application.research_report import run_quality,append_quality

@pytest.mark.parametrize('method',list(REGISTRY))
def test_every_registered_method_has_scope_and_verified_sources(method):
    value=method_contract(method)
    assert all(value[k] for k in ('estimand','population','diagnostics','limits','sources','knowledge_sha256'))
    assert all(v['url'].startswith('https://') and v['access_scope'] for v in value['sources'])

@pytest.mark.parametrize('kind',['missing','duplicates','infinity','constant','sentinel','key','post','future','self','nullable','zero','sparse','extreme'])
def test_quality_adversarial_cases_do_not_modify_data(kind):
    frame=pd.DataFrame({'id':range(40),'day':['2026-01-01']*40,'x':np.arange(40,dtype=float),'y':np.arange(40,dtype=float),'category':['a']*39+['b']})
    body={'entity':'id','time':'day','outcome':'y','covariates':['x'],'fields':[{'field':'x','timing':'pre_treatment'}]}
    expected={'missing':'missing','duplicates':'duplicates','infinity':'nonfinite','constant':'constant','sentinel':'sentinels','key':'entity_time','post':'timing:x','future':'timing:x','self':'outcome_adjustment','nullable':'missing','zero':'zeros:x','sparse':'sparse:category','extreme':'extreme:x'}[kind]
    if kind=='missing':frame.loc[0,'x']=np.nan
    if kind=='duplicates':frame=pd.concat([frame,frame.iloc[[0]]],ignore_index=True)
    if kind=='infinity':frame.loc[0,'x']=np.inf
    if kind=='constant':frame['x']=1
    if kind=='sentinel':frame.loc[0,'x']=-999
    if kind=='key':frame.loc[1,'id']=0
    if kind in ('post','future'):body['fields'][0]['timing']='post_treatment' if kind=='post' else 'future'
    if kind=='self':body['covariates']=['y']
    if kind=='nullable':frame['x']=pd.Series([pd.NA]+list(range(39)),dtype='Int64')
    if kind=='zero':frame.loc[:30,'x']=0
    if kind=='extreme':frame.loc[0,'x']=1e8
    before=frame.copy(deep=True);a=audit_research(frame,body)
    assert next(v for v in a['checks'] if v['code']==expected)['status']!='pass'
    pd.testing.assert_frame_equal(frame,before)
    assert not a['assumptions_verified'] and not a['raw_rows_included']
    json.dumps(a,allow_nan=False)

@pytest.mark.parametrize('purpose',['exploratory','predictive','causal'])
def test_options_are_bounded_and_never_approve(purpose):
    body={'purpose':purpose,'outcome':'y','predictors':['x']}
    options=next_research_steps(body,{'checks':[]})
    assert 1<=len(options)<=3 and all(v['route'] in ('plan','method','explore') for v in options)
    assert '当前上传' in research_brief(body)['population']

def test_local_scope_is_frozen_and_report_is_bound(tmp_path):
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path)))
    frame=pd.DataFrame({'x':np.random.default_rng(1).normal(size=30),'y':np.random.default_rng(2).normal(size=30)})
    sid=s.create_task(payload=frame.to_csv(index=False).encode(),name='synthetic.csv')
    original=DataContract(outcome='y',analysis_unit='样本',research={'population':'样本A','provenance':'人工测量说明 <script>alert(1)</script>','inclusion':'全部30条'}).model_dump()
    v1=s.contracts.save(sid,original,human_confirmed=True)
    f=s.start(sid,'描述 y 的分布',mode='plan')
    assert f['status']=='awaiting_review'
    snapshot=s.output(f['id'],'research_quality')
    assert snapshot['brief']['population']=='样本A' and snapshot['contract_ref']['sha']==v1['sha']
    assert '人工测量说明' not in json.dumps(public_contract_context(s,f),ensure_ascii=False)
    p=s.a.get_plan(f['plan_id'])
    s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True)
    ref=s.a.completed_runs(sid)[0];rq=run_quality(s.a,sid,ref['run_id'])
    original['research']['population']='样本B'
    s.contracts.save(sid,original,expected_sha=v1['sha'],human_confirmed=True)
    assert s.output(f['id'],'research_quality')==snapshot
    assert run_quality(s.a,sid,ref['run_id'])['brief']['population']=='样本A'
    report=append_quality('<html><body></body></html>',rq)
    assert '<script>' not in report and '&lt;script&gt;' in report and '全部30条' in report
    assert rq['saved_configurations'] and not rq['reestimate']

def test_doubleml_reproducible_actual_folds():
    from test_extended_estimators import _observational_data,_observational_spec
    from causalops.estimators import estimate_double_ml_plr
    from causalops.schemas import CausalMethod
    frame=_observational_data(rows=240);spec=_observational_spec(CausalMethod.DOUBLE_ML)
    a=estimate_double_ml_plr(frame,spec,n_folds=2,seed=11);b=estimate_double_ml_plr(frame,spec,n_folds=2,seed=11)
    assert a.estimate==b.estimate and a.evidence['split_sha256']==b.evidence['split_sha256']
    assert sum(a.evidence['fold_sizes'])==len(frame)
    assert a.evidence['overlap_prediction_source'].startswith('same_DoubleMLPLR')
    frame['treatment']=frame['treatment'].astype(float)
    frame.loc[0,'treatment']=.4
    with pytest.raises(ValueError,match='binary'):estimate_double_ml_plr(frame,spec)

def test_psm_zero_variance_is_not_certainty():
    from test_extended_estimators import _observational_data,_observational_spec
    from causalops.estimators.psm import estimate_psm_att,_standardized_mean_difference
    from causalops.schemas import CausalMethod
    frame=_observational_data(rows=400);frame['outcome']=frame.treatment*2
    result=estimate_psm_att(frame,_observational_spec(CausalMethod.PSM))
    assert result.estimate.p_value is None and result.estimate.confidence_interval is None
    assert not next(d for d in result.diagnostics if d.name=='conditional_pair_variance').passed
    assert result.evidence['unmatched_treated']>=0
    assert _standardized_mean_difference(pd.DataFrame({'x':[1,1]}),pd.DataFrame({'x':[0,0]}),['x'])['x'] is None

@pytest.mark.parametrize('estimator',['psm','double_ml'])
def test_repeated_unit_not_silently_independent(estimator):
    from test_extended_estimators import _observational_data,_observational_spec
    from causalops.estimators.psm import estimate_psm_att
    from causalops.estimators import estimate_double_ml_plr
    from causalops.schemas import CausalMethod
    frame=_observational_data(rows=100);frame['id']=np.arange(100)//2
    spec=_observational_spec(CausalMethod.PSM if estimator=='psm' else CausalMethod.DOUBLE_ML).model_copy(update={'entity_id_column':'id'})
    with pytest.raises(ValueError,match='independent|unique'):(estimate_psm_att if estimator=='psm' else estimate_double_ml_plr)(frame,spec)


def test_randomized_degenerate_and_infinite_are_rejected():
    from causalops.estimators.randomized import estimate_ab_test
    from causalops.demo_data import get_demo_scenarios
    scenario=next(v for v in get_demo_scenarios().values() if v.spec.candidate_methods[0].value=='ab_test')
    f=scenario.frame.copy();f[scenario.spec.outcome]=f[scenario.spec.treatment].astype(float)*2
    with pytest.raises(ValueError,match='variation'):estimate_ab_test(f,scenario.spec)
    f.loc[0,scenario.spec.outcome]=np.inf
    with pytest.raises(ValueError,match='finite'):estimate_ab_test(f,scenario.spec)


def test_main_export_contains_research_appendix(tmp_path):
    from causalops.application.research_service import ResearchService
    from causalops.application.task_conclusions import build_task_conclusion
    from causalops.ui.assistant_app import make_report
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path)))
    sid=s.create_task(payload=pd.DataFrame({'x':np.random.default_rng(71).normal(size=40)}).to_csv(index=False).encode(),name='sample.csv')
    f=s.start(sid,'描述数据分布',mode='plan');p=s.a.get_plan(f['plan_id'])
    s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True)
    ref=s.a.completed_runs(sid)[0]
    html=make_report(s.a,ref,sid,build_task_conclusion(s.a,sid,ref['run_id']))
    assert 'data-research-quality="1"' in html and '适用对象' in html and ref['run_id'] in html


def test_result_advice_tracks_failed_diagnostics_without_authorizing_execution():
    from causalops.application.research_report import result_next_steps
    advice=result_next_steps('psm',['匹配后不平衡'],{})
    assert '匹配后不平衡' in advice[0] and '追求显著' in advice[0]
    assert any('不确定性' in x for x in advice) and len(advice)<=3


def test_verified_example_has_source_and_resolved_plan_question(tmp_path):
    from causalops.sample_data import create_wine_task
    from causalops.application.guided_intake import GuidedIntake
    from causalops.ui.research_quality import resolved_research_question
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path)))
    sid=create_wine_task(s.a)
    GuidedIntake(s).use_example(sid,human_confirmed=True)
    body=s.contracts.latest(sid)['body']
    assert 'archive.ics.uci.edu' in body['research']['provenance']
    assert '不代表' in body['research']['population']
    f=s.start(sid,'描述 quality 的分布',mode='plan')
    brief=s.output(f['id'],'research_quality')['brief']
    assert resolved_research_question(s,f,brief)==s.a.get_plan(f['plan_id'])['plan']['objective']
