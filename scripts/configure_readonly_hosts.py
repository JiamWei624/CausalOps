"""Generate E/local-project host configs without touching the user's global C drive config."""
from pathlib import Path
import sys,json,argparse

def configure(project,workspace,python=None):
    project=Path(project).resolve();workspace=Path(workspace).resolve();python=Path(python or sys.executable).resolve()
    args=['-m','causalops.protocols.readonly_server','--workspace',workspace.as_posix()]
    env={'PYTHONPATH':(project/'src').as_posix(),'TEMP':workspace.drive+'/project-temp','TMP':workspace.drive+'/project-temp','PYTHONIOENCODING':'utf-8'}
    command=python.as_posix();q=lambda x:json.dumps(x,ensure_ascii=False)
    toml='[mcp_servers.causalops_readonly]\ncommand = '+q(command)+'\nargs = '+q(args)+'\nenabled = true\nenabled_tools = ["search_methods", "read_method_source", "list_analysis_capabilities", "read_run_evidence", "check_evidence_citations"]\nstartup_timeout_sec = 30\ntool_timeout_sec = 30\n\n[mcp_servers.causalops_readonly.env]\n'+''.join(k+' = '+q(v)+'\n' for k,v in env.items())
    folder=project/'.codex';folder.mkdir(exist_ok=True);target=folder/'config.toml'
    if target.exists() and '[mcp_servers.causalops_readonly]' not in target.read_text(encoding='utf-8'):text=target.read_text(encoding='utf-8')+'\n'+toml
    elif target.exists() and target.read_text(encoding='utf-8')!=toml:raise ValueError('已有不同配置，不覆盖；请人工合并')
    else:text=toml
    target.write_text(text,encoding='utf-8')
    claude=project/'.mcp.json'
    if claude.exists():existing=json.loads(claude.read_text(encoding='utf-8'))
    else:existing={'mcpServers':{}}
    expected={'command':command,'args':args,'env':env}
    if 'causalops_readonly' in existing.get('mcpServers',{}) and existing['mcpServers']['causalops_readonly']!=expected:raise ValueError('Claude项目已有不同配置，未覆盖')
    existing.setdefault('mcpServers',{})['causalops_readonly']=expected;claude.write_text(json.dumps(existing,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'codex':str(target),'claude':str(claude),'global_config_touched':False,'host_reload_required':True}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();print(json.dumps(configure(a.project,a.workspace),ensure_ascii=False))
