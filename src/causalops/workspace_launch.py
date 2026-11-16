"""One local foreground supervisor, two owned services, one explicit workspace."""
from __future__ import annotations
import argparse,importlib,json,os,socket,subprocess,sys,time,uuid,webbrowser
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from causalops.web_bundle import verify_bundle,workspace_identity

class ProcessGroup:
    """On Windows a job object closes descendants even after supervisor failure."""
    def __init__(self):
        self.handle=None;self.children=[]
        if os.name!='nt':return
        import ctypes as c
        from ctypes import wintypes as w
        class IO(c.Structure):_fields_=[(n,c.c_ulonglong)for n in ('readops','writeops','otherops','readbytes','writebytes','otherbytes')]
        class Basic(c.Structure):_fields_=[('user',c.c_longlong),('jobuser',c.c_longlong),('flags',w.DWORD),('min',c.c_size_t),('max',c.c_size_t),('active',w.DWORD),('affinity',c.c_size_t),('priority',w.DWORD),('schedule',w.DWORD)]
        class Extended(c.Structure):_fields_=[('basic',Basic),('io',IO),('processmem',c.c_size_t),('jobmem',c.c_size_t),('peakprocess',c.c_size_t),('peakjob',c.c_size_t)]
        k=c.WinDLL('kernel32',use_last_error=True);k.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR];k.CreateJobObjectW.restype=w.HANDLE;k.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];k.CloseHandle.argtypes=[w.HANDLE]
        h=k.CreateJobObjectW(None,None);info=Extended();info.basic.flags=0x2000
        if not h or not k.SetInformationJobObject(h,9,c.byref(info),c.sizeof(info)):
            if h:k.CloseHandle(h)
            raise RuntimeError('无法建立本地子进程生命周期控制，未启动工作台。')
        self.handle=h;self.kernel=k
    def add(self,child):
        self.children.append(child)
        if self.handle and not self.kernel.AssignProcessToJobObject(self.handle,int(child._handle)):
            child.terminate();child.wait(timeout=10)
            raise RuntimeError('无法绑定本地服务进程，启动已停止。')
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None
        for p in self.children:
            if p.poll() is None:p.terminate()
        for p in self.children:
            try:p.wait(timeout=12)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)

def child_environment(home,base=None):
    home=Path(home).resolve();env=dict(os.environ if base is None else base);env['CAUSALOPS_HOME']=str(home)
    for key,rel in {'TEMP':'temp','TMP':'temp','MPLCONFIGDIR':'cache/matplotlib','HF_HOME':'cache/huggingface','TORCH_HOME':'cache/torch','JOBLIB_TEMP_FOLDER':'temp'}.items():
        p=home/rel;p.mkdir(parents=True,exist_ok=True);env[key]=str(p)
    for key in ('DEEPSEEK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','LANGSMITH_API_KEY','LANGCHAIN_API_KEY','PYTHONPATH'):env.pop(key,None)
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',LANGSMITH_TRACING='false',LANGCHAIN_TRACING_V2='false',STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')
    return env

def configuration(argv=None,project_root=None):
    p=argparse.ArgumentParser(description='CausalOps React默认工作台 + Streamlit完整兼容入口；仅本机单用户')
    p.add_argument('--workspace',type=Path);p.add_argument('--port',type=int,default=8790);p.add_argument('--streamlit-port',type=int);p.add_argument('--no-browser',action='store_true');p.add_argument('--open',choices=['react','streamlit'],default='react');p.add_argument('--diagnose',action='store_true');p.add_argument('--startup-timeout',type=float,default=45)
    a=p.parse_args(argv);a.streamlit_port=a.streamlit_port if a.streamlit_port is not None else a.port+1
    if not all(1024<=v<=65535 for v in (a.port,a.streamlit_port))or a.port==a.streamlit_port:p.error('两个端口须不同，且位于1024到65535。')
    if not 1<=a.startup_timeout<=180:p.error('启动等待须为1到180秒。')
    base=Path(project_root).resolve()if project_root else Path.cwd();a.workspace=(a.workspace or Path(os.environ.get('CAUSALOPS_HOME',base/'causalops-workspace'))).expanduser().resolve();return a

def occupied(port):
    with socket.socket()as s:s.settimeout(.2);return s.connect_ex(('127.0.0.1',port))==0

def read_json(url):
    try:
        with build_opener(ProxyHandler({})).open(url,timeout=.8)as r:return json.loads(r.read(16384))if r.status==200 else None
    except (OSError,ValueError):return None

def streamlit_healthy(port):
    try:
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/_stcore/health',timeout=.8)as r:return r.status==200 and r.read(64).strip()==b'ok'
    except OSError:return False

def match_health(data,*,instance,home,version,frontend_sha):
    return bool(isinstance(data,dict)and data.get('instance')==instance and data.get('workspace')==workspace_identity(home)and data.get('version')==version and data.get('frontend_sha')==frontend_sha and data.get('ready')is True)

def deps():
    required=('fastapi','uvicorn','streamlit')+(('pywintypes',)if os.name=='nt'else())
    try:
        for name in required:importlib.import_module(name)
    except ImportError as e:raise RuntimeError('工作台依赖缺失：'+str(e.name)+'。请按requirements-windows-py311.lock.txt安装并执行pip check。')from None

def write_state(path,body):
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding='utf8');os.replace(tmp,path)

