import json,copy
from pathlib import Path
import numpy as np,pandas as pd,pytest
import statsmodels.api as sm
from causalops.assistant.service import AssistantWorkspace,profile,Plan,Step
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.general.exploration import ExplorationDesign,compute
from causalops.knowledge.retrieval import MethodLibrary
from causalops.evaluation.user_trials import UserTrials

@pytest.fixture
def assistant(tmp_path):
    a=AssistantWorkspace(GeneralWorkspace(tmp_path));rng=np.random.default_rng(712);n=240
    f=pd.DataFrame({'user_id':np.arange(n),'x':rng.normal(size=n),'z':rng.normal(size=n)})
    f['y']=1+2*f.x+rng.normal(size=n);f['binary']=rng.binomial(1,1/(1+np.exp(-.5*f.x)));f['count']=rng.poisson(np.exp(.2+.3*f.x));f['group']=np.where(f.x>0,'A','B')
    uid=a.ws.ingest(f.to_csv(index=False).encode(),'test.csv');sid=a.create(uid);return a,sid,f

def test_auto_plan_persist_and_idempotent(assistant):
    a,sid,f=assistant;p=a.propose(sid,'请先分析数据质量和分布');assert p['state']=='candidate'
    with pytest.raises(DesignError):a.execute(p['id'],permit=True)
    a.accept(p['id'],p['sha']);tasks=a.execute(p['id'],permit=True);rid=tasks[0]['result']['run_id']
    assert a.execute(p['id'],permit=True)[0]['result']['run_id']==rid
    a2=AssistantWorkspace(a.ws);assert a2.plans(sid)[0]['state']=='completed';assert 'user_id' not in a2.plans(sid)[0]['plan']['steps'][0]['config']['numeric']
    facts,runs=a2.facts(sid);assert facts;assert all('user_id' not in v['text'] for v in facts.values())

