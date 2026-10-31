"""Exercise the official SDK client over a real stdio child process."""
import asyncio,json,os,sys,argparse
from pathlib import Path
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

async def verify(root,run_id=None):
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    params=StdioServerParameters(command=sys.executable,args=['-m','causalops.protocols.readonly_server','--workspace',str(root)],env=env)
    async with Client(params) as client:
        tools=await client.list_tools();names=[t.name for t in tools.tools] if hasattr(tools,'tools') else [t.name for t in tools]
        assert set(names)=={'search_methods','read_run_evidence','list_analysis_capabilities','read_method_source','check_evidence_citations'},names
        result=await client.call_tool('search_methods',{'question':'DID平行趋势事件研究','k':3})
        text=' '.join(x.text for x in result.content if hasattr(x,'text'));assert 'did' in text
        if run_id:
            existing=await client.call_tool('read_run_evidence',{'run_id':run_id});assert 'found' in str(existing) and 'finite_n' in str(existing)
        missing=await client.call_tool('read_run_evidence',{'run_id':'a'*32});assert 'not_exported' in str(missing)
        bad=await client.call_tool('read_run_evidence',{'run_id':'../../private.csv'});assert getattr(bad,'is_error',getattr(bad,'isError',False)),bad
        forbidden=await client.call_tool('execute_analysis',{});assert getattr(forbidden,'is_error',getattr(forbidden,'isError',False)),forbidden
    return {'transport':'official SDK stdio child process','tools':names,'rag_retrieval':True,'path_traversal_rejected':True,'execution_tool_absent':True,'existing_run_read':bool(run_id)}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--run-id');a=p.parse_args()
    a.out.parent.mkdir(parents=True,exist_ok=True);r=asyncio.run(verify(a.workspace,a.run_id));a.out.write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