def reusable(record,a,bundle):
    from causalops import __version__
    from causalops.assistant.runtime import process_birth
    if not record or record.get('status')!='ready' or record.get('workspace')!=str(a.workspace)or record.get('streamlit_port')!=a.streamlit_port:return False
    for row in [record.get('supervisor',{}),*record.get('children',[])]:
        if not row.get('pid')or process_birth(row['pid'])!=row.get('birth')or row.get('birth')in (None,'?'):return False
    return match_health(read_json(f'http://127.0.0.1:{a.port}/api/health'),instance=record.get('instance'),home=a.workspace,version=__version__,frontend_sha=bundle['sha'])and streamlit_healthy(a.streamlit_port)

def main(argv=None,project_root=None):
    a=configuration(argv,project_root);deps();bundle=verify_bundle();from causalops import __version__
    from causalops.assistant.runtime import process_birth
    from causalops.application.locking import flow_lock
    a.workspace.mkdir(parents=True,exist_ok=True);runtime=a.workspace/'runtime';runtime.mkdir(exist_ok=True);state=runtime/f'workbench-{a.port}.json';react=f'http://127.0.0.1:{a.port}';legacy=f'http://127.0.0.1:{a.streamlit_port}';url=legacy if a.open=='streamlit'else react
    try:old=json.loads(state.read_text(encoding='utf8'))
    except (OSError,ValueError):old={}
    if a.diagnose:
        print(json.dumps(dict(version=__version__,workspace=str(a.workspace),react=react,streamlit=legacy,frontend_sha=bundle['sha'],dependencies='ok',ports={str(p):occupied(p)for p in (a.port,a.streamlit_port)},existing_pair_valid=reusable(old,a,bundle)),ensure_ascii=False));return 0
    if occupied(a.port)or occupied(a.streamlit_port):
        if reusable(old,a,bundle):
            print('CausalOps '+__version__+' 已运行：'+url,flush=True)
            if not a.no_browser:webbrowser.open(url)
            return 0
        raise RuntimeError('端口已被其他服务、其他工作区或不同版本占用，未连接或关闭该进程。请关闭原启动窗口，或同时指定空闲--port与--streamlit-port。')
    with flow_lock(a.workspace,'workbench-launch-'+str(a.port)):
        if occupied(a.port)or occupied(a.streamlit_port):raise RuntimeError('端口在启动期间被占用，未连接已有服务。')
        env=child_environment(a.workspace);instance=uuid.uuid4().hex;env['CAUSALOPS_LAUNCH_INSTANCE']=instance
        if project_root:env['PYTHONPATH']=str(Path(project_root).resolve()/'src')
        app=Path(__file__).resolve().parent/'ui/workbench.py';stamp=time.time_ns();handles=[];group=ProcessGroup();record=dict(version=__version__,status='starting',workspace=str(a.workspace),instance=instance,port=a.port,streamlit_port=a.streamlit_port,react=react,streamlit=legacy,frontend_sha=bundle['sha'],supervisor=dict(pid=os.getpid(),birth=process_birth(os.getpid())),children=[])
        commands=[('react',[sys.executable,'-m','causalops.react_api','--port',str(a.port),'--streamlit-url',legacy,'--dist',str(bundle['root'])]),('streamlit',[sys.executable,'-m','streamlit','run',str(app),'--server.address=127.0.0.1','--server.port='+str(a.streamlit_port),'--server.headless=true','--server.fileWatcherType=none','--browser.gatherUsageStats=false'])]
        try:
            for name,args in commands:
                log=runtime/f'{name}-{stamp}.log';f=log.open('w',encoding='utf8');handles.append(f)
                p=subprocess.Popen(args,cwd=a.workspace,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=f,creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)if os.name=='nt'else 0);group.add(p);record['children'].append(dict(role=name,pid=p.pid,birth=process_birth(p.pid),log=log.name))
            write_state(state,record);deadline=time.monotonic()+a.startup_timeout
            while time.monotonic()<deadline:
                if any(p.poll()is not None for p in group.children):raise RuntimeError('本地服务提前退出，请查看工作区runtime日志。')
                if match_health(read_json(react+'/api/health'),instance=instance,home=a.workspace,version=__version__,frontend_sha=bundle['sha'])and streamlit_healthy(a.streamlit_port):break
                time.sleep(.2)
            else:raise RuntimeError('本地服务未通过工作区、版本与健康核验，启动超时；未打开页面。请查看runtime日志。')
            record['status']='ready';write_state(state,record)
            print('CausalOps '+__version__+' React：'+react,flush=True);print('完整兼容工作台：'+legacy,flush=True);print('共享工作区：'+str(a.workspace),flush=True);print('关闭本窗口或Ctrl+C将停止两个服务；记录保留。运行中请先在页面请求暂停，重启后核查恢复。',flush=True)
            if not a.no_browser:webbrowser.open(url)
            while True:
                for p in group.children:
                    if p.poll()is not None:raise RuntimeError('一个本地服务已退出，已停止另一服务；请查看runtime日志。研究结果保留，重启后核查恢复。')
                time.sleep(.3)
        except KeyboardInterrupt:print('正在停止两个本地服务，保留研究记录。',flush=True)
        except BaseException:
            record['status']='failed';raise
        finally:
            group.close()
            for f in handles:f.close()
            if record['status']!='failed':record['status']='stopped'
            write_state(state,record)
    return 0

def entrypoint():
    try:return main()
    except (OSError,RuntimeError,ValueError)as exc:raise SystemExit('启动未完成：'+str(exc))from None

def streamlit_entrypoint():
    try:return main(['--open','streamlit',*sys.argv[1:]])
    except (OSError,RuntimeError,ValueError)as exc:raise SystemExit('启动未完成：'+str(exc))from None

if __name__=='__main__':entrypoint()
