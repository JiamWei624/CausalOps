import json,copy
import numpy as np,pandas as pd,pytest
from causalops.assistant.service import AssistantWorkspace,PROTECTED,digest
from causalops.assistant.contracts import REGISTRY
from causalops.assistant.runtime import process_birth,alive
from causalops.assistant.observation import EvidenceLoop
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.knowledge.retrieval import MethodLibrary

@pytest.fixture
def task(tmp_path):
    a=AssistantWorkspace(GeneralWorkspace(tmp_path));rng=np.random.default_rng(407);n=180
    f=pd.DataFrame({'user_id':np.arange(n),'x':rng.normal(size=n),'z':rng.normal(size=n),'d':rng.binomial(1,.5,n)})
    f['y']=2*f.x+f.d+rng.normal(size=n)
    uid=a.ws.ingest(f.to_csv(index=False).encode(),'synthetic.csv');sid=a.create(uid)
    return a,sid,f

def done(a,sid,q='请先描述x和y的整体分布'):
    p=a.propose(sid,q);a.accept(p['id'],p['sha']);ts=a.execute(p['id'],permit=True)
    assert all(t['state']=='completed' for t in ts),ts
    return p,ts

@pytest.mark.parametrize('method',list(REGISTRY))
def test_registry_schema_and_tool_agree(task,method):
    a,sid,f=task;s=REGISTRY[method];assert a.tools.method(s.tool,method)==s
    schema=a.tools.schema(method,PROTECTED)
    assert not set(schema['properties'])&PROTECTED
    assert schema['properties']['method']['enum']==[method]
    with pytest.raises(DesignError):a.tools.method('not-a-tool',method)

def test_selected_old_run_no_latest_leak_and_persists(task):
    a,sid,f=task;p1,t1=done(a,sid);r1=t1[0]['result']['run_id'];p2,t2=done(a,sid,'研究x和y的相关关系');r2=t2[-1]['result']['run_id']
    a.select_run(sid,r1);facts,runs=a.facts(sid)
    assert {x['run_id'] for x in facts.values()}=={r1}
    b=AssistantWorkspace(a.ws);assert b.selected_run(sid)==r1
    answer=b.ask(sid,'解释当前样本与均值');assert answer['run_ids']==[r1]
    assert all(x['run_id']==r1 for x in answer['facts'])
    assert r2 not in json.dumps(b.external_payload(sid,'说明本次均值',facts=facts))

def test_cross_session_and_unlisted_run_rejected(task):
    a,sid,f=task;p,t=done(a,sid);rid=t[0]['result']['run_id'];sid2=a.create(a.session(sid)['upload_id'])
    for func in (lambda:a.select_run(sid2,rid),lambda:a.ask(sid2,'解释其他研究的结果',run_id=rid),lambda:a.facts(sid,run_ids=['0'*32])):
        with pytest.raises(DesignError):func()

def test_explicit_comparison_has_only_selected_runs(task):
    a,sid,f=task;_,t1=done(a,sid);r1=t1[0]['result']['run_id'];_,t2=done(a,sid,'研究x和y的相关关系');r2=t2[-1]['result']['run_id']
    answer=a.ask(sid,'比较这些运行的统计口径',compare_run_ids=[r1,r2]);assert set(answer['run_ids'])=={r1,r2};assert answer['scope']=='explicit_comparison'
    from causalops.assistant.export import attach_discussion
    assert attach_discussion('<html></html>',a.events(sid),r1,a.library)=='<html></html>' # no mixed-run appendix

def test_contract_tamper_rejected(task):
    a,sid,f=task;p,t=done(a,sid);row=t[0];ref=row['result'];ref['contract']['result_fingerprint']='bad'
    with a.ws.connection() as c:c.execute('UPDATE assistant_tasks SET result=? WHERE id=?',(json.dumps(ref),row['id']))
    with pytest.raises(DesignError):a.facts(sid)

