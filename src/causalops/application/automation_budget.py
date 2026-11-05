
"""Task-scoped durable physical-request/revision ledger. No credentials or payloads."""
from __future__ import annotations
import contextvars,json,time,uuid
from contextlib import contextmanager
from causalops.general.service import DesignError

class BudgetExceeded(DesignError): pass
_CURRENT=contextvars.ContextVar("automation_model_budget",default=None)

def active_budget():
    return _CURRENT.get()

class BudgetLedger:
    POLICY={"version":"bounded-v2-2","physical_requests":12,"semantic_revisions":2,
            "tool_attempts":2,"payload_bytes":131072,"cost_warning_cny":1.0}
    def __init__(self,ws,task_id):
        self.ws,self.task_id=ws,task_id
        with ws.connection() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS automation_v2_budget(
                    task_id TEXT PRIMARY KEY, policy TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS automation_v2_model_requests(
                    id TEXT PRIMARY KEY,task_id TEXT NOT NULL,purpose TEXT NOT NULL,
                    config TEXT NOT NULL,payload_bytes INTEGER NOT NULL,created REAL NOT NULL,
                    status TEXT NOT NULL,receipt TEXT,finished REAL);
                CREATE TABLE IF NOT EXISTS automation_v2_budget_stops(
                    id TEXT PRIMARY KEY,task_id TEXT NOT NULL,reason TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS automation_v2_prices(
                    task_id TEXT PRIMARY KEY,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS automation_v2_revisions(
                    task_id TEXT NOT NULL,revision_key TEXT NOT NULL,created REAL NOT NULL,
                    PRIMARY KEY(task_id,revision_key));
            """)
            if not c.execute("SELECT 1 FROM automation_v2_tasks WHERE id=?",(task_id,)).fetchone():
                raise DesignError("预算必须属于已存在的自动化任务。")
            c.execute("INSERT OR IGNORE INTO automation_v2_budget VALUES(?,?)",(task_id,json.dumps(self.POLICY)))
    def validate_policy(self):
        with self.ws.connection() as c:
            row=c.execute("SELECT policy FROM automation_v2_budget WHERE task_id=?",(self.task_id,)).fetchone()
        if not row or json.loads(row[0])!=self.POLICY:raise BudgetExceeded("资源政策版本不一致，须重新审核。")

    def configure_price(self,*,model,input_cny_per_million,output_cny_per_million,source,version):
        """Caller supplies and reviews a dated price; never infer a provider tariff."""
        import math
        if not source.startswith("https://") or not version or not model:raise DesignError("价格快照须有模型、HTTPS来源与版本。")
        if any(not math.isfinite(x) or x<0 for x in (input_cny_per_million,output_cny_per_million)):
            raise DesignError("价格须为有限非负值。")
        body=dict(model=model,input_cny_per_million=input_cny_per_million,output_cny_per_million=output_cny_per_million,source=source,version=version)
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            prior=c.execute("SELECT body FROM automation_v2_prices WHERE task_id=?",(self.task_id,)).fetchone()
            if prior:
                if json.loads(prior[0])!=body:raise DesignError("价格快照不可原地改写。")
                return
            if c.execute("SELECT 1 FROM automation_v2_model_requests WHERE task_id=?",(self.task_id,)).fetchone():raise DesignError("已有请求，不能事后补价格改变原估算。")
            c.execute("INSERT INTO automation_v2_prices VALUES(?,?)",(self.task_id,json.dumps(body)))

    def _price(self):
        with self.ws.connection() as c:r=c.execute("SELECT body FROM automation_v2_prices WHERE task_id=?",(self.task_id,)).fetchone()
        return json.loads(r[0]) if r else None

    def check(self):
        self.validate_policy()
        with self.ws.connection() as c:
            row=c.execute("SELECT status FROM automation_v2_tasks WHERE id=?",(self.task_id,)).fetchone()
        if row[0] not in ("candidate","approved","running"):
            raise BudgetExceeded("任务已停止、暂停或终结，禁止新增模型请求。")
        if self.snapshot()["estimated_cost_cny"]>=1:
            raise BudgetExceeded("已达到1元估算成本预警；暂停外发并请求人工核查。")
    def _record_stop(self,reason):
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO automation_v2_budget_stops VALUES(?,?,?,?)",(uuid.uuid4().hex,self.task_id,reason,time.time()))
            c.execute("UPDATE automation_v2_tasks SET status=CASE WHEN status='running' THEN 'pause_requested' ELSE 'paused' END,reason=? WHERE id=? AND status IN ('candidate','approved','running')",
                      ("资源检查停止："+reason+" 请核查预算；已有Run保留，可只读导出。",self.task_id))

    def reserve_model(self,purpose,config,payload_bytes):
        try:return self._reserve_model(purpose,config,payload_bytes)
        except BudgetExceeded as exc:
            self._record_stop(str(exc))
            raise

    def _reserve_model(self,purpose,config,payload_bytes):
        self.check()
        if type(payload_bytes) is not int or not 0<=payload_bytes<=self.POLICY["payload_bytes"]:
            raise BudgetExceeded("模型载荷超过确定性的字节上限。")
        # Only non-secret transport metadata is stored.
        safe={k:config[k] for k in ("provider","model","api_mode","json_mode","max_output_tokens","timeout_seconds") if k in config}
        rid=uuid.uuid4().hex
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            status=c.execute("SELECT status FROM automation_v2_tasks WHERE id=?",(self.task_id,)).fetchone()[0]
            if status not in ("candidate","approved","running"):raise BudgetExceeded("停止请求已经生效，禁止外发。")
            costs=c.execute("SELECT receipt FROM automation_v2_model_requests WHERE task_id=?",(self.task_id,)).fetchall()
            if sum((json.loads(r[0]).get("estimated_cost_cny") or 0) for r in costs if r[0])>=1:
                raise BudgetExceeded("估算费用已达1元预警，暂停外发并人工核查。")
            n=c.execute("SELECT count(*) FROM automation_v2_model_requests WHERE task_id=?",(self.task_id,)).fetchone()[0]
            if n>=12:raise BudgetExceeded("单任务12次物理请求预算已耗尽；不能发送第13次。")
            c.execute("INSERT INTO automation_v2_model_requests VALUES(?,?,?,?,?,?,?,NULL,NULL)",
                      (rid,self.task_id,str(purpose)[:80],json.dumps(safe),payload_bytes,time.time(),"reserved_usage_unknown"))
        return rid
    def receipt(self,rid,event):
        safe={k:event[k] for k in ("status","status_code","requested_model","model","input_tokens",
              "output_tokens","total_tokens","latency_ms","error","will_retry") if k in event}
        price=self._price()
        if price and safe.get("model")==price["model"] and type(safe.get("input_tokens")) is int and type(safe.get("output_tokens")) is int:
            safe["estimated_cost_cny"]=(safe["input_tokens"]*price["input_cny_per_million"]+safe["output_tokens"]*price["output_cny_per_million"])/1_000_000
            safe["price_source"]=price["source"];safe["price_version"]=price["version"]
        with self.ws.connection() as c:
            c.execute("UPDATE automation_v2_model_requests SET receipt=?,status=?,finished=? WHERE id=? AND task_id=? AND finished IS NULL",
                      (json.dumps(safe),safe.get("status","unknown"),time.time(),rid,self.task_id))
    def revision(self,key):
        try:return self._revision(key)
        except BudgetExceeded as exc:
            self._record_stop(str(exc))
            raise

    def _revision(self,key):
        if not isinstance(key,str) or not key or len(key)>128:raise DesignError("语义修订须提供稳定内容标识。")
        self.check()
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM automation_v2_revisions WHERE task_id=? AND revision_key=?",(self.task_id,key)).fetchone():return
            if c.execute("SELECT count(*) FROM automation_v2_revisions WHERE task_id=?",(self.task_id,)).fetchone()[0]>=2:
                raise BudgetExceeded("初始候选之后最多两次语义修订；须人工处理。")
            c.execute("INSERT INTO automation_v2_revisions VALUES(?,?,?)",(self.task_id,key,time.time()))
    def snapshot(self):
        with self.ws.connection() as c:
            rows=c.execute("SELECT id,purpose,config,status,receipt,payload_bytes,created,finished FROM automation_v2_model_requests WHERE task_id=? ORDER BY created",(self.task_id,)).fetchall()
            revisions=c.execute("SELECT count(*) FROM automation_v2_revisions WHERE task_id=?",(self.task_id,)).fetchone()[0]
            stops=[dict(reason=r[0],created=r[1]) for r in c.execute("SELECT reason,created FROM automation_v2_budget_stops WHERE task_id=? ORDER BY rowid",(self.task_id,))]
        events=[dict(id=r[0],purpose=r[1],config=json.loads(r[2]),status=r[3],
                     receipt=json.loads(r[4]) if r[4] else {},payload_bytes=r[5],created=r[6],finished=r[7]) for r in rows]
        # No current price is guessed. Unknown usage is never treated as free.
        costs=[e["receipt"].get("estimated_cost_cny") for e in events]
        return dict(policy=self.POLICY,physical_requests=len(events),semantic_revisions=revisions,
                    input_tokens=sum(e["receipt"].get("input_tokens") or 0 for e in events),
                    output_tokens=sum(e["receipt"].get("output_tokens") or 0 for e in events),
                    usage_unknown=sum(e["receipt"].get("input_tokens") is None or e["receipt"].get("output_tokens") is None for e in events),
                    estimated_cost_cny=sum(x for x in costs if x is not None),
                    cost_status="estimated_from_dated_snapshot_unknown_usage_excluded" if self._price() else "unpriced_no_verified_price_snapshot",price_version=self._price(),
                    stops=stops,events=events)
    @contextmanager
    def model_scope(self,purpose,*,binding=None,enabled=True):
        token=_CURRENT.set((self,purpose,binding,enabled))
        try:yield
        finally:_CURRENT.reset(token)

