"""Local background worker with durable job records; credentials remain in memory."""
from __future__ import annotations
import os,json,uuid,threading,re
from concurrent.futures import ThreadPoolExecutor
from causalops.assistant.runtime import process_birth,alive,execution_source_sha
from causalops.assistant.service import AssistantWorkspace,now
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.application.research_service import ResearchService,FlowCancelled

_POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='causalops-workflow')
_FUTURES={}
_GUARD=threading.Lock()
ACTIVE=('queued','running','cancel_requested')
class BackgroundJobs:
    def __init__(self,service):
        self.service=service;self.ws=service.ws
        with self.ws.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS workflow_jobs(id TEXT PRIMARY KEY,flow_id TEXT,session_id TEXT,status TEXT,owner_pid INTEGER,owner_birth TEXT,source_sha TEXT,model_binding TEXT,created TEXT,started TEXT,finished TEXT,error_type TEXT,error_note TEXT)')
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS workflow_one_active_job ON workflow_jobs(flow_id) WHERE status IN ('queued','running','cancel_requested')")
    def jobs(self,sid):
        self.service.a.session(sid)
        with self.ws.connection() as c:
            c.row_factory=__import__('sqlite3').Row;rows=c.execute('SELECT * FROM workflow_jobs WHERE session_id=? ORDER BY rowid DESC',(sid,)).fetchall()
        return [dict(r) for r in rows]
    def job(self,jid):
        with self.ws.connection() as c:
            c.row_factory=__import__('sqlite3').Row;r=c.execute('SELECT * FROM workflow_jobs WHERE id=?',(jid,)).fetchone()
        if not r:raise DesignError('后台任务不存在。')
        return dict(r)
    def submit_start(self,sid,question,*,mode='auto',run_ids=None,parent_flow_id=None):
        self.capacity()
        f=self.service.begin(sid,question,mode=mode,run_ids=run_ids,parent_flow_id=parent_flow_id)
        return self.submit(f['id'])
    def capacity(self):
        with self.ws.connection() as c:n=c.execute("SELECT COUNT(*) FROM workflow_jobs WHERE status IN ('queued','running','cancel_requested')").fetchone()[0]
        if n>=4:raise DesignError('当前工作区已有四项排队或运行任务，请等待后再提交。')
    def submit(self,fid):
        from causalops.llm.providers import model_binding,StructuredModelClient
        f=self.service.flow(fid);self.capacity();model=self.service.model
        binding=model_binding(model) if model else None
        if binding and not self.service.a.consent_enabled(f['session_id'],binding):raise DesignError('当前模型接收配置未获任务授权。')
        if isinstance(model,StructuredModelClient):
            config=model.provider_config;credential=model._api_key
            factory=lambda:StructuredModelClient(config,credential)
            owned=True
        else:factory=lambda:model;owned=False
        jid=uuid.uuid4().hex
        with self.ws.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            prior=c.execute("SELECT id FROM workflow_jobs WHERE flow_id=? AND status IN ('queued','running','cancel_requested')",(fid,)).fetchone()
            if prior:return self.job(prior[0])
            n=c.execute("SELECT COUNT(*) FROM workflow_jobs WHERE status IN ('queued','running','cancel_requested')").fetchone()[0]
            if n>=4:raise DesignError('后台队列已满，请等待。')
            c.execute('INSERT INTO workflow_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(jid,fid,f['session_id'],'queued',os.getpid(),process_birth(os.getpid()),execution_source_sha(),json.dumps(binding) if binding else None,now(),None,None,None,None))
        future=_POOL.submit(self._run,jid,factory,owned)
        with _GUARD:
            _FUTURES[(str(self.ws.root),jid)]=future
            for key,v in list(_FUTURES.items()):
                if len(_FUTURES)>128 and v.done():_FUTURES.pop(key,None)
        return self.job(jid)
    def _run(self,jid,factory,owned):
        model=None;s=None
        try:
            with self.ws.connection() as c:
                count=c.execute("UPDATE workflow_jobs SET status='running',started=? WHERE id=? AND status='queued'",(now(),jid)).rowcount
            if not count:return
            job=self.job(jid)
            if job['source_sha']!=execution_source_sha():raise DesignError('排队期间代码已变化，请核对后重新提交。')
            model=factory();s=ResearchService(AssistantWorkspace(GeneralWorkspace(self.ws.root)),model=model)
            s.check_cancel(job['flow_id']);flow=s.continue_flow(job['flow_id'])
            status='waiting_review' if flow['status']=='awaiting_review' else 'failed' if flow['status']=='failed' else 'blocked' if flow['status']=='blocked' else 'cancelled' if flow['status']=='cancelled' else 'completed'
            with self.ws.connection() as c:c.execute('UPDATE workflow_jobs SET status=?,finished=? WHERE id=?',(status,now(),jid))
        except FlowCancelled:
            job=self.job(jid)
            if s:s.update(job['flow_id'],status='cancelled')
            else:self.service.update(job['flow_id'],status='cancelled')
            with self.ws.connection() as c:c.execute("UPDATE workflow_jobs SET status='cancelled',finished=? WHERE id=?",(now(),jid))
        except Exception as exc:
            job=self.job(jid);note=str(exc)[:500] if isinstance(exc,DesignError) else '处理未完成，请保留流程记录并核对输入与服务配置。'
            note=re.sub(r'sk-[A-Za-z0-9_-]{10,}','[认证信息已移除]',note)
            self.service.update(job['flow_id'],status='failed')
            with self.ws.connection() as c:c.execute("UPDATE workflow_jobs SET status='failed',finished=?,error_type=?,error_note=? WHERE id=?",(now(),type(exc).__name__,note,jid))
        finally:
            if owned and model:model.close()
    def cancel(self,fid,*,human_confirmed=False):
        self.service.cancel(fid,human_confirmed=human_confirmed)
        with self.ws.connection() as c:
            rows=c.execute("SELECT id,status FROM workflow_jobs WHERE flow_id=? AND status IN ('queued','running','cancel_requested')",(fid,)).fetchall()
            for jid,status in rows:
                with _GUARD:future=_FUTURES.get((str(self.ws.root),jid))
                stopped=future.cancel() if future else False
                c.execute("UPDATE workflow_jobs SET status=? WHERE id=? AND status IN ('queued','running','cancel_requested')",('cancelled' if stopped else 'cancel_requested',jid))
        if any(status=='queued' for _,status in rows):self.service.update(fid,status='cancelled')
        return self.service.flow(fid)
    def reconcile(self,sid):
        changes=[]
        for job in self.jobs(sid):
            if job['status'] not in ACTIVE:continue
            with _GUARD:future=_FUTURES.get((str(self.ws.root),job['id']))
            if future is not None and not future.done():continue
            if alive(job['owner_pid'],job['owner_birth']) and future is None:continue
            if not alive(job['owner_pid'],job['owner_birth']) or (future is not None and future.done()):
                with self.ws.connection() as c:
                    c.execute("UPDATE workflow_jobs SET status='interrupted',finished=?,error_type='WorkerInterrupted' WHERE id=? AND status IN ('queued','running','cancel_requested')",(now(),job['id']))
                changes.append(job['id'])
        return changes
    def resume(self,fid,*,human_confirmed=False):
        from causalops.llm.providers import model_binding
        flow=self.service.flow(fid);self.reconcile(flow['session_id']);jobs=[j for j in self.jobs(flow['session_id']) if j['flow_id']==fid]
        if any(j['status'] in ACTIVE for j in jobs):raise DesignError('原任务仍在处理或进程身份未确认，不能重复接管。')
        if jobs and jobs[0]['model_binding']:
            if not self.service.model or model_binding(self.service.model)!=json.loads(jobs[0]['model_binding']):raise DesignError('请重新输入并授权原模型配置；密钥不会从磁盘恢复。')
        self.service.resume(fid,human_confirmed=human_confirmed,dispatch=False)
        return self.submit(fid)


class AutomationJobs:
    """V2 job metadata; shares the existing one-worker pool, never old Flow IDs."""
    def __init__(self,service):
        self.service=service;self.ws=service.ws
        with self.ws.connection() as c:
            c.execute("CREATE TABLE IF NOT EXISTS automation_v2_jobs(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,status TEXT NOT NULL,owner_pid INTEGER,owner_birth TEXT,source_sha TEXT NOT NULL,operation TEXT NOT NULL,created TEXT NOT NULL,finished TEXT,error_note TEXT)")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS automation_one_active_job ON automation_v2_jobs(task_id) WHERE status IN ('queued','running')")
    def jobs(self,tid):
        self.service.automation_v2().task(tid)
        with self.ws.connection() as c:
            c.row_factory=__import__('sqlite3').Row
            return [dict(r) for r in c.execute("SELECT * FROM automation_v2_jobs WHERE task_id=? ORDER BY rowid DESC",(tid,))]
    def reconcile(self,tid):
        for j in self.jobs(tid):
            if j["status"] not in ("queued","running"):continue
            with _GUARD:f=_FUTURES.get((str(self.ws.root),j["id"]))
            if f is not None and not f.done():continue
            if not alive(j["owner_pid"],j["owner_birth"]) or (f is not None and f.done()):
                with self.ws.connection() as c:c.execute("UPDATE automation_v2_jobs SET status='interrupted',finished=?,error_note='原后台进程已退出；需核查运行后恢复' WHERE id=? AND status IN ('queued','running')",(now(),j["id"]))
        return self.jobs(tid)
    def submit_task(self,tid,*,resume=False):
        co=self.service.automation_v2();t=co.task(tid);self.reconcile(tid)
        existing=next((j for j in self.jobs(tid) if j["status"] in ("queued","running")),None)
        if existing:return existing
        if (not resume and t["status"]!="approved") or (resume and t["status"] not in ("paused","interrupted","running","pause_requested","approved")):
            raise DesignError("当前任务未批准、已取消或需处理阻断，不能提交执行。")
        if not resume:co._verify(t)
        jid=uuid.uuid4().hex
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            previous=c.execute("SELECT id FROM automation_v2_jobs WHERE task_id=? AND status IN ('queued','running')",(tid,)).fetchone()
            if previous:return next(j for j in self.jobs(tid) if j["id"]==previous[0])
            if c.execute("SELECT count(*) FROM automation_v2_jobs WHERE status IN ('queued','running')").fetchone()[0]>=4:
                raise DesignError("自动化队列已满，请等待。")
            c.execute("INSERT INTO automation_v2_jobs VALUES(?,?,?,?,?,?,?,?,NULL,NULL)",(jid,tid,"queued",os.getpid(),process_birth(os.getpid()),execution_source_sha(),"resume" if resume else "run",now()))
        f=_POOL.submit(self._run_task,jid,tid,resume)
        with _GUARD:_FUTURES[(str(self.ws.root),jid)]=f
        return next(j for j in self.jobs(tid) if j["id"]==jid)
    def _run_task(self,jid,tid,resume):
        try:
            with self.ws.connection() as c:
                if not c.execute("UPDATE automation_v2_jobs SET status='running' WHERE id=? AND status='queued'",(jid,)).rowcount:return
                source=c.execute("SELECT source_sha FROM automation_v2_jobs WHERE id=?",(jid,)).fetchone()[0]
            if source!=execution_source_sha():raise DesignError("排队期间代码改变，停止派发，请重新核查。")
            co=ResearchService(AssistantWorkspace(GeneralWorkspace(self.ws.root))).automation_v2()
            # A queued pause/cancel takes precedence; resume never comes from refresh.
            if resume:co.resume(tid,human_confirmed=True)
            t=co.run(tid)
            with self.ws.connection() as c:c.execute("UPDATE automation_v2_jobs SET status=?,finished=?,error_note=? WHERE id=?",(t["status"],now(),t["reason"],jid))
        except Exception as exc:
            note=str(exc)[:500] if isinstance(exc,DesignError) else "后台任务未完成："+type(exc).__name__+"；请保留证据并核查。"
            with self.ws.connection() as c:c.execute("UPDATE automation_v2_jobs SET status='interrupted',finished=?,error_note=? WHERE id=?",(now(),note,jid))

