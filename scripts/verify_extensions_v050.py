"""Reproducible extension acceptance; no external model/raw data transmission."""
from pathlib import Path
import json,hashlib,urllib.request,asyncio,tomllib,subprocess,sys
import numpy as np,pandas as pd
from causalops.advanced.service import AdvancedDesign,estimate
from causalops.knowledge.retrieval import MethodLibrary
from causalops.protocols.reviewer_server import request_review
OUT=Path(__file__).resolve().parents[1]/'artifacts/extensions-v050-20261031';OUT.mkdir(exist_ok=True)

def public_data():
 from linearmodels.datasets import card
 from linearmodels.iv import IV2SLS
 from rdrobust import rdrobust
 rows=[];f=card.load();cfg=dict(method='iv_2sls',question='官方Card教育工资示例的数值复算',outcome='lwage',treatment='educ',instruments=['nearc4'],covariates=['exper','expersq','black','smsa','south','smsa66'],independent_units_reviewed=True,instrument_exogeneity_reviewed=True,exclusion_reviewed=True,no_interference_reviewed=True,covariates_pre_reviewed=True,allow_complete_case=True,design_evidence='仅官方示例的实现基准：这些布尔值为测试设定，不能证明真实研究假设。');d=AdvancedDesign(**cfg);b=estimate(f,d);x=pd.concat([pd.Series(1.,index=f.index,name='const'),f[d.covariates]],axis=1);r=IV2SLS(f.lwage,x,f[['educ']],f[['nearc4']]).fit(cov_type='robust',debiased=True);rows.append({'case':'Card官方真实数据IV','input_rows':len(f),'estimate':b['estimate'],'official_max_abs_difference':abs(b['estimate']-r.params.educ),'purpose':'implementation_benchmark_not_new_causal_claim'})
 url='https://raw.githubusercontent.com/rdpackages/rdrobust/master/Python/rdrobust_senate.csv';raw=urllib.request.urlopen(url,timeout=30).read();p=OUT/'senate-official.csv';p.write_bytes(raw);f=pd.read_csv(p);d=AdvancedDesign(method='rd_sharp',question='官方参议院RDD例子的数值与聚类复算',outcome='vote',running='margin',cluster='state',allow_complete_case=True,continuity_reviewed=True,no_manipulation_reviewed=True,threshold_rule_reviewed=True,no_interference_reviewed=True,design_evidence='仅官方数据的聚类实现基准，未经本项目独立确认因果识别条件。');b=estimate(f,d);clean=f.dropna(subset=['vote','margin','state']);r=rdrobust(clean.vote,clean.margin,c=0,p=1,q=2,bwselect='mserd',kernel='tri',masspoints='adjust',cluster=clean.state);rows.append({'case':'rdrobust作者参议院真实数据RDD','input_rows':len(f),'analysis_rows':b['analysis_rows'],'excluded_rows':b['excluded_rows'],'estimate':b['estimate'],'official_max_abs_difference':abs(b['estimate']-float(r.coef.loc['Robust'].iloc[0])),'source':url,'download_sha256':hashlib.sha256(raw).hexdigest(),'purpose':'implementation_benchmark_not_new_causal_claim'})
 (OUT/'public-data-acceptance.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8');print('public',rows)

async def protocols():
 import sqlite3
 from mcp.client.session import ClientSession
 from mcp.client.stdio import StdioServerParameters,stdio_client
 work=OUT/'protocol-test-workspace';work.mkdir(exist_ok=True);rid='a'*32
 with sqlite3.connect(work/'assistant-readonly.sqlite3') as c:
  c.execute('CREATE TABLE IF NOT EXISTS exported_run_facts(run_id TEXT PRIMARY KEY,facts_json TEXT NOT NULL)');c.execute('INSERT OR REPLACE INTO exported_run_facts VALUES(?,?)',(rid,json.dumps([{'id':'example','value':2.,'claim':'synthetic'}])))
 config=tomllib.loads((OUT.parents[1]/'.codex/config.toml').read_text(encoding='utf-8'))['mcp_servers']['causalops_readonly'];params=StdioServerParameters(command=config['command'],args=['-m','causalops.protocols.readonly_server','--workspace',str(work)],env=config['env']);info={}
 async with stdio_client(params) as streams:
  async with ClientSession(*streams) as client:
   await client.initialize();tools=await client.list_tools();info['mcp_tools']=[t.name for t in tools.tools]
   r=await client.call_tool('search_methods',{'question':'工具变量2SLS排除限制','method':'iv_2sls'});info['mcp_retrieval']=not r.is_error
   r=await client.call_tool('read_run_evidence',{'run_id':rid});info['mcp_existing_evidence']=not r.is_error and 'found' in str(r.content)
   r=await client.call_tool('read_run_evidence',{'run_id':'../secret'});info['mcp_traversal_rejected']=bool(r.is_error)
 a=await request_review({'action':'review_method','method':'staggered_did','question':'不同处理批次如何选择干净对照？'});deny=await request_review({'action':'execute','raw_rows':[1,2]})
 info.update(a2a_actual_sdk_version='1.3.0',a2a_transport='JSONRPC loopback official SDK client/server',a2a_task_completed=any(e.get('status_update',{}).get('status',{}).get('state')=='TASK_STATE_COMPLETED' for e in a),a2a_artifact_received=any('artifact_update' in e for e in a),a2a_execution_rejected=any(e.get('status_update',{}).get('status',{}).get('state')=='TASK_STATE_REJECTED' for e in deny))
 (OUT/'protocol-acceptance.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'a2a-actual-events.json').write_text(json.dumps(a,ensure_ascii=False,indent=2),encoding='utf-8');print('protocol',info)

def rag():
 lib=MethodLibrary();rows=[]
 for q,m in [('工具变量排除限制和弱工具','iv_2sls'),('断点回归阈值带宽诊断','rd_sharp'),('交错处理干净对照与动态ATT','staggered_did'),('Baker JFE 交错TWFE','staggered_did'),('平台政策抽佣与餐厅溢出','staggered_did'),('CSR 股东投票阈值','rd_sharp')]:
  hit=lib.search(q,method=m);rows.append({'query':q,'method':m,'cards':[x['card_id'] for x in hit['hits']],'ok':bool(hit['hits'])})
 (OUT/'rag-acceptance.json').write_text(json.dumps({'cards':len(lib.cards),'sources':len(lib.catalog['sources']),'digest':lib.digest,'queries':rows,'unknown_abstains':lib.search('合成控制')['status']=='insufficient_evidence'},ensure_ascii=False,indent=2),encoding='utf-8');print('rag',rows)
if __name__=='__main__':public_data();asyncio.run(protocols());rag()
