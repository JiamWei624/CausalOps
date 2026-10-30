import json
import numpy as np,pandas as pd,pytest
import statsmodels.api as sm
from scipy.stats import spearmanr
from causalops.general.exploration import ExplorationDesign,ExplorationWorkspace,compute
from causalops.general.exploration_report import render_report
from causalops.general.service import GeneralWorkspace,DesignError,GeneralDesign
from causalops.estimators.aipw import estimate_aipw_ate
from causalops.schemas import CausalSpec
from causalops.identification import route_identification

@pytest.fixture
def f():
    return pd.DataFrame({'x':[1.,2.,3.,4.,100.,np.nan,np.inf],'z':[7.,6.,np.nan,4.,3.,2.,1.],'category':['a','a','b','b','b',None,'a'],'date':['2026-01-01','2026-01-02','bad',None,'2026-02-01','2026-02-02','2026-02-03']})
def test_descriptive_has_no_treatment_or_causal_declarations(f):
    d=ExplorationDesign(question='这张表各字段分布与缺失如何',numeric=['x'],categorical=['category'])
    b=compute(f,d);r=b['summary']['numeric'][0]
    assert b['claim_level']=='descriptive' and 'treatment' not in b['design']
    assert r['finite_n']==5 and r['missing_n']==1 and r['infinite_n']==1
    assert r['mean']==22 and r['median']==3 and r['iqr_flag_n']==1
    assert b['summary']['row_count']==7 and b['summary']['categorical'][0]['complete_frequency_total']==7
    json.dumps(b,allow_nan=False)
def test_frequency_missing_denominator_and_group_summaries(f):
    b=compute(f,ExplorationDesign(question='分类缺失占比和分组情况如何',numeric=['x'],categorical=['category'],group='category'))
    c=b['summary']['categorical'][0];assert c['denominator']==7
    assert sum(r['n'] for r in c['top'])==7
    assert next(r for r in c['top'] if r['is_missing'])['n']==1
    assert len(b['summary']['grouped'])==3

def test_all_missing_no_fake_zero_or_nan():
    b=compute(pd.DataFrame({'x':[np.nan]*4}),ExplorationDesign(question='全部缺失的指标如何进行描述',numeric=['x']))
    assert b['summary']['numeric'][0]['mean'] is None
    assert b['summary']['numeric'][0]['std_ddof1'] is None
    assert not b['summary']['histograms'];json.dumps(b,allow_nan=False)
def test_correlations_are_pairwise_with_recorded_n(f):
    b=compute(f,ExplorationDesign(question='两个指标的相关程度是什么样的',method='correlation',numeric=['x','z']))
    r=b['summary']['correlations'][0];p=f[['x','z']].replace([np.inf,-np.inf],np.nan).dropna()
    assert r['pairwise_n']==4
    assert r['pearson']==pytest.approx(np.corrcoef(p.x,p.z)[0,1])
    assert r['spearman']==pytest.approx(spearmanr(p.x,p.z).statistic)
    assert '未生成' in r['p_values']
def test_constant_correlation_not_fabricated():
    b=compute(pd.DataFrame({'x':[1]*5,'z':range(5)}),ExplorationDesign(question='常量字段应不应该输出相关系数',method='correlation',numeric=['x','z']))
    assert b['summary']['correlations'][0]['pearson'] is None

def test_time_buckets_exclude_unparseable_dates_explicitly(f):
    b=compute(f,ExplorationDesign(question='输入日期的分期均值是怎样变化',numeric=['x'],date='date',frequency='M'))
    assert b['summary']['date_quality']['unusable_rows']==2
    assert len(b['summary']['trend'])==2
    assert b['summary']['trend'][0]['mean']==1.5

def test_roles_and_nonnumeric_are_blocked(f):
    with pytest.raises(DesignError):compute(f,ExplorationDesign(question='分类字段不能误作为数值字段',numeric=['category']))
    with pytest.raises(DesignError):compute(f,ExplorationDesign(question='没有分析字段不应直接生成报告'))

