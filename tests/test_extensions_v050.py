from __future__ import annotations
import json
import numpy as np
import pandas as pd
import pytest
from causalops.advanced.service import AdvancedDesign,AdvancedWorkspace,estimate,FACT_FIELDS
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.assistant.service import AssistantWorkspace
from causalops.knowledge.retrieval import MethodLibrary

@pytest.fixture
def iv():
    r=np.random.default_rng(124);n=900;z=r.normal(size=n);u=r.normal(size=n);x=r.normal(size=n);d=.8*z+.2*x+u+r.normal(size=n)
    f=pd.DataFrame(dict(z=z,d=d,x=x,y=2*d+.4*x+u+r.normal(size=n)))
    cfg=dict(method='iv_2sls',question='合成结构方程的工具变量试验',outcome='y',treatment='d',instruments=['z'],covariates=['x'])
    facts=dict(independent_units_reviewed=True,instrument_exogeneity_reviewed=True,exclusion_reviewed=True,no_interference_reviewed=True,covariates_pre_reviewed=True,design_evidence='已知合成结构方程，工具独立生成且没有直接结果通路。')
    return f,cfg,facts
@pytest.fixture
def rd():
    r=np.random.default_rng(13);x=r.uniform(-2,2,1300);f=pd.DataFrame(dict(x=x,y=.3*x+2*(x>=0)+r.normal(size=len(x))))
    return f,dict(method='rd_sharp',question='预定阈值的局部结果跳跃分析',outcome='y',running='x'),dict(independent_units_reviewed=True,continuity_reviewed=True,no_manipulation_reviewed=True,threshold_rule_reviewed=True,no_interference_reviewed=True,design_evidence='运行变量连续随机生成，已知零阈值及潜在结果连续规则。')
@pytest.fixture
def staggered():
    r=np.random.default_rng(4);rows=[]
    for i in range(180):
        g=3 if i<60 else 5 if i<120 else np.nan;a=r.normal()
        for t in range(1,8):rows.append((i,t,g,a+t*.3+2*(t>=g)+r.normal(scale=.3)))
    f=pd.DataFrame(rows,columns=['id','t','g','y'])
    return f,dict(method='staggered_did',question='合成两批次处理的动态结果分析',outcome='y',entity='id',time='t',cohort='g'),dict(independent_units_reviewed=True,parallel_reviewed=True,no_anticipation_reviewed=True,no_interference_reviewed=True,design_evidence='合成数据共享时间趋势，个体独立且首次处理后持续处理。')

def test_iv_matches_official(iv):
    from linearmodels.iv import IV2SLS
    f,c,h=iv;b=estimate(f,AdvancedDesign(**c,**h));r=IV2SLS(f.y,pd.DataFrame({'const':1.,'x':f.x}),f[['d']],f[['z']]).fit(cov_type='robust',debiased=True)
    assert b['estimate']==pytest.approx(r.params.d,abs=1e-12);assert b['ci95']==pytest.approx(r.conf_int().loc['d'].tolist());assert abs(b['estimate']-2)<.2
    assert 'F' not in b['diagnostics'][0]['note'] or '不能' in b['diagnostics'][0]['note']
def test_rd_matches_robust_row(rd):
    from rdrobust import rdrobust
    f,c,h=rd;b=estimate(f,AdvancedDesign(**c,**h));r=rdrobust(f.y,f.x,c=0,p=1,q=2,bwselect='mserd',kernel='tri',masspoints='adjust')
    assert b['estimate']==pytest.approx(float(r.coef.loc['Robust'].iloc[0]));assert b['std_error']==pytest.approx(float(r.se.loc['Robust'].iloc[0]));assert abs(b['estimate']-2)<.5
@pytest.mark.parametrize('control',['never_treated','not_yet_treated'])
def test_staggered_matches_official(staggered,control):
    from differences import ATTgt
    f,c,h=staggered;c={**c,'control_group':control};b=estimate(f,AdvancedDesign(**c,**h))
    a=ATTgt(f.rename(columns={'id':'entity','t':'period','g':'cohort','y':'outcome'}).set_index(['entity','period']),'cohort',base_period='universal');a.fit('outcome',control_group=control,est_method='reg',progress_bar=False);s=a.aggregate('simple')
    assert b['estimate']==pytest.approx(float(s.iloc[0,0]));assert abs(b['estimate']-2)<.15;assert b['pretrend']['status']=='diagnostic_only';assert b['group_time'];assert b['event_study']
@pytest.mark.parametrize('fixture',['iv','rd','staggered'])
def test_no_assumptions_no_run(request,fixture):
    f,c,h=request.getfixturevalue(fixture)
    with pytest.raises(DesignError):estimate(f,AdvancedDesign(**c))
