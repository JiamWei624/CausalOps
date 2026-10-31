"""SQLite checkpoints and fenced local workers; never infer human approval."""
from __future__ import annotations
import os,time,json,uuid,threading
from contextlib import contextmanager
from causalops.general.service import DesignError

def execution_source_sha():
    import hashlib
    from pathlib import Path
    root=Path(__file__).resolve().parents[1];h=hashlib.sha256()
    for source in sorted(root.rglob('*.py')):
        h.update(source.relative_to(root).as_posix().encode());h.update(source.read_bytes())
    return h.hexdigest()

def process_birth(pid):
    """PID reuse-safe creation token; None means process absent, '?' means unknown."""
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes as w
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
        h=k.OpenProcess(0x1000,False,int(pid))
        if not h:return None if ctypes.get_last_error() in (87,1168) else '?'
        try:
            code=w.DWORD();k.GetExitCodeProcess.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)]
            if not k.GetExitCodeProcess(h,ctypes.byref(code)):return '?'
            if code.value!=259:return None
            values=[w.FILETIME() for _ in range(4)]
            k.GetProcessTimes.argtypes=[w.HANDLE]+[ctypes.POINTER(w.FILETIME)]*4
            if not k.GetProcessTimes(h,*[ctypes.byref(v) for v in values]):return '?'
            return str((values[0].dwHighDateTime<<32)+values[0].dwLowDateTime)
        finally:
            k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle(h)
    try:
        from pathlib import Path
        stat=Path(f'/proc/{pid}/stat')
        if stat.exists():return stat.read_text().rsplit(')',1)[1].split()[19]
        os.kill(pid,0);return '?'
    except ProcessLookupError:return None
    except (OSError,ValueError):return '?'

def alive(pid,birth):
    if not pid:return False
    actual=process_birth(pid)
    return actual is not None and (actual=='?' or birth=='?' or actual==birth)

class TaskRuntime:
    def __init__(self,ws):
        self.ws=ws
        with ws.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS assistant_checkpoints(task_id TEXT PRIMARY KEY,token TEXT,owner_pid INTEGER,owner_birth TEXT,heartbeat REAL,attempts INTEGER NOT NULL DEFAULT 0,input_sha TEXT,checkpoint TEXT,cancel_requested INTEGER NOT NULL DEFAULT 0,last_status TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS assistant_attempts(id TEXT PRIMARY KEY,task_id TEXT,token TEXT,input_sha TEXT,started REAL,finished REAL,status TEXT,error_type TEXT)')
    def row(self,tid):
        with self.ws.connection() as c:
            c.row_factory=__import__('sqlite3').Row;r=c.execute('SELECT * FROM assistant_checkpoints WHERE task_id=?',(tid,)).fetchone()
        return dict(r) if r else None
    def claim(self,tid,input_sha,*,max_attempts=3):
        token=uuid.uuid4().hex;birth=process_birth(os.getpid()) or '?';t=time.time()
        with self.ws.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT state FROM assistant_tasks WHERE id=?',(tid,)).fetchone()
            if not row or row[0] not in ('pending','blocked','interrupted'):raise DesignError('步骤已执行、已取消或仍在运行，不重复启动。')
            c.execute('INSERT OR IGNORE INTO assistant_checkpoints(task_id) VALUES(?)',(tid,))
            old=c.execute('SELECT attempts,input_sha,checkpoint FROM assistant_checkpoints WHERE task_id=?',(tid,)).fetchone()
            # A changed review/config has its own bounded attempts. Old successful runs are retained.
            n=old[0]+1 if old[1]==input_sha else 1
            if n>max_attempts:raise DesignError('相同输入已达到三次尝试上限；请创建修订计划，不无限重试。')
            cp=json.loads(old[2]) if old[1]==input_sha and old[2] else None
            c.execute('UPDATE assistant_checkpoints SET token=?,owner_pid=?,owner_birth=?,heartbeat=?,attempts=?,input_sha=?,checkpoint=?,cancel_requested=0,last_status=? WHERE task_id=?',(token,os.getpid(),birth,t,n,input_sha,json.dumps(cp) if cp else None,'running',tid))
            c.execute("UPDATE assistant_tasks SET state='running' WHERE id=?",(tid,))
            c.execute('INSERT INTO assistant_attempts VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,tid,token,input_sha,t,None,'running',None))
        return token,cp
    def checkpoint(self,tid,token,value):
        with self.ws.connection() as c:
            n=c.execute('UPDATE assistant_checkpoints SET checkpoint=?,heartbeat=? WHERE task_id=? AND token=?',(json.dumps(value,ensure_ascii=False),time.time(),tid,token)).rowcount
            if n!=1:raise DesignError('执行所有权已改变，拒绝写入过期检查点。')
    def finish(self,tid,token,state,result,error_type=None):
        with self.ws.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM assistant_checkpoints WHERE task_id=? AND token=?',(tid,token)).fetchone():raise DesignError('执行令牌已失效，拒绝覆盖任务结果。')
            c.execute('UPDATE assistant_tasks SET state=?,result=? WHERE id=?',(state,json.dumps(result,ensure_ascii=False),tid))
            c.execute('UPDATE assistant_checkpoints SET last_status=?,token=NULL,heartbeat=? WHERE task_id=?',(state,time.time(),tid))
            c.execute('UPDATE assistant_attempts SET status=?,finished=?,error_type=? WHERE task_id=? AND token=?',(state,time.time(),error_type,tid,token))
    @contextmanager
    def heartbeat(self,tid,token):
        stop=threading.Event()
        def tick():
            while not stop.wait(5):
                try:
                    with self.ws.connection() as c:c.execute('UPDATE assistant_checkpoints SET heartbeat=? WHERE task_id=? AND token=?',(time.time(),tid,token))
                except Exception:pass # Recovery still requires proof the owning process is absent.
        worker=threading.Thread(target=tick,name='causalops-heartbeat',daemon=True);worker.start()
        try:yield
        finally:stop.set();worker.join(timeout=1)
    def cancel(self,pid):
        with self.ws.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute("UPDATE assistant_tasks SET state='cancelled' WHERE plan_id=? AND state IN ('pending','blocked','interrupted')",(pid,))
            for (tid,) in c.execute("SELECT id FROM assistant_tasks WHERE plan_id=? AND state='running'",(pid,)).fetchall():
                c.execute('UPDATE assistant_checkpoints SET cancel_requested=1 WHERE task_id=?',(tid,))
    def cancelled(self,tid):return bool((self.row(tid) or {}).get('cancel_requested'))
    def resume(self,pid):
        with self.ws.connection() as c:c.execute("UPDATE assistant_tasks SET state='pending' WHERE plan_id=? AND state='cancelled'",(pid,))
    def attempts(self,tid):
        with self.ws.connection() as c:
            c.row_factory=__import__('sqlite3').Row
            return [dict(r) for r in c.execute('SELECT * FROM assistant_attempts WHERE task_id=? ORDER BY started',(tid,))]
