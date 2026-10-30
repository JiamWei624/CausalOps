"""Official MCP SDK stdio transport. Only curated knowledge and sanitized run facts are exposed."""
from __future__ import annotations
import argparse,json,re,sqlite3
from pathlib import Path
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from mcp.server.mcpserver.exceptions import ToolError
from causalops.knowledge.retrieval import MethodLibrary


def create_server(workspace):
    root=Path(workspace).resolve();library=MethodLibrary()
    server=MCPServer('CausalOps read-only evidence',version='0.4.0',instructions='Only method knowledge and existing sanitized numeric evidence; no arbitrary SQL, files, raw rows, execution, or approval.')
    annotation=ToolAnnotations(read_only_hint=True,destructive_hint=False,idempotent_hint=True,open_world_hint=False)
    @server.tool(annotations=annotation)
    def search_methods(question:str,method:str|None=None,k:int=4)->dict:
        """Retrieve curated method rules/examples, source URLs and versioned citations."""
        return library.search(question,method=method,k=k)
    @server.tool(annotations=annotation)
    def read_run_evidence(run_id:str)->dict:
        """Read a previously exported sanitized numeric fact catalog by opaque run ID; never raw rows."""
        if not re.fullmatch(r'[0-9a-f]{32}',run_id):raise ToolError('run_id must be an opaque 32-character hexadecimal identifier')
        # This is an explicit export boundary: read-only MCP cannot generate evidence or write a workspace.
        database=root/'assistant-readonly.sqlite3'
        if not database.is_file():return {'status':'not_exported','run_id':run_id,'facts':[]}
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as conn:
            row=conn.execute('SELECT facts_json FROM exported_run_facts WHERE run_id=?',(run_id,)).fetchone()
        return {'status':'found' if row else 'not_exported','run_id':run_id,'facts':json.loads(row[0]) if row else []}
    return server

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();create_server(a.workspace).run(transport='stdio')
if __name__=='__main__':main()
