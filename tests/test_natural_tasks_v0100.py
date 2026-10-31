"""Natural-task context, readiness, run selection, quantitative explanation and report fidelity."""
import json,copy
import numpy as np,pandas as pd,pytest
pytest.importorskip('langgraph')
from causalops.application.research_service import ResearchService
from causalops.application.task_readiness import public_contract_context,check_declared_roles,plan_readiness
from causalops.application.task_conclusions import build_task_conclusion,attach_task_conclusion,source_dictionary
from causalops.application.answer_evidence import select_answer_facts
from causalops.assistant.service import AssistantWorkspace,Plan,Step
from causalops.general.service import GeneralWorkspace,DesignError

@pytest.fixture
def world(tmp_path):
    rng=np.random.default_rng(10);n=160;f=pd.DataFrame({'id':range(n),'x':rng.normal(size=n),'z':rng.normal(size=n)})
    f['y']=1+.5*f.x+.2*f.z+rng.normal(size=n);f['b']=rng.binomial(1,1/(1+np.exp(-f.x)))
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path)));sid=s.create_task(payload=f.to_csv(index=False).encode(),name='synthetic.csv')
    d={'analysis_unit':'独立合成样本','entity':'id','outcome':'y','predictors':['x','z'],'fields':[{'field':'y','meaning':'合成得分','unit':'分'},{'field':'x','meaning':'基线解释变量','unit':'原始单位'}],'method_facts':{'ols':{'independent_rows_reviewed':True}},'notes':'LOCAL_ONLY_SENTINEL'}
    v=s.contracts.save(sid,d,human_confirmed=True)
    return s,sid,f,d,v

def execute(s,sid):
    f=s.start(sid,'使用OLS分析x及z与结果的关系',mode='plan');p=s.a.get_plan(f['plan_id'])
    s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,use_contract_facts=True)
    return f,s.a.selected_run(sid)

def test_public_dictionary_is_minimal_and_not_method_keyed(world):
    s,sid,_,d,_=world;f=s.begin(sid,'理解当前数据字段的用途',mode='plan');ctx=public_contract_context(s,f);text=json.dumps(ctx)
    assert ctx['definition']['entity']=='id' and ctx['definition']['outcome']=='y'
    assert 'LOCAL_ONLY_SENTINEL' not in text and 'method_facts' not in text and 'independent_rows_reviewed' not in text
    assert ctx['evidence_type']=='human_declaration_not_empirical_validation'

def test_routing_receives_roles_but_selects_minimum_primary(world):
    s,sid,_,_,_=world
    class M:
        base_url='https://api.deepseek.com';last_telemetry={}
        def complete_json(self,**kw):
            assert kw['user_payload']['data_dictionary']['definition']['outcome']=='y'
            assert not any(x['field']=='id' for x in kw['user_payload']['dataset']['fields'])
            return {'route':'plan','reason':'完成一个条件关联任务','methods':['ols','correlation']}
    s.model=M();s.a.consent(sid,True);f=s.begin(sid,'控制z后x与y关系如何？');assert s.decide_route(f['id']).methods==['ols']

@pytest.mark.parametrize('field,value',[('outcome','b'),('entity','x'),('predictors',['x'])])
def test_model_cannot_silently_change_declared_roles(world,field,value):
    s,sid,_,_,_=world;f=s.begin(sid,'估计已登记变量的关联',mode='plan');cfg={'method':'ols','question':'解释已登记的条件线性关系','outcome':'y','predictors':['x','z'],'entity':'id'};cfg[field]=value
    with pytest.raises(DesignError):check_declared_roles(Plan(objective='计划',steps=[Step(config=cfg,reason='核对字段')],citations=['ols']),public_contract_context(s,f))

def test_incomplete_research_plan_returns_specific_missing_roles(world):
    s,sid,_,_,_=world;f=s.begin(sid,'制定一个待补充的研究设计',mode='plan')
    p={'steps':[{'tool':'research','config':{'method':'ab_test','question':'比较两组用户的结果差异','outcome':'y','entity':'id','treatment':'b'},'reason':'待补口径'}]}
    result=plan_readiness(s,f,p);assert not result['configuration_ready'];assert any('对照组取值' in v for v in result['errors'])