def test_no_rank_or_missing_silent(iv):
    f,c,h=iv;f.loc[0,'y']=np.nan
    with pytest.raises(DesignError,match='缺失'):estimate(f,AdvancedDesign(**c,**h))
    b=estimate(f,AdvancedDesign(**c,**h,allow_complete_case=True));assert b['excluded_rows']==1
    f['z']=f['x']
    with pytest.raises(DesignError,match='满秩'):estimate(f.dropna(),AdvancedDesign(**c,**h))
def test_rd_fuzzy_and_support_rejected(rd):
    f,c,h=rd;f['d']=np.zeros(len(f));c={**c,'treatment':'d'}
    with pytest.raises(DesignError,match='模糊'):estimate(f,AdvancedDesign(**c,**h))
    f=f[f.x<0]
    with pytest.raises(DesignError):estimate(f,AdvancedDesign(**{k:v for k,v in c.items() if k!='treatment'},**h))
@pytest.mark.parametrize('fault',['duplicate','missing_period','cohort_changes','early','few','timevarying'])
def test_panel_invalid(staggered,fault):
    f,c,h=staggered;f=f.copy()
    if fault=='duplicate':f=pd.concat([f,f.iloc[:1]])
    if fault=='missing_period':f=f.iloc[1:]
    if fault=='cohort_changes':f.loc[0,'g']=4
    if fault=='early':f.loc[f.g==3,'g']=1
    if fault=='few':f=f[f.id<130]
    if fault=='timevarying':f['x']=f.t;c={**c,'covariates':['x']};h={**h,'covariates_pre_reviewed':True}
    with pytest.raises(DesignError):estimate(f,AdvancedDesign(**c,**h))
def test_pretrends_demote(staggered):
    f,c,h=staggered;f=f.copy();f.loc[f.g.notna(),'y']+=f.loc[f.g.notna(),'t']*1.1
    b=estimate(f,AdvancedDesign(**c,**h));assert b['pretrend']['p_value']<.05;assert b['claim']=='associational'
def test_plan_protected_and_evidence_binding(iv,tmp_path):
    f,c,h=iv;a=AssistantWorkspace(GeneralWorkspace(tmp_path));uid=a.ws.ingest(f.to_csv(index=False).encode(),'iv.csv');sid=a.create(uid);lib=a.library.search('iv_2sls',method='iv_2sls');p={'objective':c['question'],'steps':[{'tool':'advanced','config':c,'reason':'官方2SLS，需人工审核工具假设'}],'citations':[v['card_id'] for v in lib['hits']]}
    bad=json.loads(json.dumps(p));bad['steps'][0]['config']['exclusion_reviewed']=True
    with pytest.raises(DesignError):a.store_plan(sid,bad,'model',c['question'],lib)
    plan=a.store_plan(sid,p,'local',c['question'],lib);a.accept(plan['id'],plan['sha']);tasks=a.execute(plan['id'],permit=True);assert tasks[0]['state']=='blocked'
    tasks=a.execute(plan['id'],permit=True,confirmations={'0':h});assert tasks[0]['state']=='completed'
    facts,runs=a.facts(sid);assert any(k.endswith(':estimate') for k in facts);assert a.export_readonly(sid)==1
    rid=runs[0]['run_id'];b=a.advanced.load(rid)
    with a.ws.connection() as conn:conn.execute('UPDATE advanced_runs SET result_json=? WHERE run_id=?',(json.dumps({**b,'estimate':999}),rid))
    with pytest.raises(DesignError,match='指纹'):a.advanced.load(rid)
@pytest.mark.parametrize('q,method',[('工具变量的排除限制与弱工具','iv_2sls'),('断点回归阈值局部估计','rd_sharp'),('交错批次与尚未处理对照','staggered_did')])
def test_method_rag_extended(q,method):
    lib=MethodLibrary();r=lib.search(q,method=method);assert any(method in h['methods'] for h in r['hits']);lib.validate_citations([r['hits'][0]['card_id']],r['hits'])
def test_fulltext_scopes():
    lib=MethodLibrary();sources=[v for v in lib.catalog['sources'].values() if v['access_scope'].startswith('full_text')];assert len(sources)==3;assert all('PDF' in s['locator'] for s in sources);assert lib.search('合成控制')['status']=='insufficient_evidence'
def test_advanced_report_is_offline_and_escaped(iv):
    from causalops.advanced.presentation import report
    f,c,h=iv;b=estimate(f,AdvancedDesign(**c,**h));b['run_id']='a'*32;b['design']={'evidence':'<script>bad</script>'};html=report(b)
    assert 'Plotly.newPlot' in html;assert '&lt;script&gt;bad&lt;/script&gt;' in html;assert '<script>bad</script>' not in html;assert 'cdn.plot.ly' not in html.split('Plotly.newPlot')[0][-100:]
