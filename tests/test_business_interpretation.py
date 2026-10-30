import json
from copy import deepcopy
import numpy as np
import pandas as pd
import pytest
from causalops.agent import CausalOpsAgent
from causalops.schemas import CausalSpec,CausalMethod,ClaimLevel
from causalops.results.interpretation import collect_interpretation_inputs,interpret_run,persist_interpretation
from causalops.results.evidence import build_run_evidence,build_interpreted_run_evidence,select_question_evidence
from causalops.results.qa import validate_and_render,CitationValidationError,ResultQAService
from causalops.research import ResearchRepository,RevisionSource,DraftStatus
from causalops.ui.controller import run_versioned_workflow
from causalops.reporting import render_html_report,render_markdown_report

@pytest.fixture
def bundle(tmp_path):
 f=pd.DataFrame({'id':range(100),'t':[0]*50+[1]*50,'y':[1]*10+[0]*40+[1]*30+[0]*20,'pre':np.linspace(-1,1,100)})
 s=CausalSpec(question='营销随机实验访问差异',domain='generic',analysis_unit='customer',treatment='t',outcome='y',entity_id_column='id',candidate_methods=['ab_test'],assignment_mechanism='randomized')
 b=CausalOpsAgent().run(f,s,tmp_path/'runs',data_kind='synthetic',study_context={'metric_definition':{'label':'访问概率','unit':'概率','kind':'binary','direction':'higher_is_better','window':'两周'}}).bundle
 return f,s,b

def test_ab_baseline_relative_and_standardized_units(bundle):
 _,_,b=bundle;x=interpret_run(b)
 assert x['baseline']['control_mean']==pytest.approx(.2)
 assert x['magnitude']['estimate']==pytest.approx(.4)
 assert x['magnitude']['relative_change_pct']==pytest.approx(200)
 assert x['magnitude']['scaled_per_1000']==pytest.approx(400)
 assert '个百分点' in x['texts']['magnitude']
 assert '不是已实际新增' in x['texts']['scale']
 assert x['magnitude']['scaled_ci']==pytest.approx([v*1000 for v in b.estimate.confidence_interval])

def test_no_balance_fields_is_not_a_pass(bundle):
 b=bundle[2];d=next(d for d in b.diagnostics if d.name=='baseline_balance_not_assessed')
 assert d.value is None and not d.passed and not d.claim_blocking
 assert b.evidence['estimator']['maximum_absolute_smd'] is None

def test_zero_baseline_never_divides(bundle,tmp_path):
 f,s,_=bundle;f.loc[f.t==0,'y']=0
 b=CausalOpsAgent().run(f,s,tmp_path/'zero',data_kind='synthetic').bundle
 x=interpret_run(b);assert x['magnitude']['relative_change_pct'] is None
 assert '正值' in x['texts']['relative']

def test_adjusted_method_does_not_divide_raw_baseline(bundle):
 _,_,original=bundle;b=original.model_copy(deep=True)
 b.plan.selected_method=CausalMethod.CUPED
 x=interpret_run(b)
 assert x['magnitude']['relative_change_pct'] is None
 assert x['magnitude']['scaled_per_1000'] is None
 assert '不是调整后的预测值' in x['texts']['baseline']

def test_association_cannot_claim_causal_growth(bundle):
 b=bundle[2].model_copy(deep=True);b.plan.selected_method=CausalMethod.REGRESSION_ADJUSTMENT;b.claim_level=ClaimLevel.ASSOCIATIONAL
 x=interpret_run(b)
 assert '条件相关' in x['texts']['magnitude']
 assert '不能说干预导致' in x['texts']['boundary']
 assert '不建议据关联系数直接扩量' in x['texts']['action']
 assert x['magnitude']['relative_change_pct'] is None

def test_unknown_metric_direction_does_not_call_positive_good(bundle):
 b=bundle[2].model_copy(deep=True);b.evidence['interpretation_inputs']['metric_definition']=None;b.evidence['study_context'].pop('metric_definition',None)
 x=interpret_run(b)
 assert '未登记指标的业务方向' in x['texts']['meaning']

def test_binary_definition_rejects_nonbinary_values(bundle):
 f,s,_=bundle;f=f.copy();f['y']=f.y.astype(float);f.loc[0,'y']=.25
 with pytest.raises(ValueError,match='非二元'):
  collect_interpretation_inputs(f,s,{'metric_definition':{'label':'访问','kind':'binary'}})

def test_interval_crossing_zero_does_not_prove_no_effect(bundle):
 b=bundle[2].model_copy(deep=True);b.estimate.confidence_interval=(-.1,.6)
 x=interpret_run(b)
 assert '不能据此断言没有效果' in x['texts']['meaning']

def test_adverse_business_direction_is_explicit(bundle):
 b=bundle[2].model_copy(deep=True);b.evidence['interpretation_inputs']['metric_definition']['direction']='lower_is_better'
 assert '目标相反' in interpret_run(b)['texts']['meaning']

