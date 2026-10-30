"""Optional real official-provider acceptance using synthetic data only; credentials never persisted."""
from pathlib import Path
import json,os,time
import numpy as np,pandas as pd
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace
from causalops.llm.deepseek import DeepSeekStructuredModelClient

root=Path(os.environ['CAUSALOPS_ACCEPTANCE_OUT']);root.mkdir(parents=True,exist_ok=True)
a=AssistantWorkspace(GeneralWorkspace(root/'live-synthetic-workspace'));rng=np.random.default_rng(82)
f=pd.DataFrame({'x':rng.normal(size=160),'y':rng.normal(size=160)})
uid=a.ws.ingest(f.to_csv(index=False).encode(),'synthetic.csv');sid=a.create(uid,'synthetic acceptance only');a.consent(sid,True)
model=DeepSeekStructuredModelClient(api_key=os.environ['DEEPSEEK_API_KEY'],base_url='https://api.deepseek.com',model='deepseek-flash',max_output_tokens=5000,timeout_seconds=60,max_retries=1)
report={'data':'synthetic_only','raw_rows_sent':False,'keys_persisted':False,'cases':[]};start=time.monotonic()
try:
    p=a.propose(sid,'帮我分析x和y的数据质量、分布和相关关系。只做描述与相关，不做因果或回归。',model)
    report['cases'].append({'name':'real_model_plan','ok':True,'methods':[s['config'].get('method') for s in p['plan']['steps']],'telemetry':model.last_telemetry})
    a.accept(p['id'],p['sha']);tasks=a.execute(p['id'],permit=True);report['cases'].append({'name':'execute_real_proposal','ok':all(t['state']=='completed' for t in tasks)})
    answer=a.ask(sid,'解释当前结果的样本量和局限，只引用已有事实，不新增计算。',model)
    report['cases'].append({'name':'real_model_evidence_qa','ok':answer['source']=='DeepSeek官方模型+本地证据校验','source':answer['source'],'fact_count':len(answer['facts']),'telemetry':model.last_telemetry})
except Exception as exc:
    report['cases'].append({'name':'live_failure','ok':False,'exception_type':type(exc).__name__,'message':str(exc)[:1200]})
report['seconds']=round(time.monotonic()-start,3);report['ok']=all(x['ok'] for x in report['cases'])
(root/'live-official-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