@pytest.fixture
def regression():
    rng=np.random.default_rng(6619);x=rng.normal(size=150);y=3+2*x+rng.normal(size=150)
    return pd.DataFrame({'x':x,'y':y,'id':np.repeat(np.arange(30),5),'time':pd.date_range('2025-01-01',periods=150)})
def rd(**kwargs):return ExplorationDesign(question='数值结果与特征之间线性关联如何',method='ols',outcome='y',predictors=['x'],**kwargs)
def test_hc3_matches_official_model_and_is_not_causal(regression):
    b=compute(regression,rd(independent_rows_reviewed=True));ref=sm.OLS(regression.y,sm.add_constant(regression[['x']])).fit(cov_type='HC3')
    row=b['regression']['coefficients'][1]
    assert row['coefficient']==pytest.approx(ref.params['x']) and row['standard_error']==pytest.approx(ref.bse['x'])
    assert b['claim_level']=='associational'
def test_hac_time_sort_matches_official(regression):
    d=rd(covariance='HAC',date='time',maxlags=2);b=compute(regression.sample(frac=1,random_state=4),d)
    ref=sm.OLS(regression.y,sm.add_constant(regression[['x']])).fit(cov_type='HAC',cov_kwds={'maxlags':2,'use_correction':True})
    assert b['regression']['coefficients'][1]['standard_error']==pytest.approx(ref.bse['x'])
def test_cluster_matches_and_small_cluster_refused(regression):
    b=compute(regression,rd(covariance='cluster',cluster='id'));ref=sm.OLS(regression.y,sm.add_constant(regression[['x']])).fit(cov_type='cluster',cov_kwds={'groups':regression.id,'use_correction':True})
    assert b['regression']['coefficients'][1]['standard_error']==pytest.approx(ref.bse['x'])
    with pytest.raises(DesignError,match='20'):compute(regression.assign(id=1),rd(covariance='cluster',cluster='id'))
def test_regression_independence_missing_and_rank_are_not_silently_assumed(regression):
    with pytest.raises(DesignError,match='行独立'):compute(regression,rd())
    missing=regression.copy();missing.loc[0,'y']=np.nan
    with pytest.raises(DesignError,match='缺失'):compute(missing,rd(independent_rows_reviewed=True))
    b=compute(missing,rd(independent_rows_reviewed=True,allow_complete_case=True));assert b['regression']['excluded_complete_case_rows']==1
    const=regression.assign(x=1)
    with pytest.raises(DesignError,match='不满秩'):compute(const,rd(independent_rows_reviewed=True))
def test_immutable_exploration_restore_and_tamper(tmp_path,f):
    w=GeneralWorkspace(tmp_path);uid=w.ingest(f.to_csv(index=False).encode(),'new.csv');ex=ExplorationWorkspace(w)
    d=ExplorationDesign(question='没有处理组也可以描述分布情况',numeric=['x']);sid,v=ex.save(uid,d);b=ex.run(sid,v)
    restored=ExplorationWorkspace(GeneralWorkspace(tmp_path));assert restored.load(b['run_id'])==b
    _,v2=ex.save(uid,d.model_copy(update={'numeric':['z']}),sid)
    assert v2==2
    with pytest.raises(DesignError,match='变化'):ex.run(sid,v)
    assert ex.load(b['run_id'])==b
    p=tmp_path/'exploration-runs'/sid/(b['run_id']+'.json');p.write_text('{}')
    with pytest.raises(DesignError,match='哈希'):ex.load(b['run_id'])
def test_report_escapes_user_input(tmp_path,f):
    w=GeneralWorkspace(tmp_path);uid=w.ingest(f.to_csv(index=False).encode(),'new.csv');ex=ExplorationWorkspace(w);d=ExplorationDesign(question='测试<script>alert(7)</script>字段处理',numeric=['x']);sid,v=ex.save(uid,d)
    report=render_report(ex.run(sid,v));assert '<script>alert(7)</script>' not in report and '&lt;script&gt;' in report