def test_normal_exception_finishes_attempt_and_retry_bound(task,monkeypatch):
    a,sid,f=task;p=a.propose(sid,'请先描述当前数据的整体分布');a.accept(p['id'],p['sha'])
    def fail(*args,**kwargs):raise KeyError('private-value-must-not-persist')
    monkeypatch.setattr(a.tools,'execute',fail)
    for i in range(3):assert a.execute(p['id'],permit=True)[0]['state']=='blocked'
    with pytest.raises(DesignError):a.execute(p['id'],permit=True)
    t=a.tasks(p['id'])[0];assert 'private-value' not in json.dumps(t)
    assert len(a.runtime.attempts(t['id']))==3
    assert all(x['status']=='blocked' and x['finished'] for x in a.runtime.attempts(t['id']))

def test_cancel_and_explicit_resume(task):
    a,sid,f=task;p=a.propose(sid,'请先描述当前数据的整体分布');a.accept(p['id'],p['sha']);a.cancel(p['id'])
    assert a.execute(p['id'],permit=True)[0]['state']=='cancelled'
    with pytest.raises(DesignError):a.resume(p['id'])
    a.resume(p['id'],permit=True);assert a.execute(p['id'],permit=True)[0]['state']=='completed'

def test_interrupt_after_engine_commit_reconciles_without_rerun(task,monkeypatch):
    a,sid,f=task;p=a.propose(sid,'请先描述当前数据的整体分布');a.accept(p['id'],p['sha']);orig=a.tools.execute
    def crash(*args,**kwargs):orig(*args,**kwargs);raise SystemExit('simulated process exit')
    monkeypatch.setattr(a.tools,'execute',crash)
    with pytest.raises(SystemExit):a.execute(p['id'],permit=True)
    tid=a.tasks(p['id'])[0]['id'];cp=a.runtime.row(tid);assert a.recover(p['id'])==[] # live owner cannot be stolen
    with a.ws.connection() as c:c.execute('UPDATE assistant_checkpoints SET owner_pid=?,owner_birth=? WHERE task_id=?',(2147483646,'absent',tid))
    fixed=a.recover(p['id']);assert fixed[0]['state']=='completed';rid=a.tasks(p['id'])[0]['result']['run_id']
    monkeypatch.setattr(a.tools,'execute',lambda *args:pytest.fail('must reuse persisted result'))
    assert a.execute(p['id'],permit=True)[0]['result']['run_id']==rid
    with a.ws.connection() as c:assert c.execute('SELECT COUNT(*) FROM exploration_runs').fetchone()[0]==1

def test_interrupt_before_compute_resumes_prepared_study(task,monkeypatch):
    a,sid,f=task;p=a.propose(sid,'请先描述当前数据的整体分布');a.accept(p['id'],p['sha']);orig=a.tools.execute
    def crash(*args,**kwargs):raise SystemExit('before compute')
    monkeypatch.setattr(a.tools,'execute',crash)
    with pytest.raises(SystemExit):a.execute(p['id'],permit=True)
    tid=a.tasks(p['id'])[0]['id'];saved=json.loads(a.runtime.row(tid)['checkpoint'])
    with a.ws.connection() as c:c.execute('UPDATE assistant_checkpoints SET owner_pid=?,owner_birth=? WHERE task_id=?',(2147483646,'absent',tid))
    assert a.recover(p['id'])[0]['state']=='interrupted'
    monkeypatch.setattr(a.tools,'execute',orig);ts=a.execute(p['id'],permit=True)
    assert ts[0]['result']['run_id']==saved['run_id']
    with a.ws.connection() as c:assert c.execute('SELECT COUNT(*) FROM exploration_designs').fetchone()[0]==1

def test_fencing_token_and_live_worker(task):
    import os
    a,sid,f=task;p=a.propose(sid,'请先描述当前数据的整体分布');a.accept(p['id'],p['sha']);t=a.tasks(p['id'])[0]
    token,_=a.runtime.claim(t['id'],'fingerprint')
    assert alive(os.getpid(),process_birth(os.getpid()))
    with pytest.raises(DesignError):a.runtime.claim(t['id'],'fingerprint')
    with pytest.raises(DesignError):a.runtime.finish(t['id'],'wrong','completed',{})
    assert a.recover(p['id'])==[]
    a.runtime.finish(t['id'],token,'blocked',{'error':'test'})