def test_post_measurement_input_is_rejected_before_estimation(world):
    s,sid,_,d,v=world;d.update(purpose='predictive',fields=[{'field':'x','timing':'future'}]);s.contracts.save(sid,d,expected_sha=v['sha'],human_confirmed=True);f=s.begin(sid,'利用未来变量进行预测',mode='plan')
    p=Plan(objective='预测计划',steps=[Step(config={'method':'ols','question':'未来数据不应作为当前输入','outcome':'y','predictors':['x','z']},reason='检查时序')],citations=['ols'])
    with pytest.raises(DesignError,match='未来'):check_declared_roles(p,public_contract_context(s,f))
    assert not s.a.completed_runs(sid)

def test_conclusion_reads_source_dictionary_not_latest(world):
    s,sid,_,d,v=world;flow,rid=execute(s,sid);before=build_task_conclusion(s.a,sid,rid)
    d['fields'][0]['unit']='后来登记的新单位';s.contracts.save(sid,d,expected_sha=v['sha'],human_confirmed=True)
    after=build_task_conclusion(s.a,sid,rid);assert after['sha256']==before['sha256'];assert after['contract_ref']['sha']==v['sha']
    assert '后来登记' not in after['sections']['magnitude']

def test_four_part_explanation_is_quantitative_and_bound(world):
    s,sid,_,_,_=world;flow,rid=execute(s,sid);value=build_task_conclusion(s.a,sid,rid);b=s.a.ex.load(rid)
    assert set(value['sections'])=={'baseline','magnitude','meaning','action'}
    assert format(b['regression']['coefficients'][1]['coefficient'],'.4g') in value['sections']['magnitude']
    assert '95%' in value['sections']['magnitude'] and '条件线性关联' in value['sections']['meaning'] and value['no_reestimate']
    catalog,_=s.a.facts(sid,run_ids=[rid]);assert all(v['id'] in catalog for v in value['evidence'])

def test_conclusion_cannot_read_other_task_run(world):
    s,sid,_,_,_=world;_,rid=execute(s,sid);other=s.a.create(s.a.session(sid)['upload_id'])
    with pytest.raises(DesignError):build_task_conclusion(s.a,other,rid)

def test_report_contains_explanation_and_evidence_without_recompute(world):
    s,sid,_,_,_=world;_,rid=execute(s,sid);n=len(s.a.completed_runs(sid));v=build_task_conclusion(s.a,sid,rid)
    report=attach_task_conclusion('<html><body>原报告</body></html>',v)
    assert 'data-causalops-task-conclusion' in report and '建议采取的下一步' in report and rid in report and len(s.a.completed_runs(sid))==n

def test_logit_or_is_not_probability_change(world):
    s,sid,_,d,v=world;d['outcome']='b';d['metric_kind']='binary';d['method_facts']={'logit':{'independent_rows_reviewed':True}};s.contracts.save(sid,d,expected_sha=v['sha'],human_confirmed=True)
    f=s.start(sid,'使用Logit分析本次二元结果关联',mode='plan');p=s.a.get_plan(f['plan_id']);s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,use_contract_facts=True)
    c=build_task_conclusion(s.a,sid,s.a.selected_run(sid));assert '优势比OR' in c['sections']['magnitude'] and '不是概率比' in c['sections']['meaning'] and '不能补写转化率提升' in c['sections']['meaning']

@pytest.mark.parametrize('question',['样本量是多少？','x的差异和区间是什么？','相关强弱是什么？'])
def test_answer_evidence_budget_and_run_scope(world,question):
    s,sid,_,_,_=world;_,rid=execute(s,sid);facts,runs=s.a.facts(sid,run_ids=[rid]);selected=select_answer_facts(facts,runs,question)
    assert 0<len(selected)<=8 and all(f['run_id']==rid for _,f in selected)
    if '样本' in question:assert any(f['path'] in ('summary.row_count','regression.n') for _,f in selected)

def test_primary_result_does_not_switch_to_later_descriptive_step(world):
    s,sid,_,_,_=world
    class M:
        base_url='https://api.deepseek.com';last_telemetry={}
        def complete_json(self,**kw):
            title=kw['output_schema'].get('title');payload=kw['user_payload']
            if title=='Plan':return {'objective':'先做主要模型，再做辅助汇总','steps':[{'tool':'exploration','config':{'method':'ols','question':'解释已登记的条件线性关联','outcome':'y','predictors':['x','z']},'reason':'主要研究问题'},{'tool':'exploration','config':{'method':'descriptive','question':'核对辅助的分布汇总情况','numeric':['x']},'reason':'辅助汇总'}],'citations':[payload['retrieved_methods']['hits'][0]['card_id']]}
            if title=='GroundedReply':
                k=next(iter(payload['fact_catalog']));return {'explanation':'结果依据为[['+k+']]；不说明干预收益。','fact_ids':[k],'citations':[]}
            raise AssertionError(title)
    s.model=M();s.a.consent(sid,True);f=s.start(sid,'OLS分析当前条件关联',mode='plan');p=s.a.get_plan(f['plan_id']);s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,use_contract_facts=True)
    execution=s.output(f['id'],'execution');primary=execution['primary_run_ids'][0];assert primary!=execution['run_ids'][-1]
    assert s.output(f['id'],'answer')['run_ids']==[primary] and s.a.selected_run(sid)==primary


