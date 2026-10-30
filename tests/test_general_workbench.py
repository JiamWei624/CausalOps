import io,json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from causalops.general.service import GeneralWorkspace,GeneralDesign,DesignError,read_table,prepare
from causalops.results.interpretation import MetricDefinition
from causalops.results.qa import ResultQAService

@pytest.fixture
def incoming():
    rng=np.random.default_rng(81927);n=400;t=rng.integers(0,2,n)
    return pd.DataFrame({'score':rng.normal(size=n),'conversion':rng.binomial(1,.15+.1*t),'customer_token':['c'+str(i) for i in range(n)],'variant':np.where(t,'offer','holdout')})
@pytest.fixture
def design():
    return GeneralDesign(question='营销方案是否改变当前窗口的转化概率',analysis_unit='客户',method='ab_test',treatment='variant',control_value='holdout',treated_value='offer',outcome='conversion',entity='customer_token',assignment='randomized',metric=MetricDefinition(label='转化概率',kind='binary',unit='概率',direction='higher_is_better',window='两周'))

def test_unseen_names_csv_full_task_restore_and_qa(tmp_path,incoming,design):
    w=GeneralWorkspace(tmp_path/'arbitrary-home');uid=w.ingest(incoming.to_csv(index=False).encode(),'outside.csv');sid,rev=w.save(uid,design)
    with pytest.raises(DesignError):w.execute(sid,rev.revision_id,reviewed=False)
    result=w.execute(sid,rev.revision_id,reviewed=True,actor='automated_unseen_data_fixture_not_domain_expert')
    b=result.agent_result.bundle;expected=incoming.groupby('variant').conversion.mean()
    assert b.estimate.estimate==pytest.approx(expected['offer']-expected['holdout'])
    restored=GeneralWorkspace(w.root);assert len(restored.runs(sid))==1
    rb,_=restored.bundle(b.run_id);assert rb.model_dump_json()==b.model_dump_json()
    turn=ResultQAService(restored.repo,None).ask(session_id=sid,run_id=b.run_id,question='请解释本次幅度和区间以及结论边界。')
    assert turn['answer']['used_model'] is False and turn['answer']['citation_ids']

def test_data_corruption_blocks(tmp_path,incoming):
    w=GeneralWorkspace(tmp_path);uid=w.ingest(incoming.to_csv(index=False).encode(),'incoming.csv');p=tmp_path/'uploads'/f'{uid}.parquet';p.write_bytes(p.read_bytes()+b'changed')
    with pytest.raises(DesignError,match='哈希'):w.load_upload(uid)

def test_mapping_change_requires_new_version(tmp_path,incoming,design):
    w=GeneralWorkspace(tmp_path);uid=w.ingest(incoming.to_csv(index=False).encode(),'data.csv');sid,r1=w.save(uid,design);w.execute(sid,r1.revision_id,reviewed=True)
    d2=design.model_copy(update={'control_value':'offer','treated_value':'holdout'});_,r2=w.save(uid,d2,sid)
    assert r2.dataset_version_id!=r1.dataset_version_id
    with pytest.raises(DesignError,match='草案已变化'):w.execute(sid,r1.revision_id,reviewed=True)
    assert len(w.runs(sid))==1 and r2.status.value=='pending_review'

def test_exact_saved_design_is_not_duplicated(tmp_path,incoming,design):
    w=GeneralWorkspace(tmp_path);uid=w.ingest(incoming.to_csv(index=False).encode(),'x.csv');sid,r=w.save(uid,design);_,same=w.save(uid,design,sid);assert same.revision_id==r.revision_id

def test_no_positional_field_assumption(incoming,design):
    a,s,_=prepare(incoming,design);b,s2,_=prepare(incoming[list(reversed(incoming.columns))],design)
    assert s==s2 and a['variant'].equals(b['variant'])

def test_multiple_groups_are_not_silently_dropped(incoming,design):
    incoming.loc[0,'variant']='third'
    with pytest.raises(DesignError,match='两个'):prepare(incoming,design)

def test_duplicate_randomization_units_block(incoming,design):
    incoming.loc[1,'customer_token']=incoming.loc[0,'customer_token']
    with pytest.raises(DesignError,match='重复单位'):prepare(incoming,design)

def test_missing_exclusion_requires_explicit_rule(incoming,design):
    incoming.loc[0,'conversion']=np.nan
    with pytest.raises(DesignError,match='排除'):prepare(incoming,design)
    f,_,q=prepare(incoming,design.model_copy(update={'allow_complete_case':True}));assert len(f)==399 and q['explicit_complete_case_exclusions']==1

def test_binary_declaration_mismatch(incoming,design):
    incoming.loc[0,'conversion']=3
    with pytest.raises(DesignError,match='二元'):prepare(incoming,design)

