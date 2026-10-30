"""Create synthetic input tables locally. No downloads or real user records."""
from pathlib import Path
import argparse,json
import numpy as np,pandas as pd
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('sample-data'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
rng=np.random.default_rng(871350);n=640;t=rng.integers(0,2,n)
f=pd.DataFrame({'response_flag':rng.binomial(1,.17+.08*t),'cohort_label':np.where(t,'new_plan','baseline_plan'),'pre_activity':rng.normal(size=n),'record_key':['case-'+str(i) for i in range(n)]})
f.to_csv(a.output/'new_campaign.csv',index=False);f.to_parquet(a.output/'new_campaign.parquet',index=False)
rows=[];event=pd.Timestamp('2026-09-15')
for unit in range(80):
 treated=unit<40;intercept=rng.normal()
 for day in range(-7,7):
  rows.append({'site_key':'site-'+str(unit),'calendar_day':str((event+pd.Timedelta(days=day)).date()),'policy_day':str(event.date()) if treated else None,'policy_active':int(treated and day>=0),'service_volume':15+intercept+.06*day+(1.4 if treated and day>=0 else 0)+rng.normal(0,.3)})
pd.DataFrame(rows).to_csv(a.output/'service_policy.csv',index=False)
(a.output/'SYNTHETIC.json').write_text(json.dumps({'synthetic':True,'seed':871350,'ab_probability_increment':.08,'did_effect':1.4,'note':'sample estimate need not equal generating effect'},indent=2),encoding='utf-8')
print('Synthetic CSV/Parquet tables written:',a.output.resolve())