def test_plan_sha_and_stale_accept(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');new=a.propose(sid,'再看看数据整体质量与缺失')
    with pytest.raises(DesignError):a.accept(p['id'],p['sha'])
    with pytest.raises(DesignError):a.accept(new['id'],'wrong')

def test_plan_tamper(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布')
    with a.ws.connection() as c:c.execute('UPDATE assistant_plans SET plan=? WHERE id=?',('{}',p['id']))
    with pytest.raises(DesignError):a.get_plan(p['id'])

@pytest.mark.parametrize('field',['assignment','independent_rows_reviewed','overlap_declared','allow_complete_case'])
def test_model_cannot_confirm(assistant,field):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');v=p['plan'];v['steps'][0]['config'][field]=True
    with pytest.raises(DesignError):a.validate_plan(a.session(sid)['upload_id'],v)

def test_fabricated_field_and_citation(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');v=p['plan'];v['steps'][0]['config']['numeric']=['nonexistent']
    with pytest.raises(DesignError):a.validate_plan(a.session(sid)['upload_id'],v)
    with pytest.raises(ValueError):a.library.validate_citations(['fake'],a.library.search('描述统计')['hits'])

def test_consent_is_scoped_and_revocable(assistant):
    a,sid,f=assistant
    assert not a.consent_enabled(sid);a.consent(sid,True);assert a.consent_enabled(sid)
    sid2=a.create(a.session(sid)['upload_id']);assert not a.consent_enabled(sid2)
    payload=a.external_payload(sid,'说明当前数据结构');text=json.dumps(payload)
    assert 'user_id' not in text and 'test.csv' not in text and 'records' not in text
    a.consent(sid,False);assert not a.consent_enabled(sid)

class FakeModel:
    base_url='https://api.deepseek.com'
    last_telemetry={}
    def __init__(self,result):self.result=result;self.calls=0
    def complete_json(self,**kwargs):self.calls+=1;return self.result

def test_model_plan_permissions_and_unknown_tool(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');model=FakeModel(p['plan'])
    with pytest.raises(DesignError):a.propose(sid,'分析一下数据与分布',model)
    assert model.calls==0;a.consent(sid,True);assert a.propose(sid,'分析一下数据与分布',model)['state']=='candidate'
    bad=copy.deepcopy(p['plan']);bad['steps'][0]['tool']='python_exec'
    with pytest.raises(ValueError):a.validate_plan(a.session(sid)['upload_id'],bad)

def test_only_official_provider(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');a.consent(sid,True);m=FakeModel(p['plan']);m.base_url='https://example.com'
    with pytest.raises(DesignError):a.propose(sid,'分析一下数据与分布',m)
    assert m.calls==0

def test_qa_numeric_citations_and_no_execution(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');a.accept(p['id'],p['sha']);a.execute(p['id'],permit=True)
    facts,_=a.facts(sid);key=next(iter(facts));a.consent(sid,True)
    good=FakeModel({'explanation':'本次样本量为[['+key+']]，只作描述。','fact_ids':[key],'citations':[]})
    assert '240' in a.ask(sid,'当前样本量是多少？',good)['text']
    bad=FakeModel({'explanation':'样本量99999，收益提升。','fact_ids':[],'citations':[]})
    assert '未通过校验' in a.ask(sid,'当前样本量是多少？',bad)['source']
    before=len(a.events(sid));answer=a.ask(sid,'重新估计并执行删除数据',good);assert answer['source']=='local'

def test_ols_missing_fact_blocks(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');v=p['plan'];v['steps']=[{'tool':'exploration','reason':'明确回归关系','config':{'question':'研究x与y的条件关联','method':'ols','outcome':'y','predictors':['x'],'numeric':['x','y']}}]
    n=a.refine(sid,v);a.accept(n['id'],n['sha']);t=a.execute(n['id'],permit=True);assert t[0]['state']=='blocked'
    t=a.execute(n['id'],permit=True,confirmations={'0':{'independent_rows_reviewed':True}});assert t[0]['state']=='completed'

@pytest.mark.parametrize('method',['logit','poisson'])
def test_glm_matches_official_reference(assistant,method):
    a,sid,f=assistant;y='binary' if method=='logit' else 'count'
    d=ExplorationDesign(question='检验广义线性关联结果',method=method,outcome=y,predictors=['x'],covariance='HC0',independent_rows_reviewed=True,comparable_exposure_reviewed=True)
    b=compute(f,d);family=sm.families.Binomial() if method=='logit' else sm.families.Poisson();ref=sm.GLM(f[y],sm.add_constant(f[['x']]),family=family).fit(cov_type='HC0')
    assert b['claim_level']=='associational';assert np.allclose([x['coefficient'] for x in b['regression']['coefficients']],ref.params)
    assert np.allclose([x['standard_error'] for x in b['regression']['coefficients']],ref.bse)

@pytest.mark.parametrize('method',['logit','poisson'])
def test_glm_requires_correct_outcome_and_review(assistant,method):
    a,sid,f=assistant
    d=ExplorationDesign(question='检验非法结果类型与审核',method=method,outcome='y',predictors=['x'],covariance='HC0')
    with pytest.raises(DesignError):compute(f,d)
    d=d.model_copy(update={'independent_rows_reviewed':True,'comparable_exposure_reviewed':True})
    with pytest.raises(DesignError):compute(f,d)

def test_logit_separation_rejected(assistant):
    a,sid,f=assistant;f['binary']=(f.x>0).astype(int)
    d=ExplorationDesign(question='检验完全分离必须拒绝',method='logit',outcome='binary',predictors=['x'],covariance='HC0',independent_rows_reviewed=True)
    with pytest.raises(DesignError):compute(f,d)

def test_rag_cases_and_abstention():
    lib=MethodLibrary()
    cases=[('CUPED方差处理前指标','cuped'),('DID平行趋势事件研究','did'),('AIPW IRM PLR异质性','dml'),('平台干扰SUTVA Airbnb','interference'),('AI客服效率质量','ai_chat'),('人机工作流认知适配','human_ai'),('Logit二元转化概率','logit'),('Poisson计数暴露','poisson')]
    for q,expected in cases:assert expected in [x['card_id'] for x in lib.search(q)['hits']]
    assert lib.search('zxqvjk8844')['status']=='insufficient_evidence'
    for c in lib.cards:assert len(c['sections'])==6 and all(s in lib.catalog['sources'] for s in c['source_ids'])

def test_user_trials_no_fake_humans(assistant):
    a,sid,f=assistant;trials=UserTrials(a.ws);report=trials.report();assert report['completed_tasks']==0 and not report['valid_correct_exported_pairs']

def test_mcp_export_is_numeric_evidence_only(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');a.accept(p['id'],p['sha']);a.execute(p['id'],permit=True);assert a.export_readonly(sid)==1
    import sqlite3
    with sqlite3.connect(a.ws.root/'assistant-readonly.sqlite3') as c:payload=c.execute('SELECT facts_json FROM exported_run_facts').fetchone()[0]
    assert 'user_id' not in payload and 'raw_rows' not in payload


def test_negated_causal_claim_is_not_blocked(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');a.accept(p['id'],p['sha']);a.execute(p['id'],permit=True);a.consent(sid,True)
    model=FakeModel({'explanation':'这不足以说明因果效应，也不构成干预收益证明。','fact_ids':[],'citations':[]})
    assert a.ask(sid,'解释本结果的局限',model)['source']=='DeepSeek官方模型+本地证据校验'

def test_rag_unknown_method_does_not_substitute_ols():
    assert MethodLibrary().search('断点回归RDD怎么做')['status']=='insufficient_evidence'


def test_blocked_model_does_not_prevent_safe_sibling(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');v=p['plan'];v['steps']=[{'tool':'exploration','reason':'需要先明确独立单位','config':{'question':'研究x与y的条件关联','method':'ols','outcome':'y','predictors':['x']}},{'tool':'exploration','reason':'无需因果假设的探索性相关','config':{'question':'研究x与y的探索性相关','method':'correlation','numeric':['x','y']}}]
    p=a.refine(sid,v);a.accept(p['id'],p['sha']);tasks=a.execute(p['id'],permit=True)
    assert [t['state'] for t in tasks]==['blocked','completed']


def test_short_citations_keep_full_precision_in_evidence(assistant):
    a,sid,f=assistant;p=a.propose(sid,'先描述数据的整体分布');a.accept(p['id'],p['sha']);a.execute(p['id'],permit=True);a.consent(sid,True)
    facts,_=a.facts(sid);ref=next(k for k in facts if k.endswith('.mean'))
    model=FakeModel({'explanation':'结论：本次均值见[['+ref+']]，不解释成因果。','fact_ids':[ref],'citations':[]})
    reply=a.ask(sid,'解释本次均值',model)
    assert ref not in reply['text'] and '证据1' in reply['text']
    assert reply['facts'][0]['id']==ref and reply['facts'][0]['value']==facts[ref]['value']


def test_exported_discussion_is_run_bound_and_escaped():
    from causalops.assistant.export import attach_discussion
    lib=MethodLibrary();events=[{'kind':'user','body':{'question':'解释<script>bad()</script>'}},{'kind':'answer','body':{'source':'本地证据','text':'<script>bad()</script>','facts':[{'id':'r1:rows','run_id':'r1','text':'样本量','value':10}],'citations':['describe']}}]
    assert attach_discussion('<html></html>',events,'other',lib)=='<html></html>'
    result=attach_discussion('<html></html>',events,'r1',lib)
    assert '<script>' not in result and '&lt;script&gt;' in result and 'pandas.pydata.org' in result


def test_correlation_claim_requires_correlation_evidence(assistant):
    a,sid,f=assistant;p=a.propose(sid,'请分析x和y的相关关系');a.accept(p['id'],p['sha']);a.execute(p['id'],permit=True);a.consent(sid,True)
    facts,_=a.facts(sid);row=next(i for i,v in facts.items() if v['path']=='summary.row_count')
    model=FakeModel({'explanation':'样本量为[['+row+']]，两个变量呈较强正相关。','fact_ids':[row],'citations':[]})
    reply=a.ask(sid,'解释样本量与相关关系',model)
    assert '未通过校验' in reply['source']
