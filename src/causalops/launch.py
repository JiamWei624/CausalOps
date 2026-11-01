"""Portable local launcher. No API key or private dataset is required."""
from __future__ import annotations
import argparse,os,json,subprocess,sys,time,socket,webbrowser
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode

def launch_url(port,version,fingerprint):
    return f"http://127.0.0.1:{port}/?"+urlencode({"route":"home","release":version,"build":fingerprint[:12]})

def active_jobs(home):
    import sqlite3
    db=home/"research.sqlite3"
    if not db.is_file():return 0
    with sqlite3.connect(db.as_uri()+"?mode=ro",uri=True) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_jobs'").fetchone():return 0
        return c.execute("SELECT COUNT(*) FROM workflow_jobs WHERE status IN ('queued','running','cancel_requested')").fetchone()[0]
from urllib.request import build_opener,ProxyHandler

def healthy(port):
    try:
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/_stcore/health',timeout=1) as r:return r.status==200 and r.read(100).strip()==b'ok'
    except OSError:return False

def occupied(port):
    with socket.socket() as s:return s.connect_ex(('127.0.0.1',port))==0

def identity(pid):
    if os.name!='nt':return None
    q=f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}'; if($p){{[pscustomobject]@{{Created=$p.CreationDate.ToString('o');Command=$p.CommandLine}}|ConvertTo-Json -Compress}}"
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',q],capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
    try:return json.loads(r.stdout)
    except ValueError:return None

def owned(record,app):
    who=identity(record.get('pid',0))
    return bool(who and who['Created']==record.get('process_created') and str(app).lower() in (who['Command'] or '').lower() and 'streamlit' in (who['Command'] or '').lower())

def main(argv=None,project_root=None):
    p=argparse.ArgumentParser(description='CausalOps通用工作台，本机单用户')
    p.add_argument('--port',type=int,default=8513);p.add_argument('--workspace',type=Path);p.add_argument('--restart',action='store_true');p.add_argument('--no-browser',action='store_true');p.add_argument('--diagnose',action='store_true');a=p.parse_args(argv)
    if not 1024<=a.port<=65535:raise SystemExit('端口须在1024到65535之间。')
    base=Path(project_root).resolve() if project_root else Path.cwd().resolve()
    home=(a.workspace or Path(os.environ.get('CAUSALOPS_HOME',str(base/'causalops-workspace')))).expanduser().resolve()
    home.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['CAUSALOPS_HOME']=str(home)
    for k,folder in {'TEMP':home/'temp','TMP':home/'temp','PIP_CACHE_DIR':home/'cache/pip','MPLCONFIGDIR':home/'cache/matplotlib','HF_HOME':home/'cache/huggingface','TORCH_HOME':home/'cache/torch','JOBLIB_TEMP_FOLDER':home/'temp'}.items():
        folder.mkdir(parents=True,exist_ok=True);env[k]=str(folder);os.environ[k]=str(folder)
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',STREAMLIT_BROWSER_GATHER_USAGE_STATS='false',STREAMLIT_SERVER_SHOW_EMAIL_PROMPT='false');env.pop('DEEPSEEK_API_KEY',None)
    if project_root and (base/'src/causalops').is_dir():env['PYTHONPATH']=str(base/'src')
    os.environ['CAUSALOPS_HOME']=str(home)
    try:
        import streamlit
        from causalops.ui.showcase_support import source_fingerprint
        fingerprint=source_fingerprint()
        from causalops import __version__
    except ImportError:raise SystemExit('依赖未就绪，请按安装说明安装工作台app依赖。') from None
    runtime=home/'runtime';runtime.mkdir(exist_ok=True);state=runtime/f'service-{a.port}.json';url=launch_url(a.port,__version__,fingerprint)
    app=Path(__file__).resolve().parent/'ui/workbench.py'
    if a.diagnose:print(json.dumps({'dependencies':'ok','workspace':str(home),'port':a.port,'occupied':occupied(a.port),'healthy':healthy(a.port),'source_fingerprint':fingerprint,'version':__version__,'url':url},ensure_ascii=False));return 0
    if occupied(a.port):
        legacy=base/'artifacts/portfolio-showcase-20261030/runtime'/f'service-{a.port}.json'
        record=json.loads(state.read_text(encoding='utf-8')) if state.is_file() else json.loads(legacy.read_text(encoding='utf-8')) if legacy.is_file() else {}
        if a.restart:
            if active_jobs(home):raise SystemExit("当前工作区仍有后台任务；请先等待完成或在界面请求停止，再重启。")
            if not owned(record,app):raise SystemExit('端口不属于当前项目登记的进程，未关闭其他程序。请更换--port。')
            subprocess.run(['taskkill.exe','/PID',str(record['pid']),'/T','/F'],capture_output=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(30):
                if not occupied(a.port):break
                time.sleep(.1)
        elif healthy(a.port) and owned(record,app) and record.get('source_fingerprint')==fingerprint:
            print('CausalOps '+__version__+' 已运行：'+url)
            if not a.no_browser:webbrowser.open(url)
            return 0
        else:raise SystemExit('端口已占用或版本已更新。关闭原启动窗口，或用--restart重启登记的本项目服务。')
    env['CAUSALOPS_SOURCE_FINGERPRINT']=fingerprint
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S');log=runtime/f'server-{stamp}.log'
    command=[sys.executable,'-m','streamlit','run',str(app),'--server.address=127.0.0.1','--server.port',str(a.port),'--server.headless=true','--server.fileWatcherType=none','--server.maxUploadSize=50','--theme.base=light','--theme.primaryColor=#176b65']
    flags=(subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW) if os.name=='nt' else 0
    with log.open('w',encoding='utf-8') as output:
        child=subprocess.Popen(command,cwd=home,env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=output,creationflags=flags)
        who=identity(child.pid) or {};state.write_text(json.dumps({'pid':child.pid,'process_created':who.get('Created'),'source_fingerprint':fingerprint,'workspace':str(home),'port':a.port,'version':__version__,'url':url},ensure_ascii=False,indent=2),encoding='utf-8')
        try:
            for _ in range(150):
                if child.poll() is not None:raise RuntimeError('启动进程提前退出；请查看工作区runtime日志。')
                if healthy(a.port):break
                time.sleep(.2)
            else:raise RuntimeError('启动超时，请检查本地端口。')
            print('CausalOps '+__version__+'：'+url,flush=True);print('工作区：'+str(home),flush=True);print('默认本地处理，不需要API；关闭窗口后数据仍保留。',flush=True)
            if not a.no_browser:webbrowser.open(url)
            child.wait()
        except KeyboardInterrupt:print('正在停止服务，保留本地研究记录。')
        finally:
            if child.poll() is None:child.terminate();child.wait(timeout=15)
    return 0

def entrypoint():
    try:return main()
    except (OSError,RuntimeError,subprocess.SubprocessError) as exc:raise SystemExit('启动未完成：'+str(exc)) from None
if __name__=='__main__':entrypoint()