"""v0.9 contracts, bounded retrieval, real background work and recovery boundaries."""
import copy,json,time,threading
import numpy as np,pandas as pd,pytest
pytest.importorskip('langgraph')
from causalops.application.research_service import ResearchService
from causalops.application.background import BackgroundJobs,ACTIVE
from causalops.application.data_contracts import DataContract
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace,DesignError

@pytest.fixture
def world(tmp_path):
    r=np.random.default_rng(902);n=100
    df=pd.DataFrame({'id':range(n),'x':r.normal(size=n),'g':np.tile([0,1],n//2)})
    df['y']=2+df.x+df.g+r.normal(size=n)
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path)))
    sid=s.create_task(payload=df.to_csv(index=False).encode(),name='synthetic.csv')
    return s,sid,df

def register(s,sid,**kw):
    body=dict(analysis_unit='individual',structure='cross_section',outcome='y',entity='id',predictors=['x'],metric_label='合成结果',metric_unit='单位',metric_kind='continuous',method_facts={'ols':{'independent_rows_reviewed':True}})
    body.update(kw);old=s.contracts.latest(sid)
    return s.contracts.save(sid,body,expected_sha=old['sha'] if old else None,human_confirmed=True)

def approve(s,f,**kw):
    p=s.a.get_plan(f['plan_id'])
    return s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,**kw)

def wait(jobs,jid):
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        j=jobs.job(jid)
        if j['status'] not in ACTIVE:return j
        time.sleep(.03)
    pytest.fail('Background job did not finish')

@pytest.mark.parametrize('confirmed',[False,None,1,'true'])
def test_contract_requires_strict_human(world,confirmed):
    s,sid,_=world
    with pytest.raises(DesignError):s.contracts.save(sid,{},human_confirmed=confirmed)
    assert not s.contracts.latest(sid)

@pytest.mark.parametrize('bad',[{'outcome':'absent'},{'outcome':'g','treatment':'g'},{'fields':[{'field':'x'},{'field':'x'}]},{'method_facts':{'ols':{'independent_rows_reviewed':'true'}}},{'method_facts':{'ols':{'outcome':'y'}}},{'notes':'sk-'+('dummycredential'*2)}])
def test_contract_rejects_invalid_or_sensitive(world,bad):
    s,sid,_=world
    with pytest.raises(ValueError):register(s,sid,**bad)


def test_version_optimism_immutability_and_noop(world):
    s,sid,_=world;v1=register(s,sid);assert register(s,sid)['id']==v1['id']
    with pytest.raises(DesignError):s.contracts.save(sid,{},expected_sha='stale',human_confirmed=True)
    v2=register(s,sid,notes='新确认的口径说明')
    assert v2['version']==2 and s.contracts.versions(sid)[1]['sha']==v1['sha']


def test_declared_facts_prefill_not_automatic_approval(world):
    s,sid,_=world;register(s,sid);f=s.start(sid,'使用OLS分析当前结果与x的关联',mode='plan')
    assert f['status']=='awaiting_review' and not s.a.completed_runs(sid)
    assert s.a.get_plan(f['plan_id'])['plan']['steps'][0]['config']['method']=='ols'
    approve(s,f,use_contract_facts=True);assert len(s.a.completed_runs(sid))==1


def test_contract_change_blocks_prior_approval(world):
    s,sid,_=world;register(s,sid);f=s.start(sid,'使用OLS分析当前结果与x的关联',mode='plan')
    approve(s,f,use_contract_facts=True,dispatch=False);register(s,sid,notes='变更口径')
    with pytest.raises(DesignError,match='字典'):s.gateway.execute(f['id'])
    assert not s.a.completed_runs(sid)


def test_contract_fact_conflict_requires_new_version(world):
    s,sid,_=world;register(s,sid);f=s.start(sid,'使用OLS分析当前结果与x的关联',mode='plan')
    with pytest.raises(DesignError,match='冲突'):approve(s,f,confirmations={'0':{'independent_rows_reviewed':False}})
    assert not s.a.completed_runs(sid)


def test_future_predictor_blocks_execution(world):
    s,sid,_=world;register(s,sid,purpose='predictive',fields=[{'field':'x','timing':'future'}])
    f=s.start(sid,'使用OLS分析当前结果与x的关联',mode='plan')
    with pytest.raises(DesignError,match='未来'):approve(s,f,use_contract_facts=True)
    assert not s.a.completed_runs(sid)


