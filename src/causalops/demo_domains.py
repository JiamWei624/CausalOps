from __future__ import annotations
import numpy as np
import pandas as pd
from causalops.schemas import CausalSpec

def synthetic_scenario(kind,seed):
    rng=np.random.default_rng(seed);n=1800
    if kind in ['ab','cuped','null_ab']:
        x=rng.normal(size=n);t=rng.binomial(1,.5,n);tau=0.0 if kind=='null_ab' else 2.5
        frame=pd.DataFrame({'entity_id':np.arange(n),'assigned':t,'baseline':x,'outcome':tau*t+1.8*x+rng.normal(0,.9,n)})
        method='cuped' if kind=='cuped' else 'ab_test'
        spec=CausalSpec(question='合成营销随机实验的平均收入差异是多少？',domain='generic',analysis_unit='customer',treatment='assigned',outcome='outcome',
                        entity_id_column='entity_id',covariates=['baseline'] if kind=='cuped' else [],candidate_methods=[method],
                        assignment_mechanism='randomized',has_pre_treatment_outcome=kind=='cuped')
    elif kind in ['psm','ipw','double_ml','hidden_confounding']:
        x=rng.normal(size=n);z=rng.normal(size=n);u=rng.normal(size=n)
        hidden=kind=='hidden_confounding';p=1/(1+np.exp(-(.5*x-.3*z+(1.5*u if hidden else 0))))
        t=rng.binomial(1,p,n);tau=0.0 if hidden else 1.7
        frame=pd.DataFrame({'entity_id':np.arange(n),'treatment':t,'outcome':tau*t+.9*x-.4*z+(2*u if hidden else 0)+rng.normal(0,.8,n),'x1':x,'x2':z})
        method='regression_adjustment' if hidden else kind
        spec=CausalSpec(question='合成服务干预与结果指标差异是什么？',domain='generic',analysis_unit='account',treatment='treatment',outcome='outcome',
                        entity_id_column='entity_id',cluster_column='entity_id',covariates=['x1','x2'],candidate_methods=[method],assignment_mechanism='observational',
                        positivity_plausible=None if hidden else True,
                        identification_assumptions=[] if hidden else ['conditional exchangeability by known synthetic data-generating process'])
    else:
        n=180;periods=20;dates=pd.date_range('2025-02-01',periods=periods);tau=1.8
        effects=rng.normal(size=n);rows=[]
        for i in range(n):
            treated=i<n//2
            for k,date in enumerate(dates):
                d=int(treated and k>=10)
                rows.append({'entity_id':i,'date':date,'start':dates[10] if treated else pd.NaT,'assigned':d,'baseline':effects[i],
                             'outcome':effects[i]+.05*k+tau*d+(.20*k*treated if kind=='did_bad_trend' else 0)+rng.normal(0,.35)})
        frame=pd.DataFrame(rows)
        spec=CausalSpec(question='合成医疗服务政策对日级结果的变化是什么？',domain='generic',analysis_unit='clinic_day',treatment='assigned',outcome='outcome',
                        entity_id_column='entity_id',time_column='date',treatment_time_column='start',cluster_column='entity_id',covariates=['baseline'],
                        candidate_methods=['did'],assignment_mechanism='observational',data_structure='panel',parallel_trends_plausible=True,
                        identification_assumptions=['parallel_trends','no_anticipation'],pre_period_days=9,post_period_days=9)
    return frame,spec,tau
