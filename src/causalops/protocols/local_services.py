"""Start the optional local read-only reviewer on demand, with logs on the workspace drive."""
from pathlib import Path
import json,os,socket,subprocess,sys,time
from urllib.request import build_opener,ProxyHandler

def card(port):
    try:
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/.well-known/agent-card.json',timeout=2) as r:return json.load(r)
    except (OSError,ValueError):return None

def ensure_reviewer(workspace,port=8512):
    workspace=Path(workspace).resolve();existing=card(port)
    if existing:
        if existing.get('name')!='CausalOps Method Reviewer':raise RuntimeError('审阅端口属于其他服务，未进行替换。')
        return {'status':'already_running','port':port}
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1',port))==0:raise RuntimeError('审阅端口被其他程序占用，未关闭任何程序。')
    import a2a
    runtime=workspace/'runtime';runtime.mkdir(exist_ok=True);log=runtime/'a2a-reviewer.log';env=os.environ.copy()
    for k in ['TEMP','TMP']:env[k]=str(workspace/'temp')
    (workspace/'temp').mkdir(exist_ok=True);env['PYTHONIOENCODING']='utf-8';env.pop('DEEPSEEK_API_KEY',None)
    with log.open('a',encoding='utf-8') as f:
        p=subprocess.Popen([sys.executable,'-m','causalops.protocols.reviewer_server','--workspace',str(workspace),'--port',str(port)],cwd=workspace,env=env,stdout=f,stderr=f,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(40):
        if p.poll() is not None:raise RuntimeError('只读审阅服务启动失败，请查看工作区runtime/a2a-reviewer.log。')
        if card(port):
            (runtime/'a2a-reviewer.json').write_text(json.dumps({'pid':p.pid,'port':port,'workspace':str(workspace),'log':str(log)}),encoding='utf-8');return {'status':'started','port':port,'pid':p.pid}
        time.sleep(.15)
    p.terminate();raise RuntimeError('审阅服务启动超时。')