def test_unknown_method_has_no_invented_citations(world):
    s,sid,_=world;f=s.start(sid,'用因果森林自动估计效果',mode='plan')
    assert s.output(f['id'],'method_research')['stop_reason']=='unsupported_method'
    assert not s.output(f['id'],'retrieval')['hits'] and not s.a.plans(sid)


def test_real_method_subgraph_bounded_and_covered(world):
    s,sid,_=world;f=s.start(sid,'DID 平行趋势如何诊断',mode='method')
    advice=s.output(f['id'],'method_research')
    assert 1<=advice['retrieval_passes']<=3 and not advice['coverage_missing_methods']
    assert s.output(f['id'],'retrieval')['hits'] and advice['not_empirical_validation']
    assert any(e['node']=='method_retrieval' for e in s.events(f['id']))
    with s.graph() as graph:assert graph.get_graph(xray=True)


def test_empty_retrieval_stops_without_fabrication(world,monkeypatch):
    from causalops.integrations.method_retriever import MethodRetriever
    s,sid,_=world
    def empty(self,q):return {'hits':[],'knowledge_sha256':s.a.library.digest,'knowledge_version':'fixture','status':'insufficient_evidence'}
    monkeypatch.setattr(MethodRetriever,'search_bundle',empty)
    f=s.start(sid,'请介绍IV工具变量的识别条件',mode='method');advice=s.output(f['id'],'method_research')
    assert advice['retrieval_passes']==2 and advice['stop_reason']=='no_new_evidence'
    assert not s.output(f['id'],'answer')['citations']


def test_background_returns_before_work_and_cancel_resume(world,monkeypatch):
    from causalops.application.research_service import ToolGateway
    s,sid,_=world;register(s,sid);jobs=BackgroundJobs(s)
    j=jobs.submit_start(sid,'使用OLS分析当前结果与x的关联',mode='plan');assert wait(jobs,j['id'])['status']=='waiting_review'
    f=s.flow(j['flow_id']);approve(s,f,use_contract_facts=True,dispatch=False)
    started=threading.Event();release=threading.Event();original=ToolGateway.execute
    def delayed(self,fid):started.set();assert release.wait(15);return original(self,fid)
    monkeypatch.setattr(ToolGateway,'execute',delayed)
    t=time.monotonic();job=jobs.submit(f['id']);assert time.monotonic()-t<2 and started.wait(10)
    with pytest.raises(DesignError,match='后台'):register(s,sid,notes='不能在运行时更改')
    jobs.cancel(f['id'],human_confirmed=True);release.set();assert wait(jobs,job['id'])['status']=='cancelled'
    before=s.a.completed_runs(sid);assert len(before)<=1
    resumed=jobs.resume(f['id'],human_confirmed=True);assert wait(jobs,resumed['id'])['status']=='completed'
    assert len(s.a.completed_runs(sid))==1
    if before:assert s.a.completed_runs(sid)[0]['run_id']==before[0]['run_id']


def test_unapproved_resume_only_returns_to_review(world):
    s,sid,_=world;jobs=BackgroundJobs(s);job=jobs.submit_start(sid,'请描述数据分布',mode='plan');wait(jobs,job['id'])
    resumed=jobs.resume(job['flow_id'],human_confirmed=True);assert wait(jobs,resumed['id'])['status']=='waiting_review'
    assert not s.a.completed_runs(sid)


def test_reconcile_never_steals_alive_owner(world):
    from causalops.assistant.runtime import process_birth
    import os,uuid
    s,sid,_=world;jobs=BackgroundJobs(s);f=s.begin(sid,'查看数据结构',mode='profile');jid=uuid.uuid4().hex
    with s.ws.connection() as c:c.execute('INSERT INTO workflow_jobs(id,flow_id,session_id,status,owner_pid,owner_birth,created) VALUES(?,?,?,?,?,?,?)',(jid,f['id'],sid,'running',os.getpid(),process_birth(os.getpid()),'fixture'))
    assert jobs.reconcile(sid)==[]
    with pytest.raises(DesignError,match='原任务'):jobs.resume(f['id'],human_confirmed=True)


