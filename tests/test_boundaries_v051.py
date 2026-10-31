from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from scipy.stats import chi2
from causalops.advanced.service import AdvancedDesign,estimate
from causalops.advanced.presentation import report
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.knowledge.retrieval import MethodLibrary


def iv_case(cluster=False):
    rng=np.random.default_rng(172);n=1200;z=rng.normal(size=(n,2));x=rng.normal(size=n);u=rng.normal(size=n);d=.6*z[:,0]+.4*z[:,1]+x+u+rng.normal(size=n)
    f=pd.DataFrame(dict(y=2*d+x+u+rng.normal(size=n)*(1+abs(z[:,0])),d=d,z=z[:,0],z2=z[:,1],x=x,cluster=np.repeat(np.arange(120),10)))
    c=dict(method='iv_2sls',question='预定工具与已知合成结构的效应检验',outcome='y',treatment='d',instruments=['z','z2'],covariates=['x'],ar_null=2.,independent_units_reviewed=True,instrument_exogeneity_reviewed=True,exclusion_reviewed=True,no_interference_reviewed=True,covariates_pre_reviewed=True,design_evidence='已知合成结构与独立工具，控制在处理前生成，不存在工具直接通路。')
    if cluster:c['cluster']='cluster'
    return f,c


def fuzzy_case(reverse=False):
    r=np.random.default_rng(181);n=3500;x=r.uniform(-2,2,n);prob=np.where(x>=0,.8,.2)
    if reverse:prob=1-prob
    d=r.binomial(1,prob);f=pd.DataFrame(dict(x=x,d=d,y=2*d+.3*x+r.normal(scale=.3,size=n)))
    c=dict(method='rd_fuzzy',question='预先确定阈值下不完全遵从的局部效应',outcome='y',running='x',treatment='d',independent_units_reviewed=True,continuity_reviewed=True,no_manipulation_reviewed=True,threshold_rule_reviewed=True,no_interference_reviewed=True,exclusion_reviewed=True,monotonicity_reviewed=True,design_evidence='阈值仅改变二元处理概率，统一潜在随机数实现单调遵从且无直接结果通路。')
    return f,c


def test_robust_ar_against_independent_sandwich_formula():
    f,c=iv_case();b=estimate(f,AdvancedDesign(**c));w=np.column_stack([np.ones(len(f)),f.x,f.z,f.z2]);y=f.y.to_numpy()-2*f.d.to_numpy();inv=np.linalg.inv(w.T@w);beta=inv@w.T@y;u=y-w@beta
    covariance=inv@(w.T@(u[:,None]**2*w))@inv*len(f)/(len(f)-w.shape[1]);v=beta[-2:];stat=float(v @ np.linalg.solve(covariance[-2:,-2:],v))
    assert b['ar_test']['statistic']==pytest.approx(stat,rel=1e-10)
    assert b['ar_test']['p_value']==pytest.approx(chi2.sf(stat,2));assert b['ar_test']['null_effect']==2
    assert '置信区间' not in b['ar_test'].get('status','')


def test_cluster_ar_matches_explicit_official_wald():
    import statsmodels.api as sm
    f,c=iv_case(True);b=estimate(f,AdvancedDesign(**c));w=np.column_stack([np.ones(len(f)),f.x,f.z,f.z2]);m=sm.OLS(f.y-2*f.d,w).fit(cov_type='cluster',cov_kwds={'groups':f.cluster,'use_correction':True},use_t=False)
    restrictions=np.array([[0,0,1,0],[0,0,0,1]]);t=m.wald_test(restrictions,use_f=False,scalar=True)
    assert b['ar_test']['p_value']==pytest.approx(float(t.pvalue));assert b['ar_test']['covariance']=='cluster'


def test_fuzzy_matches_official_estimate_and_uncertainty():
    from rdrobust import rdrobust
    f,c=fuzzy_case();b=estimate(f,AdvancedDesign(**c));official=rdrobust(f.y,f.x,fuzzy=f.d,c=0,p=1,q=2,kernel='tri',masspoints='adjust',bwselect='mserd')
    assert b['estimate']==pytest.approx(float(official.coef.loc['Robust'].iloc[0]));assert b['ci95']==pytest.approx(official.ci.loc['Robust'].tolist());assert abs(b['estimate']-2)<.3
    assert b['claim']=='local_fuzzy_rd_under_declared_assumptions';assert b['treatment_jump']['ci95'][0]>0