@pytest.mark.parametrize('text,method,claim',[('购买率提高[[known]]个百分点','logit','associational'),('产品导致了增长[[known]]','ols','associational'),('ROI提高[[known]]','ab_test','identified_causal')])
def test_quantitative_semantics_rejects_unsupported_claim(text,method,claim):
    from causalops.application.answer_evidence import check_answer_semantics
    with pytest.raises(DesignError):check_answer_semantics(text,[('known',{'claim':claim})],[{'method':method}])

@pytest.mark.parametrize('text',['不能把优势比解释为购买率提高若干个百分点。','当前关联不能证明产品导致了增长。','没有成本，不能说ROI提高。'])
def test_quantitative_semantics_keeps_valid_limitations(text):
    from causalops.application.answer_evidence import check_answer_semantics
    check_answer_semantics(text,[('known',{'claim':'associational'})],[{'method':'logit'}])



def test_method_specific_supplement_is_not_crowded_out(world):
    from causalops.integrations.method_retriever import MethodRetriever
    s,sid,_,_,_=world
    result=MethodRetriever(library=s.a.library,method_filter='ab_test',k=8).search_bundle('ab_test 适用问题 数据要求 识别条件 诊断方法 描述 数据质量')
    assert result['hits'] and all('ab_test' in x['methods'] for x in result['hits'])


def test_glm_ratio_interval_is_monotone_transform_of_saved_bounds():
    from causalops.general.exploration import ExplorationDesign,compute
    rng=np.random.default_rng(123);x=rng.normal(size=700);frame=pd.DataFrame({'x':x,'y':rng.binomial(1,1/(1+np.exp(-x)))})
    b=compute(frame,ExplorationDesign(method='logit',question='核对优势比区间的单调指数变换',outcome='y',predictors=['x'],covariance='HC0',independent_rows_reviewed=True))
    for row in b['regression']['coefficients']:assert row['exp_ci95']==pytest.approx(np.exp([row['ci95_low'],row['ci95_high']]))


def test_route_prompt_distinguishes_empirical_request_from_method_consultation(world):
    s,sid,_,_,_=world
    class M:
        base_url='https://api.deepseek.com';last_telemetry={}
        def complete_json(self,**kw):
            assert '路由plan' in kw['system_instruction'] and '用户未写统计方法名' in kw['system_instruction']
            return {'route':'plan','reason':'用当前表回答实证问题','methods':['ols']}
    s.model=M();s.a.consent(sid,True);f=s.begin(sid,'控制其他变量后，x与y的关系多大？')
    assert s.decide_route(f['id']).route=='plan'


def test_result_answer_cannot_pass_by_dropping_all_evidence(world):
    s,sid,_,_,_=world;_,rid=execute(s,sid)
    class M:
        base_url='https://api.deepseek.com';last_telemetry={}
        def complete_json(self,**kw):
            return {'explanation':'目前可观察到关联，但无法据此决策。','fact_ids':[],'citations':[]}
    s.a.consent(sid,True);reply=s.a.ask(sid,'结果的幅度和区间是什么？',M(),run_id=rid)
    assert reply['source'].startswith('本地') and reply['facts']
    assert any('至少引用一条' in x for x in reply['validation_repairs'])


def test_only_completed_output_contract_failure_has_bounded_changed_input_repair(world):
    from causalops.llm.providers import OutputContractError
    s,sid,_,_,_=world
    class M:
        base_url='https://api.deepseek.com';last_telemetry={};calls=0
        def complete_json(self,**kw):
            self.calls+=1
            if self.calls==1:
                self.last_telemetry={'total_tokens':11};raise OutputContractError('schema mismatch')
            assert 'output_contract_repair' in kw['user_payload']
            self.last_telemetry={'total_tokens':13};return {'ok':True}
    m=M();s.a.consent(sid,True);assert s.a._call(sid,m,'test',{}, {})=={'ok':True} and m.calls==2
    usage=[x['body'] for x in s.a.events(sid) if x['kind']=='model_usage'];assert sum(x['total_tokens'] for x in usage)==24