def test_observation_local_stops_for_human_and_is_readonly(task):
    a,sid,f=task;p,t=done(a,sid);rid=t[0]['result']['run_id'];before=a.tasks(p['id'])
    out=EvidenceLoop(a).run(sid,'根据此运行说明还有什么研究问题',run_id=rid)
    assert out['stop_reason']=='human_fact_required' and not out['automatic_execution']
    assert a.tasks(p['id'])==before and a.plans(sid)[0]['id']==p['id']

class Actions:
    base_url='https://api.deepseek.com';last_telemetry={}
    def __init__(self,values):self.values=iter(values);self.calls=0
    def complete_json(self,**kwargs):self.calls+=1;return next(self.values)

def test_observation_repeat_and_action_budget(task):
    a,sid,f=task;_,t=done(a,sid);a.consent(sid,True)
    row={'action':'inspect_run','reason':'核对运行证据','query':'','questions':[]};m=Actions([row,row])
    out=EvidenceLoop(a).run(sid,'核对当前运行的分析诊断',model=m)
    assert out['stop_reason']=='repeated_action' and m.calls==2
    with pytest.raises(ValueError):EvidenceLoop(a).run(sid,'核对当前运行的分析诊断',max_steps=4)

def test_observation_cannot_execute_or_approve(task):
    a,sid,f=task;p,t=done(a,sid);a.consent(sid,True)
    row={'action':'execute','reason':'伪造执行','query':'','questions':[]};m=Actions([row,row])
    out=EvidenceLoop(a).run(sid,'核对当前运行的分析诊断',model=m);assert out['stop_reason']=='validation_failed'
    assert a.plans(sid)[0]['id']==p['id']

def test_observation_candidate_permission_required(task):
    a,sid,f=task;p,t=done(a,sid);a.consent(sid,True)
    m=Actions([{'action':'propose_revision','reason':'建议修订','query':'请生成新的描述性计划','questions':[]}])
    out=EvidenceLoop(a).run(sid,'根据本次运行提出后续研究',model=m)
    assert out['stop_reason']=='candidate_permission_required';assert a.plans(sid)[0]['id']==p['id']

def test_context_snapshots_and_rejected_are_not_facts(task):
    a,sid,f=task;p,t=done(a,sid);old=a.propose(sid,'研究x和y的相关关系');a.reject(old['id'])
    facts,_=a.facts(sid);payload=a.external_payload(sid,'说明本次运行的研究依据',facts=facts);ctx=payload['research_context']
    assert 'correlation' in ctx['rejected_methods'];assert ctx['selected_run_ids']==[t[0]['result']['run_id']]
    assert ctx['source_plans'][0]['sha']==p['sha']
    with a.ws.connection() as c:assert c.execute('SELECT COUNT(*) FROM assistant_context_snapshots').fetchone()[0]>0

def test_section_provenance_and_tamper():
    lib=MethodLibrary();r=lib.search('模糊断点的局部效应与处理概率跳跃');assert r['hits'][0]['card_id']=='rd_fuzzy'
    hit=r['hits'][0];assert hit['matched_sections'] and hit['provenance']
    assert lib.validate_citations([hit['card_id']],r['hits'])
    changed=copy.deepcopy(r['hits']);changed[0]['matched_sections'][0]['text']='编造摘录'
    with pytest.raises(ValueError):lib.validate_citations([hit['card_id']],changed)
    changed=copy.deepcopy(r['hits']);changed[0]['knowledge_sha256']='bad'
    with pytest.raises(ValueError):lib.validate_citations([hit['card_id']],changed)
    assert lib.search('任意问题',method='invented')['status']=='insufficient_evidence'

