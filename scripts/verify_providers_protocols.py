"""Exercise added MCP tools and independent A2A evidence review over actual transports."""
import asyncio,json,os,sys
from pathlib import Path
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from causalops.protocols.reviewer_server import request_review
from causalops.protocols.local_services import card

async def main():
 out=Path(os.environ['CAUSALOPS_PROTOCOL_OUT']);ws=Path(os.environ['CAUSALOPS_PROTOCOL_WORKSPACE']);rid=os.environ['CAUSALOPS_PROTOCOL_RUN'];result={}
 env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
 def unpack(r):
  text=''.join(x.text for x in r.content if hasattr(x,'text'));return json.loads(text)
 async with Client(StdioServerParameters(command=sys.executable,args=['-m','causalops.protocols.readonly_server','--workspace',str(ws)],env=env)) as client:
  ts=await client.list_tools();names=[t.name for t in ts.tools] if hasattr(ts,'tools') else [t.name for t in ts];assert len(names)==5
  caps=unpack(await client.call_tool('list_analysis_capabilities',{}));assert len(caps['methods'])==17 and not caps['execution_available']
  source=unpack(await client.call_tool('read_method_source',{'card_id':'rd_fuzzy','section':'识别条件'}));assert source['status']=='found' and source['sources'] and len(source['sections'])==1
  facts=unpack(await client.call_tool('read_run_evidence',{'run_id':rid}));fid=facts['facts'][0]['id']
  valid=unpack(await client.call_tool('check_evidence_citations',{'run_id':rid,'fact_ids':[fid]}));bad=unpack(await client.call_tool('check_evidence_citations',{'run_id':rid,'fact_ids':['b'*32+':rows']}));assert valid['status']=='valid' and bad['status']=='invalid'
  result['mcp']={'tools':names,'method_count':len(caps['methods']),'exact_source_section':True,'correct_citation_accepted':True,'wrong_run_citation_rejected':True}
 events=await request_review({'action':'review_evidence','run_id':rid})
 def walk(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k=='text' and isinstance(v,str):
     try:
      p=json.loads(v)
      if isinstance(p,dict) and 'checks' in p:yield p
     except ValueError:pass
    yield from walk(v)
  elif isinstance(x,list):
   for v in x:yield from walk(v)
 reviews=list(walk(events));assert reviews and reviews[0]['run_id']==rid and not reviews[0]['assumptions_verified'];assert not reviews[0]['execution_performed']
 rejected=await request_review({'action':'review_evidence','run_id':'../../private.csv'});assert 'REJECTED' in json.dumps(rejected)
 result['a2a']={'version':card(8512)['version'],'transport':'official A2A SDK JSON-RPC loopback','review_returned':True,'checks':reviews[0]['checks'],'assumptions_verified':False,'execution_performed':False,'path_input_rejected':True}
 out.write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