def test_http_error_is_not_retried_as_output_repair(world):
    from causalops.llm.providers import ProviderError
    s,sid,_,_,_=world
    class M:
        base_url='https://api.deepseek.com';last_telemetry={};calls=0
        def complete_json(self,**kw):self.calls+=1;raise ProviderError('HTTP 400')
    m=M();s.a.consent(sid,True)
    with pytest.raises(DesignError):s.a._call(sid,m,'test',{}, {})
    assert m.calls==1


def test_same_model_cannot_be_fitted_twice_under_descriptive_labels(world):
    s,sid,_,_,_=world;config={'method':'ols','question':'解释当前数据的条件关联','outcome':'y','predictors':['x','z']}
    p=Plan(objective='错误地重复拟合同一模型',steps=[Step(config=config,reason='主模型'),Step(config={**config,'question':'体检却仍拟合同样的模型','numeric':['x']},reason='错误的体检')],citations=['ols'])
    with pytest.raises(DesignError,match='重复拟合'):s.a.validate_plan(s.a.session(sid)['upload_id'],p)


def test_short_model_evidence_alias_is_restored_to_immutable_id(world):
    s,sid,_,_,_=world;_,rid=execute(s,sid)
    class M:
        base_url='https://api.deepseek.com';last_telemetry={}
        def complete_json(self,**kw):
            keys=list(kw['user_payload']['fact_catalog']);assert keys and all(k.startswith('F') and len(k)<=2 for k in keys)
            return {'explanation':'本次保存结果为[['+keys[0]+']]；不能当作干预收益。','fact_ids':[keys[0]],'citations':[]}
    s.a.consent(sid,True);ans=s.a.ask(sid,'解释当前结果与限制',M(),run_id=rid);facts,_=s.a.facts(sid,run_ids=[rid])
    assert ans['source'].startswith('DeepSeek') and ans['facts'][0]['id'] in facts and ans['facts'][0]['id']!='F1'


def test_result_payload_does_not_mix_draft_numbers_and_old_evidence_refs():
    from causalops.application.answer_evidence import prepare_result_payload
    p={'dataset':{'rows':300,'exact_duplicate_rows':41,'fields':[{'field':'x','dtype':'float','numeric':True,'distinct_n':99}]},'research_context':{'source_plans':[{'version':1,'state':'completed','plan':{'objective':'解释关联','dataset_notes':['曾发现41重复行'],'steps':[{'tool':'exploration','config':{'method':'ols','covariance':'HC3','question':'草案当时的数字41'}}]}}],'plan_questions_at_creation':['确认41条重复'],'recent_scoped_answer_refs':[{'fact_ids':['oldref']}],'registered_facts':[{'human_registered_flags':{'independent_rows_reviewed':True}}]},'fact_catalog':{'F1':{'value':.5}}}
    q=prepare_result_payload(p);assert 'exact_duplicate_rows' not in q['dataset'];assert q['research_context']['recent_scoped_answer_refs']==[] and q['research_context']['registered_facts']==p['research_context']['registered_facts']
    assert '41' not in json.dumps(q) and q['fact_catalog']==p['fact_catalog']


def test_report_conclusion_is_inside_body(world):
    s,sid,_,_,_=world;_,rid=execute(s,sid);v=build_task_conclusion(s.a,sid,rid)
    text=attach_task_conclusion('<html><body>report</body></html>',v)
    assert text.index('data-causalops-task-conclusion')<text.index('</body>')


def test_result_render_does_not_repeat_metric_name_or_expose_claim_enum(world):
    from causalops.assistant.service import display_number
    s,sid,_,_,_=world;_,rid=execute(s,sid)
    class M:
        base_url='https://api.deepseek.com';last_telemetry={}
        def complete_json(self,**kw):
            k,v=next(iter(kw['user_payload']['fact_catalog'].items()))
            return {'explanation':v['text']+'为[['+k+']]，不能据此宣称因果收益。','fact_ids':[k],'citations':[]}
    s.a.consent(sid,True);reply=s.a.ask(sid,'解释当前结果和限制',M(),run_id=rid)
    assert reply['source'].startswith('DeepSeek') and reply['text'].count(reply['facts'][0]['text'])==1
    assert display_number('associational')=='条件关联关系'
