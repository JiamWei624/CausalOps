from pathlib import Path
import sys,json,time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_extended_estimators import _randomized_data,_experiment_spec,_observational_data,_observational_spec
from test_estimators import _did_data,_did_spec
from causalops.estimators import estimate_ab_test,estimate_cuped,estimate_twfe_did,estimate_double_ml_plr,estimate_psm_att,estimate_ipw_ate
from causalops.schemas import CausalMethod
from scipy.stats import norm
if __name__=='__main__':
    out=Path(sys.argv[1]) if len(sys.argv)>1 else Path('benchmark-output')
    out.mkdir(parents=True,exist_ok=True)
    rows=[];start=time.perf_counter()
    for i in range(30):
     seed=20261102+i;f=_randomized_data(seed=seed,rows=900)
     for m,fn in [('ab_test',estimate_ab_test),('cuped',estimate_cuped)]:
      b=fn(f,_experiment_spec(CausalMethod(m)));e=b.estimate
      row={'method':m,'seed':seed,'truth':1.2,'estimate':e.estimate,'se':e.standard_error,'ci':e.confidence_interval}
      if m=='ab_test':
       y1=f.loc[f.assignment==1,'retention_7d'].to_numpy();y0=f.loc[f.assignment==0,'retention_7d'].to_numpy()
       row['independent_formula_error']=abs(e.estimate-(y1.mean()-y0.mean()))
       row['independent_se_error']=abs(e.standard_error-np.sqrt(y1.var(ddof=1)/len(y1)+y0.var(ddof=1)/len(y0)))
      rows.append(row)
    for i in range(12):
     seed=20261202+i;b=estimate_twfe_did(_did_data(seed),_did_spec());e=b.estimate
     rows.append({'method':'did','seed':seed,'truth':2.,'estimate':e.estimate,'se':e.standard_error,'ci':e.confidence_interval})
    for i in range(6):
     seed=20261302+i;f=_observational_data(seed=seed,rows=600)
     for m,fn in [('double_ml',estimate_double_ml_plr),('psm',estimate_psm_att),('ipw',estimate_ipw_ate)]:
      b=fn(f,_observational_spec(CausalMethod(m)));e=b.estimate
      rows.append({'method':m,'seed':seed,'truth':1.7,'estimate':e.estimate,'se':e.standard_error,'ci':e.confidence_interval})
    summary=[]
    for m in dict.fromkeys(x['method'] for x in rows):
     v=[x for x in rows if x['method']==m];err=np.array([x['estimate']-x['truth'] for x in v]);interval=[x for x in v if x['ci']]
     summary.append({'method':m,'replications':len(v),'bias':float(err.mean()),'rmse':float(np.sqrt((err**2).mean())),'coverage95':sum(x['ci'][0]<=x['truth']<=x['ci'][1] for x in interval)/len(interval),'mean_se':float(np.mean([x['se'] for x in v]))})
    value={'type':'limited_synthetic_smoke_benchmark_not_complete_statistical_certification','replications_total':len(rows),'seconds':time.perf_counter()-start,'summary':summary,'runs':rows,'limits':['Only simple documented DGPs; small replication count, especially PSM/IPW/DML.','Coverage is descriptive; no claim of nominal coverage guarantee.','PSM SE is conditional on estimated matches.','No live model or independent user evaluation.']}
    (out/'statistical-benchmark.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'summary':summary,'seconds':value['seconds']}))
    assert all(x.get('independent_formula_error',0)<1e-12 and x.get('independent_se_error',0)<1e-12 for x in rows)
    assert all(np.isfinite([x['estimate'],x['se']]).all() for x in rows)