def test_predefined_bandwidths_match_direct_official_calls():
    from rdrobust import rdrobust
    f,c=fuzzy_case();b=estimate(f,AdvancedDesign(**c));assert [x['bandwidth_scale'] for x in b['bandwidth_sensitivity']]==[.75,1.,1.25]
    for row in b['bandwidth_sensitivity']:
        assert row['status']=='computed'
        o=rdrobust(f.y,f.x,fuzzy=f.d,c=0,p=1,q=2,kernel='tri',masspoints='adjust',h=[row['h_left'],row['h_right']],b=[row['b_left'],row['b_right']])
        assert row['estimate']==pytest.approx(float(o.coef.loc['Robust'].iloc[0]));assert row['ci95_low']==pytest.approx(float(o.ci.loc['Robust'].iloc[0]))


def test_reverse_probability_jump_does_not_get_local_causal_label():
    f,c=fuzzy_case(True);b=estimate(f,AdvancedDesign(**c));assert b['claim']=='associational';assert not b['treatment_jump']['positive_jump_precisely_estimated'];assert '仅作关联' in b['conclusion']


@pytest.mark.parametrize('fault',['no_treatment','continuous_treatment','unreviewed_exclusion','unreviewed_monotonicity'])
def test_fuzzy_invalid_design_is_blocked(fault):
    f,c=fuzzy_case()
    if fault=='no_treatment':c['treatment']=None
    if fault=='continuous_treatment':f['d']=f.x
    if fault=='unreviewed_exclusion':c['exclusion_reviewed']=False
    if fault=='unreviewed_monotonicity':c['monotonicity_reviewed']=False
    with pytest.raises(DesignError):estimate(f,AdvancedDesign(**c))


def test_split_entity_clusters_rejected():
    f,c=iv_case(True);f['entity']=np.repeat(np.arange(60),20);c['entity']='entity'
    with pytest.raises(DesignError,match='跨越'):estimate(f,AdvancedDesign(**c))


def test_new_diagnostics_have_run_bound_references(tmp_path):
    f,c=iv_case();facts={k:c.pop(k) for k in list(c) if k.endswith('_reviewed') or k=='design_evidence'};a=AssistantWorkspace(GeneralWorkspace(tmp_path));uid=a.ws.ingest(f.to_csv(index=False).encode(),'synthetic.csv');sid=a.create(uid);hits=a.library.search('工具变量',method='iv_2sls');p=a.store_plan(sid,dict(objective=c['question'],steps=[dict(tool='advanced',config=c,reason='预定工具的效应估计与原假设检验')],citations=[hits['hits'][0]['card_id']]),'local',c['question'],hits);a.accept(p['id'],p['sha']);t=a.execute(p['id'],permit=True,confirmations={'0':facts});assert t[0]['state']=='completed'
    catalog,runs=a.facts(sid);ar=[v for v in catalog.values() if v['path']=='ar_test.p_value'];assert len(ar)==1;assert ar[0]['run_id']==t[0]['result']['run_id']


def test_fuzzy_has_retrievable_source_and_report_boundaries():
    lib=MethodLibrary();hit=lib.search('模糊断点不完全遵从',method='rd_fuzzy');assert hit['hits'][0]['card_id']=='rd_fuzzy';assert hit['hits'][0]['sources']
    f,c=fuzzy_case();b=estimate(f,AdvancedDesign(**c));b.update(run_id='b'*32,design={'cutoff':0});s=report(b)
    for text in ['主要结论','识别诊断','预定带宽敏感性','解释范围','弱第一阶段','复现记录']:assert text in s
    assert '把问题交给助手' not in s


@pytest.mark.parametrize('method',['rd_sharp','rd_fuzzy'])
def test_actual_treatment_cannot_be_used_as_covariate(method):
    f,c=fuzzy_case();c.update(method=method,covariates=['d'],covariates_pre_reviewed=True)
    with pytest.raises(DesignError,match='实际处理变量'):estimate(f,AdvancedDesign(**c))
