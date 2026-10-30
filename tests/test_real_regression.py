from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import statsmodels.formula.api as smf

from causalops.schemas import CausalSpec, CausalMethod, AssignmentMechanism, DataStructure, ClaimLevel
from causalops.estimators.regression import estimate_clustered_regression
from causalops.execution import execute_analysis
from causalops.research import ResearchRepository, RevisionSource, DraftStatus, ResearchStateError
from causalops.ui.controller import run_versioned_association_workflow
from causalops.real_data import horizon_label
from causalops.metadata.field_catalog import build_field_catalog
from causalops.results.qa import ResultQAService


def fixture():
    rng=np.random.default_rng(921)
    n=1200
    df=pd.DataFrame({'user_id':np.repeat(np.arange(300),4).astype(str),
                     'month':rng.choice(['a','b','c','d'],n),'region':rng.choice(['x','y','z'],n),
                     'treated':rng.binomial(1,.4,n),'x':rng.normal(size=n)})
    df['y']=.3*df.treated+.2*df.x+df.month.map({'a':0,'b':.2,'c':-.1,'d':.4})+rng.normal(size=n)
    spec=CausalSpec(question='回复与下一次互动的条件相关关系是什么？',analysis_unit='post_event',
        treatment='treated',outcome='y',entity_id_column='user_id',cluster_column='user_id',
        covariates=['x','month','region'],candidate_methods=[CausalMethod.REGRESSION_ADJUSTMENT],
        assignment_mechanism=AssignmentMechanism.OBSERVATIONAL,data_structure=DataStructure.PANEL)
    return df,spec


def test_absorbing_coefficient_matches_independent_dummy_ols():
    df,spec=fixture()
    result=estimate_clustered_regression(df,spec)
    oracle=smf.ols('y~treated+x+C(month)+C(region)',df).fit(cov_type='cluster',cov_kwds={'groups':df.user_id})
    assert result.estimate.estimate==pytest.approx(oracle.params['treated'],abs=1e-10)
    assert result.estimate.standard_error==pytest.approx(oracle.bse['treated'],rel=.01)
    assert result.evidence['cluster_count']==300
    assert result.evidence['fixed_effect_columns']==['month','region']


def test_default_gate_still_blocks_unconfirmed_causal_analysis(tmp_path):
    df,spec=fixture()
    with pytest.raises(ValueError,match='Identification gate'):
        execute_analysis(df,spec,tmp_path)
    bundle=execute_analysis(df,spec,tmp_path,execution_scope='association_only',data_kind='user_provided')
    assert bundle.claim_level==ClaimLevel.ASSOCIATIONAL
    assert bundle.spec.identification_assumptions==[]


def test_authorization_is_version_bound_and_does_not_approve_assumptions(tmp_path):
    df,spec=fixture()
    repo=ResearchRepository(tmp_path/'state.sqlite3')
    session=repo.create_session(title='真实关联流程测试',dataset_fingerprint='test',row_count=len(df),
                                column_schema={c:str(t) for c,t in df.dtypes.items()})
    revision=repo.create_revision(session.session_id,spec,source=RevisionSource.SYSTEM_INITIAL,
                                  change_reason='测试',activate=True,status=DraftStatus.PENDING_REVIEW)
    with pytest.raises(ResearchStateError):
        run_versioned_association_workflow(df,repo,session_id=session.session_id,revision_id=revision.revision_id,
                                           output_dir=tmp_path/'runs',source_description='test')
    repo.authorize_association_analysis(revision.revision_id,authorized_by='user instruction',
                                       authorization_note='用户明确要求自动使用全量数据完成关联分析，不确认因果识别假设。')
    result=run_versioned_association_workflow(df,repo,session_id=session.session_id,revision_id=revision.revision_id,
                                             output_dir=tmp_path/'runs',source_description='test')
    assert result.agent_result.bundle.claim_level==ClaimLevel.ASSOCIATIONAL
    class NeverCall:
        calls=0
        last_telemetry={}
        def complete_json(self,**kwargs):
            self.calls+=1
            raise AssertionError('真实数据未授权不得调用外部模型')
    client=NeverCall()
    turn=ResultQAService(repo,client).ask(session_id=session.session_id,run_id=result.run_record.run_id,
                                         question='解释本次真实数据结果')
    assert not turn['answer']['used_model'] and client.calls==0
    assert repo.get_revision(revision.revision_id).status==DraftStatus.PENDING_REVIEW
    with pytest.raises(ResearchStateError): repo.get_approval(revision.revision_id)
    new=repo.create_revision(session.session_id,spec,source=RevisionSource.USER_EDIT,change_reason='新版本',
                             activate=True,status=DraftStatus.PENDING_REVIEW)
    with pytest.raises(ResearchStateError):
        repo.assert_association_execution_authorized(session_id=session.session_id,revision_id=new.revision_id,
                                                     dataset_version_id=new.dataset_version_id)


def test_obvious_future_covariates_and_single_cluster_rejected():
    df,spec=fixture()
    df['next_gap']=0.
    with pytest.raises(ValueError,match='未来信息'):
        estimate_clustered_regression(df,spec.model_copy(update={'covariates':['next_gap']}))
    df['user_id']='one'
    with pytest.raises(ValueError,match='两个独立聚类'):
        estimate_clustered_regression(df,spec)


def test_horizon_labels_keep_censored_unknown_and_recover_observed_zero():
    event=pd.Series([1,1,1,0,0,0,1])
    duration=pd.Series([10,604800,604801,604800,10,999999,0])
    result=horizon_label(event,duration,604800)
    assert result.iloc[:4].tolist()==[1.,1.,0.,0.]
    assert pd.isna(result.iloc[4]) and result.iloc[5]==0 and pd.isna(result.iloc[6])


def test_month_category_is_explicit_fixed_effect_not_arbitrary_datetime_covariate():
    frame=pd.DataFrame({'post_year_month_cat':['2024-01','2024-02']*20,
                        'event_date':pd.date_range('2024-01-01',periods=40)})
    catalog=build_field_catalog(frame)
    assert catalog['post_year_month_cat'].can_be_covariate
    assert not catalog['event_date'].can_be_covariate