def test_nonrandomized_does_not_execute_ab(tmp_path,incoming,design):
    w=GeneralWorkspace(tmp_path);uid=w.ingest(incoming.to_csv(index=False).encode(),'a.csv');sid,r=w.save(uid,design.model_copy(update={'assignment':'unknown'}))
    with pytest.raises(DesignError,match='识别条件'):w.execute(sid,r.revision_id,reviewed=True)
    assert not w.runs(sid)

def test_zero_variance_not_claimed_significant(incoming,design):
    incoming['conversion']=0
    with pytest.raises(DesignError,match='组内变异'):prepare(incoming,design)

@pytest.mark.parametrize('payload',[b'a,a\n1,2',b',b\n1,2'])
def test_bad_headers(payload):
    with pytest.raises(DesignError,match='列名'):read_table(payload,'bad.csv')

def test_row_limit_and_code_extension():
    with pytest.raises(DesignError):read_table(b'a,b\n1,2\n3,4\n5,6','x.csv',max_rows=2)
    with pytest.raises(DesignError):read_table(b'print(1)','x.py')

def test_parquet_and_csv_use_same_contract(incoming,design):
    buf=io.BytesIO();incoming.to_parquet(buf,index=False);f=read_table(buf.getvalue(),'input.parquet');_,spec,_=prepare(f,design);assert spec.outcome=='conversion'

def test_workspace_path_does_not_depend_on_drive(tmp_path):
    w=GeneralWorkspace(tmp_path/'with space'/'custom');assert w.repo.database_path.is_relative_to(w.root)

def test_observational_regression_remains_association(tmp_path,incoming,design):
    d=design.model_copy(update={'method':'regression_adjustment','assignment':'observational','covariates':['score'],'covariates_reviewed':True})
    w=GeneralWorkspace(tmp_path);uid=w.ingest(incoming.to_csv(index=False).encode(),'obs.csv');sid,r=w.save(uid,d);b=w.execute(sid,r.revision_id,reviewed=True).agent_result.bundle
    assert b.claim_level.value=='associational'
@pytest.mark.parametrize('method',['cuped','psm','ipw','double_ml'])
def test_additional_method_through_generic_contract(tmp_path,incoming,design,method):
    d=design.model_copy(update={'method':method,'assignment':'randomized' if method=='cuped' else 'observational','covariates':['score'],'covariates_reviewed':True,'exchangeability_declared':True,'overlap_declared':True})
    w=GeneralWorkspace(tmp_path/method);uid=w.ingest(incoming.to_csv(index=False).encode(),'new.csv');sid,r=w.save(uid,d)
    b=w.execute(sid,r.revision_id,reviewed=True,actor='automated_fixture_not_expert').agent_result.bundle
    assert np.isfinite(b.estimate.estimate)
    assert b.spec.candidate_methods[0].value==method
    restored,_=GeneralWorkspace(w.root).bundle(b.run_id)
    assert restored.model_dump()==b.model_dump()

@pytest.fixture
def daily():
    rows=[];event=pd.Timestamp('2026-09-15')
    for site in range(8):
        for k in range(-3,4):
            rows.append({'site':str(site),'day':event+pd.Timedelta(days=k),'start':event if site<4 else pd.NaT,'active':int(site<4 and k>=0),'outcome':site+.1*k+int(site<4 and k>=0)})
    return pd.DataFrame(rows)
@pytest.fixture
def daily_design():
    return GeneralDesign(question='政策实施后站点结果是否有差异',analysis_unit='站点日',method='did',treatment='active',control_value='0',treated_value='1',outcome='outcome',entity='site',assignment='observational',time='day',treatment_time='start',pre_days=3,post_days=4,panel_confirmed=True,parallel_declared=True,no_anticipation_declared=True,metric=MetricDefinition(label='站点指标',kind='continuous',unit='分',window='前3后4天'))

def test_daily_window_missing_is_not_filled(daily,daily_design):
    with pytest.raises(DesignError,match='缺日'):prepare(daily.iloc[1:],daily_design)

def test_daily_ever_treated_flag_is_not_post_treatment(daily,daily_design):
    daily['active']=daily.start.notna().astype(int)
    with pytest.raises(DesignError,match='当日'):prepare(daily,daily_design)

def test_staggered_is_blocked(daily,daily_design):
    daily.loc[daily.site=='0','start']=pd.Timestamp('2026-09-16')
    with pytest.raises(DesignError,match='交错'):prepare(daily,daily_design)

def test_intraday_is_not_silently_truncated(daily,daily_design):
    daily['day']=daily.day+pd.Timedelta(hours=1)
    with pytest.raises(DesignError,match='时分秒'):prepare(daily,daily_design)

def test_duplicate_day_is_blocked(daily,daily_design):
    with pytest.raises(DesignError,match='一行'):prepare(pd.concat([daily,daily.iloc[[0]]]),daily_design)
