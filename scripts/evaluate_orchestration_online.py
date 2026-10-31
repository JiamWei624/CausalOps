"""Small real-provider smoke evaluation. Key comes from process environment only."""
from pathlib import Path
import os,json,time
import pandas as pd,numpy as np
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace
from causalops.assistant.observation import EvidenceLoop
from causalops.llm.deepseek import DeepSeekStructuredModelClient
root=Path(os.environ['CAUSALOPS_EVALUATION_OUT']);root.mkdir(parents=True,exist_ok=True)
a=AssistantWorkspace(GeneralWorkspace(root/'workspace'));rng=np.random.default_rng(71);x=rng.normal(size=140)
f=pd.DataFrame({'x':x,'y':2*x+rng.normal(size=140)})
uid=a.ws.ingest(f.to_csv(index=False).encode(),'public-synthetic-evaluation.csv');sid=a.create(uid,'official model synthetic smoke evaluation')
p=a.propose(sid,'先描述当前数据的整体分布');a.accept(p['id'],p['sha']);t=a.execute(p['id'],permit=True);old=t[0]['result']['run_id']
a.consent(sid,True)
model=DeepSeekStructuredModelClient(api_key=os.environ['CAUSALOPS_EVAL_KEY'],base_url='https://api.deepseek.com',model='deepseek-flash',api_mode='responses',max_output_tokens=3500,timeout_seconds=50,max_retries=0)
rows=[]
try:
 start=time.perf_counter();candidate=a.propose(sid,'请先检查数据质量，然后分析x与y的相关关系；不作因果解释。',model)
 rows.append({'case':'structured_plan','ok':candidate['state']=='candidate','calls_source':'official_API','seconds':time.perf_counter()-start})
 a.accept(candidate['id'],candidate['sha']);tasks=a.execute(candidate['id'],permit=True)
 a.select_run(sid,old)
 reply=a.ask(sid,'解释当前选定旧运行的样本量与均值，不引用新运行，不作因果解释。',model,run_id=old)
 rows.append({'case':'old_run_grounded_answer','ok':reply['source']=='DeepSeek官方模型+本地证据校验' and reply['run_ids']==[old] and all(v['run_id']==old for v in reply['facts']),'source':reply['source'],'validation_repairs':reply.get('validation_repairs',[])})
 review=EvidenceLoop(a).run(sid,'请根据此运行核对数据质量风险；只读观察并提出需核对的事项，不创建新计划。',run_id=old,model=model,max_steps=3)
 rows.append({'case':'bounded_observation','ok':not review['automatic_execution'] and review['candidate_id'] is None and review['stop_reason'] in ('human_fact_required','finished','step_budget'),'model_calls':review['model_calls'],'stop_reason':review['stop_reason']})
except Exception as exc:
 rows.append({'case':'provider_or_validation_failure','ok':False,'error_type':type(exc).__name__,'message':str(exc)[:300]})
usage=[e['body'] for e in a.events(sid) if e['kind']=='model_usage']
report={'provider':'https://api.deepseek.com','model':'deepseek-flash','data':'fixed synthetic aggregate-only; no user research rows','cases':rows,'telemetry':usage,'all_passed':len(rows)==3 and all(r['ok'] for r in rows),'limits':'Small provider smoke evaluation; not independent user or open-ended model accuracy.'}
(root/'evaluation.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps(report,ensure_ascii=False))
