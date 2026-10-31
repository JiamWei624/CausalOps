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
    server=MCPServer('CausalOps read-only evidence',version='0.7.0',instructions='Only method knowledge and existing sanitized numeric evidence; no arbitrary SQL, files, raw rows, execution, or approval.')
    annotation=ToolAnnotations(read_only_hint=True,destructive_hint=False,idempotent_hint=True,open_world_hint=False)
    @server.tool(annotations=annotation)
    def search_methods(question:str,method:str|None=None,k:int=4)->dict:
        """Retrieve curated method rules/examples, source URLs and versioned citations."""
        return library.search(question,method=method,k=k)
    @server.tool(annotations=annotation)
    def read_run_evidence(run_id:str)->dict:
        """Read a previously exported sanitized numeric fact catalog by opaque run ID; never raw rows."""
        return read_exported_facts(root,run_id)

    @server.tool(annotations=annotation)
    def list_analysis_capabilities()->dict:
        """List executable method contracts and their human-review boundaries; never execute."""
        from causalops.assistant.contracts import REGISTRY
        return {'methods':[v.json() for v in REGISTRY.values()],'execution_available':False,'approval_available':False}
    @server.tool(annotations=annotation)
    def read_method_source(card_id:str,section:str|None=None)->dict:
        """Read an exact curated method card/section with registered source locators."""
        if not isinstance(card_id,str) or len(card_id)>80:raise ToolError('Invalid card identifier')
        c=next((c for c in library.cards if c['card_id']==card_id),None)
        if c is None:return {'status':'not_found','card_id':card_id}
        if section is not None and section not in c['sections']:return {'status':'section_not_found','card_id':card_id}
        return {'status':'found','card_id':card_id,'title':c['title'],'version':c['version'],'knowledge_sha256':library.digest,'sections':{section:c['sections'][section]} if section else c['sections'],'sources':[library.catalog['sources'][x] for x in c['source_ids']],'scope':'original curated summary, not a verbatim full-text document'}
    @server.tool(annotations=annotation)
    def check_evidence_citations(run_id:str,fact_ids:list[str])->dict:
        """Check that every cited fact belongs to one explicitly exported run."""
        from causalops.protocols.evidence_review import validate_fact_citations
        return validate_fact_citations(read_exported_facts(root,run_id),fact_ids)

    return server

def read_exported_facts(workspace,run_id):
    root=Path(workspace).resolve()
    if not re.fullmatch(r'[0-9a-f]{32}',run_id):raise ToolError('run_id must be an opaque 32-character hexadecimal identifier')
    # This is an explicit export boundary: read-only MCP cannot generate evidence or write a workspace.
    database=root/'assistant-readonly.sqlite3'
    if not database.is_file():return {'status':'not_exported','run_id':run_id,'facts':[]}
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as conn:
        row=conn.execute('SELECT facts_json FROM exported_run_facts WHERE run_id=?',(run_id,)).fetchone()
    return {'status':'found' if row else 'not_exported','run_id':run_id,'facts':json.loads(row[0]) if row else []}

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();create_server(a.workspace).run(transport='stdio')
if __name__=='__main__':main()
