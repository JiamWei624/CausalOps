"""Preregistered live task evaluation. Credentials stay in memory; no row is sent."""
from pathlib import Path
import argparse,os,json,time,hashlib,traceback
import numpy as np,pandas as pd,statsmodels.api as sm
from causalops.application.research_service import ResearchService
from causalops.application.background import BackgroundJobs,ACTIVE
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.llm.providers import ProviderConfig,StructuredModelClient

def wait(jobs,job):
 end=time.monotonic()+240
 while time.monotonic()<end:
  row=jobs.job(job['id'])
  if row['status'] not in ACTIVE:return jobs.service.flow(row['flow_id']),row
  time.sleep(.1)
 raise TimeoutError('Task exceeded bounded evaluation deadline')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--benchmark',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--split',choices=['development','holdout'],required=True);parser.add_argument('--case',action='append',default=[],help='Optional frozen case IDs for explicitly labelled targeted replays');args=parser.parse_args();out=args.output.resolve()
 if out.drive.lower()=='c:':raise SystemExit('Use a data-drive output outside C:.')
 out.mkdir(parents=True,exist_ok=True);raw=args.benchmark.read_bytes();frozen=json.loads(raw);expected=args.benchmark.with_suffix('.sha256').read_text(encoding='utf-8').strip();assert hashlib.sha256(raw).hexdigest()==expected
 cfg=ProviderConfig(timeout_seconds=60,max_output_tokens=4800);key=os.environ.pop('CAUSALOPS_LIVE_KEY',None)
 if not key:raise SystemExit('Set CAUSALOPS_LIVE_KEY in process memory; never put it in a case file.')
 records=[]
 for case in frozen['cases']:
  if case['split']!=args.split or (args.case and case['id'] not in args.case):continue
  start=time.perf_counter();record={'id':case['id'],'split':case['split'],'policy':case['policy'],'question':case['question'],'benchmark_sha256':expected,'expected_methods':case['expected_methods'],'checks':{},'errors':[]};client=None;s=None;sid=None
  try:
   path=args.benchmark.parent/'benchmark-data'/(case['data']+'.parquet');payload=path.read_bytes();assert hashlib.sha256(payload).hexdigest()==case['data_sha256'];frame=pd.read_parquet(path)
   s=ResearchService(AssistantWorkspace(GeneralWorkspace(out/'workspace')));sid=s.create_task(payload=payload,name=case['data']+'.parquet',title=case['id'])
   if case['dictionary']:s.contracts.save(sid,case['dictionary'],human_confirmed=True)
   client=StructuredModelClient(cfg,key);s.a.consent(sid,True,cfg);s.model=client;jobs=BackgroundJobs(s)
   f,job=wait(jobs,jobs.submit_start(sid,case['question']));record['flow_id']=f['id'];record['flow_status']=f['status'];record['route']=s.output(f['id'],'route');record['method_research']=s.output(f['id'],'method_research');record['readiness']=s.output(f['id'],'readiness');record['checks']['no_preapproval_estimate']=not s.a.completed_runs(sid)
   if f['status']=='failed':record['errors'].append(job.get('error_type')+':'+str(job.get('error_note')))
   if f['plan_id']:
    p=s.a.get_plan(f['plan_id']);record['plan']=p['plan'];methods=[x['config']['method'] for x in p['plan']['steps']];record['selected_methods']=methods
   else:p=None;methods=[]
   if case['policy']=='no_estimation':
    record['checks']['request_handled_without_estimation']=not s.a.completed_runs(sid) and f['status'] in ('completed','needs_clarification') and (record['route'] or {}).get('route') in ('method','clarify','profile')
    record['answer']=s.output(f['id'],'answer') or s.output(f['id'],'profile')
   elif case['policy']=='profile_or_describe' and (record['route'] or {}).get('route')=='profile':
    record['checks']['profile_matches_source']=s.output(f['id'],'profile')['rows']==len(frame)
   else:
    target=case['expected_methods'][0];record['checks']['selected_expected_method']=target in methods and set(methods)<={target,'descriptive'}
    if not record['checks']['selected_expected_method']:raise AssertionError('Candidate did not select the preregistered primary method; no plan was rewritten.')
    for step in p['plan']['steps']:
     if step['config']['method']==target:
      for field in ('outcome','treatment','entity','time','treatment_time'):
       if case['dictionary'].get(field):assert step['config'].get(field)==case['dictionary'][field],('role mismatch',field)
      if case['dictionary'].get('predictors'):assert set(step['config'].get('predictors',[]))==set(case['dictionary']['predictors']), 'Predictors differ from requested adjustment set'
    s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,use_contract_facts=True,dispatch=False)
    final,job=wait(jobs,jobs.submit(f['id']));record['execution_status']=final['status'];record['execution']=s.output(f['id'],'execution');refs=s.a.completed_runs(sid);record['checks']['execution_completed']=final['status']=='completed'
    primary=[x for x in refs if x['method']==target];assert len(primary)==1,'Expected exactly one primary result';ref=primary[0];rid=ref['run_id'];record['run_id']=rid
    if ref['kind']=='exploration':
     b=s.a.ex.load(rid);record['claim']=b['claim_level'];d=b['design']
     if target=='descriptive':record['checks']['numeric_reference']=b['summary']['row_count']==len(frame)
     else:
      part=frame[[d['outcome'],*d['predictors']]].dropna();x=sm.add_constant(pd.get_dummies(part[d['predictors']],drop_first=True,dtype=float).astype(float),has_constant='add');y=part[d['outcome']].astype(float)
      fit=sm.OLS(y,x).fit(cov_type=d.get('covariance','HC3')) if target=='ols' else sm.GLM(y,x,family=sm.families.Binomial()).fit(cov_type=d['covariance']);delta=max(abs(row['coefficient']-fit.params[row['term']]) for row in b['regression']['coefficients']);record['max_reference_error']=float(delta);record['checks']['numeric_reference']=delta<1e-8
    else:
     b,run=s.ws.bundle(rid);record['claim']=b.claim_level.value;record['estimate']=b.estimate.estimate
     if target=='ab_test':
      d=case['dictionary'];groups=frame.groupby(d['treatment'])[d['outcome']].mean();refvalue=float(groups.loc[int(d['treated_value'])]-groups.loc[int(d['control_value'])]);record['max_reference_error']=abs(refvalue-b.estimate.estimate);record['checks']['numeric_reference']=record['max_reference_error']<1e-8
     else:
      # Known synthetic constant effect is not empirical business ground truth.
      record['checks']['numeric_reference']=np.isfinite(b.estimate.estimate)
      record['checks']['claim_boundary']=record['claim']=='associational' if case['policy']=='execute_downgrade' else record['claim'] in ('reduced_form','associational')
    before=len(refs);q,job=wait(jobs,jobs.submit_start(sid,case['followup'],mode='results',run_ids=[rid]));answer=s.output(q['id'],'answer');record['answer']=answer;record['checks']['followup_no_recompute']=len(s.a.completed_runs(sid))==before;record['checks']['answer_has_run_evidence']=bool(answer and answer.get('facts') and answer.get('run_ids')==[rid]);record['model_answer_passed']=bool(answer and not answer.get('source','').startswith('本地'))
    record['initial_answer']=s.output(f['id'],'answer')
    if ref['kind']=='exploration':
     from causalops.general.exploration_report import render_report
     report=render_report(b)
    else:
     from causalops.reporting import render_html_report
     report=render_html_report(b)
    from causalops.application.task_conclusions import build_task_conclusion,attach_task_conclusion
    conclusion=build_task_conclusion(s.a,sid,rid);record['task_conclusion']=conclusion;report=attach_task_conclusion(report,conclusion)
    record['checks']['four_part_conclusion']=set(conclusion['sections'])=={'baseline','magnitude','meaning','action'}
    record['checks']['conclusion_run_bound']=conclusion['run_id']==rid and bool(conclusion['evidence'])
    (out/(case['id']+'-report.html')).write_text(report,encoding='utf-8');record['checks']['report_exported']=True
  except Exception as exc:
   record['errors'].append(type(exc).__name__+':'+str(exc)[:700]);record['traceback']=traceback.format_exc()
  finally:
   if s and sid:
    events=s.a.events(sid);record['usage']=[e['body'] for e in events if e['kind']=='model_usage'];record['validation_rejections']=[e['body'] for e in events if e['kind']=='answer_validation'];record['request_count']=len(record['usage']);record['total_tokens']=sum(e.get('total_tokens',0) for e in record['usage'])
   if client:client.close()
   from causalops.general.exploration import clean_json
   record=clean_json(record)
   record['elapsed_seconds']=round(time.perf_counter()-start,3);record['passed']=bool(record['checks']) and all(record['checks'].values()) and not record['errors'];records.append(record);(out/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
   print(json.dumps({'id':record['id'],'passed':record['passed'],'route':record.get('route'),'selected_methods':record.get('selected_methods'),'checks':record['checks'],'errors':record['errors'],'tokens':record.get('total_tokens')},ensure_ascii=False),flush=True)
 print(json.dumps({'split':args.split,'cases':len(records),'passed':sum(x['passed'] for x in records),'total_tokens':sum(x.get('total_tokens',0) for x in records)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