def test_research_adapter_contract_and_selected_evidence(task):
    a,sid,f=task;p=a.propose(sid,'请先描述当前数据的整体分布');v=p['plan'];v['citations']=['ab']
    v['steps']=[{'tool':'research','reason':'固定合成数据的随机实验检验，不代表真实业务收益','config':{'question':'合成实验的处理对结果有何影响','analysis_unit':'synthetic individual','method':'ab_test','treatment':'d','control_value':'0','treated_value':'1','outcome':'y','entity':'user_id','metric':{'label':'合成结果','kind':'continuous','unit':'原单位','direction':'neutral','window':'固定合成窗口'}}}]
    p=a.refine(sid,v);a.accept(p['id'],p['sha']);t=a.execute(p['id'],permit=True,confirmations={'0':{'assignment':'randomized'}})
    assert t[0]['state']=='completed',t
    ref=t[0]['result'];assert ref['contract']['kind']=='research';assert ref['contract']['upload_id']==a.session(sid)['upload_id']
    facts,runs=a.facts(sid);assert facts and {f['run_id'] for f in facts.values()}=={ref['run_id']}
    obs=EvidenceLoop(a).observe(sid,ref['run_id']);assert obs['diagnostics']['diagnostics'] is not None

def test_advanced_adapter_contract_and_resume_receipt(task):
    a,sid,f=task;p=a.propose(sid,'请先描述当前数据的整体分布');v=p['plan'];v['citations']=['iv_2sls']
    v['steps']=[{'tool':'advanced','reason':'仅在固定合成夹具上检查接口与运行证据，不证明真实外生性','config':{'question':'检查合成工具变量模型的结果契约','method':'iv_2sls','outcome':'y','treatment':'d','instruments':['x'],'covariates':['z']}}]
    p=a.refine(sid,v);a.accept(p['id'],p['sha'])
    t=a.execute(p['id'],permit=True,confirmations={'0':{'instrument_exogeneity_reviewed':True,'exclusion_reviewed':True,'no_interference_reviewed':True,'independent_units_reviewed':True,'monotonicity_reviewed':True,'covariates_pre_reviewed':True,'design_evidence':'此为固定合成夹具，仅测试执行接口、契约与恢复记录，不作业务结论。'}})
    assert t[0]['state']=='completed',t
    assert t[0]['result']['contract']['kind']=='advanced';assert a.facts(sid)[0]
    cp=json.loads(a.runtime.row(t[0]['id'])['checkpoint']);assert a.tools.reconcile(a.session(sid)['upload_id'],cp).run_id==t[0]['result']['run_id']

def test_cooperative_cancel_keeps_inflight_receipt(task,monkeypatch):
    a,sid,f=task;p=a.propose(sid,'研究x和y的相关关系');a.accept(p['id'],p['sha']);orig=a.tools.execute
    def cancel_after_result(*args,**kwargs):
        result=orig(*args,**kwargs);a.cancel(p['id']);return result
    monkeypatch.setattr(a.tools,'execute',cancel_after_result);ts=a.execute(p['id'],permit=True)
    assert ts[0]['state']=='completed' and ts[1]['state']=='cancelled';assert ts[0]['result']['run_id']

def test_real_child_process_crash_recovers_committed_result(task):
    import os,subprocess,sys
    a,sid,f=task;p=a.propose(sid,'请先描述当前数据的整体分布');a.accept(p['id'],p['sha'])
    code="""import os,sys
from pathlib import Path
from causalops.general.service import GeneralWorkspace
from causalops.assistant.service import AssistantWorkspace
a=AssistantWorkspace(GeneralWorkspace(Path(sys.argv[1])))
original=a.tools.execute
def crash(*args,**kwargs):
 original(*args,**kwargs)
 os._exit(73)
a.tools.execute=crash
a.execute(sys.argv[2],permit=True)
"""
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1');child=subprocess.run([sys.executable,'-c',code,str(a.ws.root),p['id']],env=env,capture_output=True,timeout=60)
    assert child.returncode==73,child.stderr.decode(errors='replace')
    assert a.tasks(p['id'])[0]['state']=='running'
    assert a.recover(p['id'])[0]['state']=='completed'
    assert a.execute(p['id'],permit=True)[0]['state']=='completed'
    with a.ws.connection() as c:assert c.execute('SELECT COUNT(*) FROM exploration_runs').fetchone()[0]==1