def test_snapshot_extension_never_mutates_legacy(bundle):
 b=bundle[2];old=build_run_evidence(b);copy=deepcopy(old);new=build_interpreted_run_evidence(b)
 assert old==copy==build_run_evidence(b)
 assert new['schema_version']!=old['schema_version']
 assert new['bundle_sha256']==old['bundle_sha256']
 assert new['snapshot_id']!=old['snapshot_id']
 assert any(x['evidence_id']=='C004' for x in new['facts'])

def test_derived_values_still_require_citations(bundle):
 b=bundle[2];snap=build_interpreted_run_evidence(b);facts=select_question_evidence(snap,'基线与相对变化')
 raw={'run_id':b.run_id,'claim_level':snap['claim_level'],'sections':[{'title':'直接回答','template':'{{C001}}{{C002}}{{C003}}'},{'title':'结论边界','template':'{{E004}}{{E020}}'}]}
 result=validate_and_render(raw,snap,facts);assert '200' in result['sections'][0]['text']
 raw['sections'][0]['template']+='新增999名用户'
 with pytest.raises(CitationValidationError):validate_and_render(raw,snap,facts)

def test_sidecar_tampering_and_immutable_version(bundle,tmp_path,monkeypatch):
 import causalops.results.interpretation as module
 monkeypatch.setattr(module,'ROOT',tmp_path/'interpretations')
 b=bundle[2];path=persist_interpretation(b);before=path.read_bytes()
 assert persist_interpretation(b).read_bytes()==before
 p=json.loads(before);p['texts']['magnitude']='编造的数值';path.write_text(json.dumps(p),encoding='utf-8')
 with pytest.raises(ValueError,match='校验失败'):interpret_run(b)

def test_summary_precedes_statistical_table_in_both_formats(bundle):
 b=bundle[2];html=render_html_report(b);md=render_markdown_report(b)
 assert html.index('一页读懂')<html.index('主分析估计')
 assert md.index('一页读懂')<md.index('## 估计结果')
 assert '成本' in html and 'ROI' in html

def test_previous_snapshot_history_is_preserved(bundle,tmp_path):
 f,s,_=bundle;repo=ResearchRepository(tmp_path/'state.sqlite3')
 session=repo.create_session(title='test',dataset_fingerprint='test',row_count=len(f),column_schema={c:str(t) for c,t in f.dtypes.items()})
 rev=repo.create_revision(session.session_id,s,source=RevisionSource.SYSTEM_INITIAL,change_reason='fixture',activate=True,status=DraftStatus.PENDING_REVIEW)
 repo.approve_revision(rev.revision_id,approved_by='test_fixture',checklist={'variables':True,'covariates':True,'assumptions':True})
 result=run_versioned_workflow(f,repo,session_id=session.session_id,revision_id=rev.revision_id,output_dir=tmp_path/'versioned',source_description='synthetic',data_kind='synthetic')
 b=result.agent_result.bundle;old=repo.save_result_snapshot(build_run_evidence(b))
 repo.add_result_qa_turn(run_id=b.run_id,snapshot_id=old['snapshot_id'],question='历史问题',answer={'run_id':b.run_id,'sections':[]})
 _,new=ResultQAService(repo).prepare(session_id=session.session_id,run_id=b.run_id)
 assert len(repo.list_result_qa_turns(run_id=b.run_id,snapshot_id=old['snapshot_id']))==1
 assert len(repo.list_previous_result_qa_turns(run_id=b.run_id,exclude_snapshot_id=new['snapshot_id']))==1
 assert repo.list_result_qa_turns(run_id=b.run_id,snapshot_id=new['snapshot_id'])==[]

def test_arbitrary_continuous_scale_cannot_become_relative_growth(bundle):
 b=bundle[2].model_copy(deep=True)
 b.evidence['interpretation_inputs']['metric_definition']={'label':'温度','kind':'continuous','unit':'摄氏度','direction':'higher_is_better','ratio_scale':False}
 assert interpret_run(b)['magnitude']['relative_change_pct'] is None

def test_business_answer_plan_requires_units_and_cost_citations(bundle):
 from causalops.results.qa import answer_contract,validate_answer_contract
 snap=build_interpreted_run_evidence(bundle[2]);contract=answer_contract('基线、绝对变化、相对变化、每千条以及净利润是什么？',snap)
 assert {'C001','C002','C003','C004','C008'}<=set(contract['required_evidence'])
 raw={'run_id':snap['run_id'],'claim_level':snap['claim_level'],'sections':[{'title':p['title'],'template':''.join('{{'+i+'}}' for i in p['evidence_ids'])} for p in contract['citation_plan']]}
 answer=validate_and_render(raw,snap,select_question_evidence(snap,'基线相对提升'))
 validate_answer_contract(answer,contract)
 assert '未计算净利润' in str(answer)