def test_dead_worker_can_resume_without_credential_storage(world):
    import uuid
    s,sid,_=world;jobs=BackgroundJobs(s);f=s.begin(sid,'查看数据结构',mode='profile');jid=uuid.uuid4().hex
    with s.ws.connection() as c:c.execute('INSERT INTO workflow_jobs(id,flow_id,session_id,status,owner_pid,owner_birth,created) VALUES(?,?,?,?,?,?,?)',(jid,f['id'],sid,'running',99999999,'missing','fixture'))
    assert jobs.reconcile(sid)==[jid]
    result=jobs.resume(f['id'],human_confirmed=True);assert wait(jobs,result['id'])['status']=='completed'
    assert not s.a.completed_runs(sid)


def test_logit_is_invariant_to_predictor_units():
    from causalops.general.exploration import ExplorationDesign,compute
    rng=np.random.default_rng(998);x=rng.normal(size=800);p=1/(1+np.exp(-(.3+.8*x)))
    frame=pd.DataFrame({'x':x,'tiny':x/10000,'y':rng.binomial(1,p)})
    opts=dict(question='核对变量单位变化不应改变拟合',method='logit',outcome='y',covariance='HC0',independent_rows_reviewed=True)
    a=compute(frame,ExplorationDesign(**opts,predictors=['x']))['regression']
    b=compute(frame,ExplorationDesign(**opts,predictors=['tiny']))['regression']
    assert b['coefficients'][1]['coefficient']/10000==pytest.approx(a['coefficients'][1]['coefficient'])
    assert b['coefficients'][1]['exp_coefficient'] is None


def test_background_queue_bound_and_queued_cancel(world,monkeypatch):
    s,sid,_=world;jobs=BackgroundJobs(s);release=threading.Event();started=threading.Event();original=ResearchService.decide_route
    def slow(self,*args):started.set();assert release.wait(15);return original(self,*args)
    monkeypatch.setattr(ResearchService,'decide_route',slow)
    first=jobs.submit_start(sid,'查看数据概况',mode='profile');assert started.wait(10)
    queued=[jobs.submit_start(sid,'查看数据概况',mode='profile') for _ in range(3)]
    try:
        with pytest.raises(DesignError,match='四项'):jobs.submit_start(sid,'查看数据概况',mode='profile')
        for j in queued:jobs.cancel(j['flow_id'],human_confirmed=True);assert jobs.job(j['id'])['status']=='cancelled'
    finally:release.set()
    assert wait(jobs,first['id'])['status']=='completed'
    assert not s.a.completed_runs(sid)


def test_explicit_method_never_silently_replaced(world):
    s,sid,_=world
    with pytest.raises(DesignError,match='不会静默'):s.start(sid,'请使用ab_test评估当前表',mode='plan')
    assert not s.a.plans(sid)


def test_method_scope_model_cannot_add_unsolicited_analysis(world):
    s,sid,_=world
    class M:
        base_url='https://api.deepseek.com';last_telemetry={}
        def __init__(self):self.calls=0
        def complete_json(self,**kw):
            self.calls+=1
            return {'objective':'仅制定描述统计计划','steps':[{'tool':'exploration','config':{'method':'correlation' if self.calls==1 else 'descriptive','question':'检查当前数据的分布和缺失情况','numeric':['x','y']},'reason':'只分析已请求内容'}],'citations':['describe']}
    model=M();s.a.consent(sid,True)
    p=s.a.propose(sid,'仅做描述统计，不要额外分析',model,guidance={'candidate_methods':['descriptive']})
    assert model.calls==2 and p['plan']['steps'][0]['config']['method']=='descriptive'
    assert not s.a.completed_runs(sid)


@pytest.mark.parametrize('stop',['coverage_complete','retrieval_budget'])
def test_supplementary_retrieval_has_explicit_stop(world,monkeypatch,stop):
    from causalops.integrations.method_retriever import MethodRetriever
    s,sid,_=world;calls=[]
    # Actual registered source cards, with a deliberately incomplete first retrieval.
    cards={m:s.a.library.search(m,method=m,k=1) for m in ('descriptive','ols','logit','did')}
    def controlled(self,q):
        i=len(calls);calls.append(q)
        if stop=='coverage_complete':return cards['descriptive'] if i==0 else cards['did']
        return cards[('descriptive','ols','logit')[min(i,2)]]
    monkeypatch.setattr(MethodRetriever,'search_bundle',controlled)
    f=s.start(sid,'DID的适用条件',mode='method');advice=s.output(f['id'],'method_research')
    assert advice['stop_reason']==stop and len(calls)==(2 if stop=='coverage_complete' else 3)
    assert not s.a.completed_runs(sid)