def test_observation_rejects_unverified_numeric_reason(task):
    a,sid,f=task;done(a,sid);a.consent(sid,True)
    row={'action':'finish','reason':'提升了25%，假设已验证','query':'','questions':[]};m=Actions([row,row])
    out=EvidenceLoop(a).run(sid,'复核当前研究的分析诊断',model=m);assert out['stop_reason']=='validation_failed'

def test_observation_shared_budget_includes_proposal_repair(task):
    a,sid,f=task;p,t=done(a,sid);a.consent(sid,True)
    action={'action':'propose_revision','reason':'需要新的待审方案','query':'请描述当前数据的整体分布','questions':[]}
    candidate=copy.deepcopy(p['plan']);candidate['steps'][0]['config']['assignment']='randomized'
    m=Actions([action,candidate,candidate])
    out=EvidenceLoop(a).run(sid,'提出新的研究方案供审核',model=m,allow_candidate=True)
    assert out['stop_reason']=='proposal_validation_failed'
    assert m.calls==3 and a.plans(sid)[0]['id']==p['id']

def test_grouped_schemas_remove_duplicate_prompt_types(task):
    a,sid,f=task;schemas=a.tools.schemas(PROTECTED)
    assert set(schemas)=={'exploration','research','advanced'}
    for kind,config in schemas.items():
        assert config['properties']['method']['enum']==[m for m,s in REGISTRY.items() if s.tool==kind]
        assert not PROTECTED&set(config['properties'])
    assert len(json.dumps(schemas))<len(json.dumps({m:a.tools.schema(m,PROTECTED) for m in REGISTRY}))

def test_export_preserves_original_source_snapshot(task):
    from causalops.assistant.export import attach_discussion
    a,sid,f=task;_,t=done(a,sid);rid=t[0]['result']['run_id'];a.ask(sid,'解释当前结果的统计描述')
    original=copy.deepcopy(a.events(sid));library=MethodLibrary();library.catalog['sources']['pandas']['url']='https://wrong.example/changed'
    text=attach_discussion('<html></html>',original,rid,library)
    assert 'wrong.example' not in text and 'pandas.pydata.org' in text

def test_source_url_tamper_is_rejected():
    lib=MethodLibrary();hits=copy.deepcopy(lib.search('CUPED处理前指标')['hits']);cid=hits[0]['card_id'];hits[0]['sources'][0]['url']='https://wrong.example/fake'
    with pytest.raises(ValueError):lib.validate_citations([cid],hits)

def test_context_defaults_not_presented_as_confirmed_facts(task):
    from causalops.assistant.context import research_context
    a,sid,f=task;_,t=done(a,sid);ctx=research_context(a,sid)
    assert all(v is not False and v!='unknown' for r in ctx['registered_facts'] for v in r['human_registered_flags'].values())
    assert ctx['unresolved_items']==[]

def test_observation_repairs_invalid_numbers_without_executing(task):
    a,sid,f=task;p,t=done(a,sid);a.consent(sid,True)
    m=Actions([{'action':'ask_fact','reason':'存在140行','query':'','questions':[]},{'action':'ask_fact','reason':'请核对指标与观察口径','query':'','questions':['是否已确认分析单位？']}])
    out=EvidenceLoop(a).run(sid,'核对此运行的后续研究事项',model=m)
    assert out['stop_reason']=='human_fact_required' and out['model_calls']==2
    assert a.plans(sid)[0]['id']==p['id'] and not out['automatic_execution']

def test_welch_alias_does_not_confirm_randomization(task):
    a,sid,f=task;hits=a.library.search('Welch两独立样本检验')['hits']
    assert hits[0]['card_id']=='ab'
    p=a.propose(sid,'Welch两独立样本检验，请检查当前数据')
    assert all(not set(s['config'])&PROTECTED for s in p['plan']['steps'])
