from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import pytest
from causalops.evaluation.human_timing import HumanTimingStore,TimingStateError
from causalops.evaluation.metrics import summarize_pairs,semantic_result,score_completion
from causalops.evaluation.tasks import load_task
from causalops.evaluation.workflow import prepare_task_session,run_complete_task
from causalops.research import ResearchRepository
from causalops.results.interpretation import interpret_run

class Clock:
 def __init__(self):self.value=datetime(2026,10,30,tzinfo=timezone.utc)
 def __call__(self):return self.value
 def add(self,seconds):self.value+=timedelta(seconds=seconds)

@pytest.fixture
def timing(tmp_path):
 c=Clock();store=HumanTimingStore(tmp_path/'timing.sqlite3',c)
 ref={'task_id':'test','data_sha256':'fixture','estimate':.05,'lower':.01,'upper':.09,'claim':'associational','binary':True}
 return c,store,ref

def answer(**changes):
 return {'estimate':5.,'lower':1.,'upper':9.,'unit':'percentage_points','claim':'associational','explanation':'该差异仅为条件相关，建议开展后续实验。',**changes}

def test_timing_pause_reopen_and_submit(timing):
 c,s,r=timing;t=s.start('p001','test','script',r);c.add(10);s.pause(t);c.add(300)
 restored=HumanTimingStore(s.path,c);assert restored.get(t)['active_elapsed_seconds']==10
 restored.resume(t);c.add(15);row=restored.submit(t,answer())
 assert row['active_elapsed_seconds']==25
 assert json.loads(row['score_json'])['objective_passed']
 assert json.loads(row['score_json'])['business_explanation_review']=='pending_human_review'

def test_timing_duplicate_submit_rejected(timing):
 _,s,r=timing;t=s.start('p001','test','agent',r);s.submit(t,answer())
 with pytest.raises(TimingStateError):s.submit(t,answer())
 assert s.export()['submitted_count']==1

def test_only_one_active_trial_per_alias(timing):
 _,s,r=timing;s.start('p001','test','agent',r)
 with pytest.raises(TimingStateError):s.start('p001','test','script',r)

def test_abandoned_trials_are_retained_not_scored(timing):
 c,s,r=timing;t=s.start('p001','test','agent',r);c.add(8);s.abandon(t)
 assert s.get(t)['status']=='abandoned' and s.export()['submitted_count']==0
 assert not s.export()['human_savings_claim_validated']

def test_clock_rollback_is_not_negative_time(timing):
 c,s,r=timing;t=s.start('p001','test','agent',r);c.add(-2)
 with pytest.raises(TimingStateError):s.get(t)

def test_units_and_finite_answers_are_enforced(timing):
 _,s,r=timing
 with pytest.raises(TimingStateError):s.score(answer(estimate=float('nan')),r)
 r['binary']=False
 with pytest.raises(TimingStateError):s.score(answer(),r)

def test_wrong_claim_does_not_pass_just_because_numbers_match(timing):
 _,s,r=timing;score=s.score(answer(claim='identified_causal'),r)
 assert not score['objective_passed']

def test_no_started_trials_means_no_human_results(timing):
 _,s,_=timing
 assert s.export()['trials']==[] and s.export()['submitted_count']==0

def test_reference_cannot_be_reused_for_another_task(timing):
 _,s,r=timing
 with pytest.raises(TimingStateError):s.start('p001','other','agent',r)

def test_paired_summary_excludes_warmup_and_incomplete_pairs():
 def row(pair,c,t,w=False):return {'task_id':'t','pair':pair,'condition':c,'seconds':t,'passed':True,'warmup':w,'score':{'semantic_sha256':'same'}}
 rows=[row(-1,'script',100,True),row(-1,'agent',100,True),row(0,'script',1),row(0,'agent',1.1),row(1,'script',2)]
 d=summarize_pairs(rows)[0]
 assert d['complete_pairs']==1 and d['agent_minus_script_median_seconds']==pytest.approx(.1)

def test_script_and_agent_have_equal_deliverables(tmp_path):
 t=load_task('synthetic_null_ab');repo=ResearchRepository(tmp_path/'workflows.sqlite3');outputs=[]
 for condition in ['script','agent']:
  s,v=prepare_task_session(repo,t);result,record,turn,_=run_complete_task(t,repo,s,v,tmp_path/condition,condition)
  score=score_completion(t,result,record,turn)
  assert score['passed'] and score['items']>=12
  outputs.append(semantic_result(result.bundle))
 assert outputs[0]==outputs[1]

def test_panel_state_zero_not_mislabeled_as_fixed_control(tmp_path):
 t=load_task('synthetic_did_bad_trend');repo=ResearchRepository(tmp_path/'panel.sqlite3');s,v=prepare_task_session(repo,t)
 result,_,_,_=run_complete_task(t,repo,s,v,tmp_path/'panel','agent')
 text=interpret_run(result.bundle)['texts']['baseline']
 assert '不自动等于固定处理组和对照组' in text
 assert result.bundle.claim_level.value=='associational'

def test_incorrect_business_answer_not_hidden_by_timing(timing):
 _,s,r=timing;t=s.start('p001','test','script',r);row=s.submit(t,answer(estimate=50.))
 assert row['status']=='submitted' and not json.loads(row['score_json'])['objective_passed']

def test_legacy_metric_definitions_remain_available(tmp_path,monkeypatch):
 import causalops.results.interpretation as i
 from causalops.demo_domains import synthetic_scenario
 from causalops.agent import CausalOpsAgent
 monkeypatch.setattr(i,'ROOT',tmp_path/'interpretations')
 f,s,_=synthetic_scenario('ab',1);b=CausalOpsAgent().run(f,s,tmp_path/'run',data_kind='synthetic').bundle
 payload=i.interpret_run(b,use_saved=False);payload.pop('interpretation_id');payload['version']='business_interpretation_v1'
 payload['inputs']['metric_definition']={'label':'旧版登记单位','unit':'金额','kind':'continuous','direction':'neutral'}
 payload['interpretation_id']=i.digest(payload)
 p=i.ROOT/b.run_id/'business_interpretation_v1.json';p.parent.mkdir(parents=True);p.write_text(json.dumps(payload),encoding='utf-8')
 assert i.interpret_run(b)['metric']['label']=='旧版登记单位'
 assert i.interpret_run(b)['version']=='business_interpretation_v2'
@pytest.mark.parametrize('question,expected',[
 ('优先考虑CUPED提高精度','cuped'),('使用DID比较变化','did'),('请做A/B实验','ab_test'),
 ('不用DID，请使用PSM','psm'),('比较DID和PSM，优先PSM','psm'),
 ('检查did_score字段而不指定设计','descriptive')])
def test_chinese_method_intent_keeps_requested_primary(question,expected):
 from causalops.llm.proposal import _guard_method_order
 t=load_task('synthetic_null_ab');spec,_=_guard_method_order(question,t.spec)
 assert spec.candidate_methods[0].value==expected
 assert spec.assignment_mechanism==t.spec.assignment_mechanism

def test_human_task_reference_rejects_stale_dataset_fingerprint():
 from causalops.evaluation.tasks import validate_task_reference
 t=load_task('synthetic_null_ab');description=t.public_description()
 assert validate_task_reference(description)==t.data_sha256
 description['data_sha256']='stale'
 with pytest.raises(ValueError,match='指纹不一致'):validate_task_reference(description)