def test_aipw_reproducible_score_and_synthetic_effect():
    rng=np.random.default_rng(41236);n=700;x=rng.normal(size=n);t=rng.binomial(1,1/(1+np.exp(-.4*x)));y=.7*x+t*(1.6+.2*x)+rng.normal(0,.4,n)
    f=pd.DataFrame({'x':x,'t':t,'y':y,'id':range(n)});spec=CausalSpec(question='交叉拟合AIPW能否恢复合成平均效应',analysis_unit='person',treatment='t',outcome='y',covariates=['x'],entity_id_column='id',candidate_methods=['aipw'],assignment_mechanism='observational',positivity_plausible=True,identification_assumptions=['conditional exchangeability'])
    assert route_identification(spec).status.value=='pass'
    a=estimate_aipw_ate(f,spec);b=estimate_aipw_ate(f,spec)
    assert a.estimate.estimate==pytest.approx(b.estimate.estimate,abs=1e-12)
    assert abs(a.estimate.estimate-1.6)<.25
    assert a.evidence['score_recomputed_mean']==pytest.approx(a.estimate.estimate,abs=1e-10)
    assert a.estimate.confidence_interval[0]<a.estimate.confidence_interval[1]
    with pytest.raises(ValueError,match='独立实体'):estimate_aipw_ate(f.assign(id=1),spec)
    assert route_identification(spec.model_copy(update={'identification_assumptions':[]})).status.value=='needs_review'
def test_exploration_ui_save_opens_saved_record_and_preserves_group(tmp_path,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('CAUSALOPS_HOME',str(tmp_path/'home'))
    w=GeneralWorkspace(tmp_path/'home');uid=w.ingest(pd.DataFrame({'x':[1,2,3,4],'g':['a','a','b','b']}).to_csv(index=False).encode(),'small.csv')
    app=AppTest.from_file(str(Path(__file__).parents[1]/'src/causalops/ui/workbench.py'));app.query_params['route']='analysis';app.run(timeout=30)
    next(r for r in app.radio if r.label=='分析任务类型').set_value('descriptive').run(timeout=30)
    next(x for x in app.selectbox if x.label=='或选择已导入的本地表').select(uid).run(timeout=30)
    next(x for x in app.text_area if x.label=='本次分析问题').input('这张小表的分组分布和均值是多少').run(timeout=30)
    next(x for x in app.multiselect if x.label=='数值字段（不自动把ID当作指标）').set_value(['x']).run(timeout=30)
    next(x for x in app.selectbox if x.label=='分组字段（可选，最多50类）').select('g').run(timeout=30)
    next(x for x in app.button if x.label=='保存分析配置').click().run(timeout=30)
    assert not app.exception
    assert any(x.value=='2. 核对并运行已保存配置' for x in app.subheader)
    saved=ExplorationWorkspace(w).studies('descriptive')[0];assert saved['design'].group=='g'
    next(x for x in app.button if x.label=='运行已保存分析').click().run(timeout=30)
    assert not app.exception and any(x.value=='3. 分析结果、图表与结论' for x in app.subheader)
    ex=ExplorationWorkspace(w);assert len(ex.load(ex.runs(saved['study_id'])[0])['summary']['grouped'])==2


def test_same_title_records_have_distinct_ui_labels(tmp_path,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('CAUSALOPS_HOME',str(tmp_path/'home'));w=GeneralWorkspace(tmp_path/'home');ex=ExplorationWorkspace(w)
    uid=w.ingest(pd.DataFrame({'x':[1,2,3]}).to_csv(index=False).encode(),'same.csv');d=ExplorationDesign(question='相同标题也必须恢复到正确的分析记录',numeric=['x'])
    first,_=ex.save(uid,d);second,_=ex.save(uid,d)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'src/causalops/ui/workbench.py'));app.query_params['route']='analysis';app.run(timeout=30)
    next(r for r in app.radio if r.label=='分析任务类型').set_value('descriptive').run(timeout=30)
    next(r for r in app.radio if r.label=='分析记录').set_value('恢复已保存分析').run(timeout=30)
    selection=next(x for x in app.selectbox if x.label=='选择已保存分析')
    assert len(selection.options)==len(set(selection.options))==2
    selection.select(second).run(timeout=30)
    next(x for x in app.button if x.label=='运行已保存分析').click().run(timeout=30)
    assert len(ex.runs(second))==1 and len(ex.runs(first))==0
