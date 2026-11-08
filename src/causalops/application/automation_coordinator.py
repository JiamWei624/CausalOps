"""Bounded public-Hillstrom execution with durable reconciliation and safe stops.

V2 approval is separate from legacy workflow approvals. Statistical tasks reuse
TaskRuntime/AnalysisTools and the original research-domain approval checks.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
import os
from causalops.assistant.runtime import alive, process_birth
from causalops.application.automation_budget import BudgetLedger

from causalops.application.automation_contracts import PlanV2, fixed_steps, scope
from causalops.application.configurable_research import parse_plan, ConfigurablePlan, approval_schema, authorized_facts, is_configurable
from causalops.application.data_contracts import DataContract
from causalops.application.locking import flow_lock
from causalops.assistant.runtime import execution_source_sha
from causalops.assistant.service import digest, now
from causalops.execution import _data_fingerprint
from causalops.general.service import DesignError
from causalops.sample_data.hillstrom import ARCHIVE_SHA, SOURCE, cohort, contract


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class BoundedCoordinator:
    def __init__(self, service):
        if service.model is not None:
            raise DesignError("V2第一阶段关闭模型自主规划；请使用无模型的受限执行入口。")
        self.s, self.a, self.ws = service, service.a, service.ws
        with self.ws.connection() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS automation_v2_tasks(
                    id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, session_id TEXT NOT NULL,
                    plan_json TEXT NOT NULL, plan_sha TEXT NOT NULL, source TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS automation_v2_approvals(
                    task_id TEXT PRIMARY KEY, id TEXT UNIQUE NOT NULL, body TEXT NOT NULL,
                    sha TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS automation_v2_steps(
                    task_id TEXT NOT NULL, step_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    status TEXT NOT NULL, assistant_task_id TEXT, input_sha TEXT,
                    output TEXT, output_sha TEXT, started TEXT, finished TEXT, seconds REAL,
                    PRIMARY KEY(task_id,step_id));
                CREATE TABLE IF NOT EXISTS automation_v2_events(
                    task_id TEXT NOT NULL, seq INTEGER NOT NULL, step_id TEXT, event TEXT NOT NULL,
                    body TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(task_id,seq));
            """)

    def _init_control(self,tid):
        with self.ws.connection() as c:
            c.execute("CREATE TABLE IF NOT EXISTS automation_v2_owners(task_id TEXT PRIMARY KEY,token TEXT,owner_pid INTEGER,owner_birth TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS automation_v2_step_attempts(id TEXT PRIMARY KEY,task_id TEXT,step_id TEXT,input_sha TEXT,status TEXT,error_type TEXT,started TEXT,finished TEXT)")
        return BudgetLedger(self.ws,tid)

    def budget(self,tid):
        self.task(tid)
        return self._init_control(tid).snapshot()

    def model_context(self,tid,*,purpose,binding):
        """Internal authorized model work; fixed-chain planning remains closed."""
        t=self.task(tid);self._verify(t)
        if not t["plan"]["model_requests"]:raise DesignError("当前固定计划未批准任何模型步骤，模型自主规划仍关闭。")
        if not self.a.consent_enabled(t["session_id"],binding):
            raise DesignError("该任务未授权此服务接收模型上下文。")
        return self._init_control(tid).model_scope(purpose,binding=binding)

    def _claim_owner(self,tid):
        self._init_control(tid)
        token=uuid.uuid4().hex
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT token,owner_pid,owner_birth FROM automation_v2_owners WHERE task_id=?",(tid,)).fetchone()
            if row and row[0] and alive(row[1],row[2]):
                raise DesignError("旧执行所有者仍有效或身份不明，不能接管。")
            c.execute("INSERT OR REPLACE INTO automation_v2_owners VALUES(?,?,?,?)",
                      (tid,token,os.getpid(),process_birth(os.getpid()) or '?'))
        return token

    def _release_owner(self,tid,token):
        with self.ws.connection() as c:
            c.execute("UPDATE automation_v2_owners SET token=NULL WHERE task_id=? AND token=?",(tid,token))

    def _fault(self,point,tid,step_id):
        """No-op fault seam; tests may terminate a child at a precise durable boundary."""

    def create_hillstrom(self, payload, *, request_id, source_confirmed=False):
        if source_confirmed is not True:
            raise DesignError("请先核对公开来源、随机分配、客户单位与两周访问指标；这不是执行批准。")
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", request_id):
            raise DesignError("请提供稳定且非敏感的请求编号，以防重复提交。")
        # Always validate public provenance, even when a request ID is reused.
        data = cohort(payload)
        request_key = digest({"request_id":request_id})
        with flow_lock(self.ws.root, request_key):
            with self.ws.connection() as c:
                row = c.execute("SELECT id FROM automation_v2_tasks WHERE request_key=?", (request_key,)).fetchone()
            if row:
                return self.task(row[0])
            sid = self.s.create_task(payload=data, name="hillstrom_v2.csv", title="受限自动化：两周访问率")
            self.s.contracts.save(sid, contract(), expected_sha=None, human_confirmed=True)
            binding = self.s.data_binding(sid)
            source = dict(archive_sha256=hashlib.sha256(payload).hexdigest(), source_url=SOURCE,
                          adapter="causalops.sample_data.hillstrom.cohort",
                          adapter_source_sha=execution_source_sha(), derived_data=binding,
                          human_source_confirmed=True, scope=scope())
            plan = PlanV2(plan_id=uuid.uuid4().hex, data=binding, contract_ref=self.s.contracts.ref(sid),
                          scope=scope(), source_sha=digest(source), steps=fixed_steps()).model_dump(mode="json")
            return self._save_candidate(request_key,sid,source,plan)

    def _save_candidate(self,request_key,sid,source,plan):
        tid = uuid.uuid4().hex
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO automation_v2_tasks VALUES(?,?,?,?,?,?,?,?,?)",
                      (tid,request_key,sid,encoded(plan),digest(plan),encoded(source),"candidate",None,now()))
            for ordinal, step in enumerate(plan["steps"]):
                aid = uuid.uuid4().hex if step["kind"]=="statistical" else None
                c.execute("INSERT INTO automation_v2_steps(task_id,step_id,ordinal,status,assistant_task_id) VALUES(?,?,?,?,?)",
                          (tid,step["step_id"],ordinal,"pending",aid))
                if aid:
                    # V2 IDs never live in assistant_plans: legacy accept/execute cannot authorize them.
                    c.execute("INSERT INTO assistant_tasks VALUES(?,?,?,?,?)",
                              (aid,plan["plan_id"],ordinal,"pending",None))
        self._event(tid,None,"candidate_created",{"plan_sha":digest(plan),"mode":"restricted_deterministic","model_calls":0})
        self._init_control(tid)
        return self.task(tid)

    def create_configurable(self,payload,**kwargs):
        from .configurable_research import create
        return create(self,payload,**kwargs)

    def revise_configurable(self,tid,**kwargs):
        from .configurable_research import revise
        return revise(self,tid,**kwargs)

    def _user_events_table(self,c):
        c.execute("CREATE TABLE IF NOT EXISTS configurable_user_events(id TEXT PRIMARY KEY,task_id TEXT,upload_id TEXT,action TEXT,origin TEXT,error_class TEXT,created TEXT)")

    def record_import(self,upload_id):
        self.ws.load_upload(upload_id)
        origin="fixed_browser_test" if os.environ.get("CAUSALOPS_EVENT_ORIGIN")=="fixed_browser_test" else "local_user"
        event_id=uuid.uuid4().hex
        with self.ws.connection() as c:
            self._user_events_table(c)
            c.execute("INSERT INTO configurable_user_events VALUES(?,NULL,?,?,?,?,?)",(event_id,upload_id,"data_imported",origin,None,now()))
        return event_id

    def user_event(self,tid,action,*,error_class=None):
        allowed={"conditions_confirmed","plan_created","review_submitted","execution_started","task_stopped","research_completed","report_viewed","user_restore"}
        if action not in allowed:raise DesignError("未登记的本地行为事件。")
        t=self.task(tid)
        origin="fixed_browser_test" if os.environ.get("CAUSALOPS_EVENT_ORIGIN")=="fixed_browser_test" else "local_user"
        with self.ws.connection() as c:
            self._user_events_table(c)
            c.execute("INSERT INTO configurable_user_events VALUES(?,?,?,?,?,?,?)",(uuid.uuid4().hex,tid,t["plan"]["data"]["upload_id"],action,origin,error_class,now()))

    def task(self, tid):
        if not isinstance(tid,str) or not re.fullmatch(r"[a-f0-9]{32}",tid):
            raise DesignError("自动化任务编号不合法。")
        with self.ws.connection() as c:
            c.row_factory=sqlite3.Row
            row=c.execute("SELECT * FROM automation_v2_tasks WHERE id=?",(tid,)).fetchone()
        if row is None:
            raise DesignError("自动化任务不存在。")
        out=dict(row)
        out["plan"]=json.loads(out.pop("plan_json"))
        out["source"]=json.loads(out["source"])
        return out

    def steps(self,tid):
        self.task(tid)
        with self.ws.connection() as c:
            c.row_factory=sqlite3.Row
            return [dict(r) for r in c.execute("SELECT * FROM automation_v2_steps WHERE task_id=? ORDER BY ordinal",(tid,))]

    def events(self,tid):
        self.task(tid)
        with self.ws.connection() as c:
            return [dict(seq=r[0],step_id=r[1],event=r[2],body=json.loads(r[3]),created=r[4])
                    for r in c.execute("SELECT seq,step_id,event,body,created FROM automation_v2_events WHERE task_id=? ORDER BY seq",(tid,))]

    def _event(self,tid,step,event,body):
        if event=="statistical_dispatch_authorized":self.user_event(tid,"execution_started")
        if event=="step_succeeded" and step=="S05":self.user_event(tid,"research_completed")
        if event in ("blocked","interrupted"):self.user_event(tid,"task_stopped",error_class=event)
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            seq=c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM automation_v2_events WHERE task_id=?",(tid,)).fetchone()[0]
            c.execute("INSERT INTO automation_v2_events VALUES(?,?,?,?,?,?)",(tid,seq,step,event,encoded(body),now()))

    def _binding(self,t):
        p=parse_plan(t["plan"])
        if digest(t["plan"])!=t["plan_sha"] or digest(t["source"])!=p.source_sha:
            raise DesignError("计划或来源指纹不一致。")
        source=t["source"]
        if not isinstance(p,ConfigurablePlan) and (source["archive_sha256"]!=ARCHIVE_SHA or source["source_url"]!=SOURCE or source["human_source_confirmed"] is not True):
            raise DesignError("不是已核验并经人工确认的公开营销来源。")
        if source["derived_data"]!=p.data or source["scope"]!=p.scope:
            raise DesignError("派生数据与纳入范围不匹配。")
        if source["adapter_source_sha"]!=execution_source_sha():
            raise DesignError("代码版本已经变化，不能沿用原候选或批准。")
        if self.s.data_binding(t["session_id"])!=p.data:
            raise DesignError("数据版本已经变化。")
        frame=self.ws.load_upload(p.data["upload_id"])
        if set([p.scope["entity"],p.scope["treatment"],p.scope["outcome"]])-set(frame):
            raise DesignError("缺少必要的实体、分组或访问指标字段。")
        if _data_fingerprint(frame)!=p.data["frame_sha"]:
            raise DesignError("实际分析表与获批数据指纹不同，不能执行。")
        row=self.s.contracts.latest(t["session_id"])
        if not row or self.s.contracts.ref(t["session_id"])!=p.contract_ref:
            raise DesignError("DataContract版本已变化，须重新审核。")
        if isinstance(p,ConfigurablePlan):
            from .configurable_research import binding
            binding(self,t,p)
            return p,frame
        expected=DataContract.model_validate(contract()).model_dump(mode="json")
        if row["body"]!=expected:
            raise DesignError("指标、客户单位、随机化依据或两周窗口与受限场景不一致。")
        return p,frame

    def approve(self,tid,*,expected_plan_sha,human_confirmed=False):
        if human_confirmed is not True:
            raise DesignError("必须由用户明确审核整份计划，模型不能批准。")
        with flow_lock(self.ws.root,tid):
            t=self.task(tid)
            p,_=self._binding(t)
            if expected_plan_sha!=t["plan_sha"]:
                raise DesignError("用户审核的计划版本已经变化。")
            if t["status"] in ("approved","running","completed","paused"):
                return self._verify(t)  # repeat approval does not mint a new receipt
            if t["status"]!="candidate":
                raise DesignError("当前状态不能批准；请保留记录并建立后继任务。")
            aid=uuid.uuid4().hex
            receipt=dict(schema_version=approval_schema(t),approval_id=aid,task_id=tid,
                         session_id=t["session_id"],plan_id=p.plan_id,plan_sha=t["plan_sha"],
                         data=p.data,contract_ref=p.contract_ref,source_sha=p.source_sha,scope=p.scope,
                         execution_source_sha=execution_source_sha(),approved_at=now(),
                         actor="explicit_human_whole_plan_review",resource_policy=BudgetLedger.POLICY,
                         facts=authorized_facts(t))
            with self.ws.connection() as c:
                c.execute("BEGIN IMMEDIATE")
                c.execute("INSERT INTO automation_v2_approvals VALUES(?,?,?,?,0)",(tid,aid,encoded(receipt),digest(receipt)))
                c.execute("UPDATE automation_v2_tasks SET status='approved' WHERE id=?",(tid,))
            self._event(tid,None,"whole_plan_approved",{"approval_id":aid,"plan_sha":t["plan_sha"]})
            self.user_event(tid,"review_submitted")
            return receipt

    def _verify(self,t):
        p,_=self._binding(t)
        with self.ws.connection() as c:
            row=c.execute("SELECT body,sha,revoked FROM automation_v2_approvals WHERE task_id=?",(t["id"],)).fetchone()
        if not row or row[2]:
            raise DesignError("缺少有效的V2整体人工批准。")
        r=json.loads(row[0])
        if digest(r)!=row[1] or r.get("schema_version")!=approval_schema(t):
            raise DesignError("V2批准收据不合法，不能使用旧版批准。")
        expected=dict(task_id=t["id"],session_id=t["session_id"],plan_id=p.plan_id,plan_sha=t["plan_sha"],
                      data=p.data,contract_ref=p.contract_ref,source_sha=p.source_sha,scope=p.scope,
                      execution_source_sha=execution_source_sha(),resource_policy=BudgetLedger.POLICY,facts=authorized_facts(t))
        if any(r.get(k)!=v for k,v in expected.items()):
            raise DesignError("批准未绑定当前数据、配置、范围、版本或研究事实。")
        return r

    def evidence(self,tid,step_id):
        t=self.task(tid)
        step=next((r for r in self.steps(tid) if r["step_id"]==step_id),None)
        if not step or step["status"]!="succeeded" or not step["output"]:
            raise DesignError("上游步骤没有成功且完整的持久化输出："+str(step_id))
        e=json.loads(step["output"])
        if digest(e)!=step["output_sha"]:
            raise DesignError("上游证据内容哈希不匹配："+step_id)
        if (e["task_id"]!=tid or e["plan_sha"]!=t["plan_sha"] or e["plan_id"]!=t["plan"]["plan_id"]
                or e["scope"]!=t["plan"]["scope"] or e["data"]!=t["plan"]["data"]
                or e["contract_ref"]!=t["plan"]["contract_ref"] or e["step_id"]!=step_id):
            raise DesignError("上游证据不属于当前任务、计划、指标或窗口。")
        with self.ws.connection() as c:
            receipt_row=c.execute("SELECT id,body,sha FROM automation_v2_approvals WHERE task_id=?",(tid,)).fetchone()
        if (not receipt_row or digest(json.loads(receipt_row[1]))!=receipt_row[2]
                or e.get("approval_id")!=receipt_row[0]
                or json.loads(receipt_row[1]).get("plan_sha")!=t["plan_sha"]):
            raise DesignError("上游证据未绑定原整体批准。")
        spec=next(s for s in t["plan"]["steps"] if s["step_id"]==step_id)
        if spec["kind"]=="statistical" and e["body"].get("approval_id")!=e["approval_id"]:
            raise DesignError("统计Run与步骤证据的批准来源不同。")
        if e["schema"]!=spec["output_type"] or e["config_sha"]!=digest(spec) or set(e["upstreams"])!=set(spec["depends_on"]):
            raise DesignError("步骤配置或依赖证据不一致。")
        for parent,sha in e["upstreams"].items():
            if digest(self.evidence(tid,parent))!=sha:
                raise DesignError("上游输出已变化，不能继续沿用门禁结果。")
        if spec["kind"]=="statistical":
            self._load_stat(t,step,e["body"])
        return e

    def _load_stat(self,t,step,body,*,reconciling=False):
        from causalops.assistant.contracts import ToolResult
        saved=ToolResult.model_validate(body["tool_result"])
        expected=next(x for x in t["plan"]["steps"] if x["step_id"]==step["step_id"])
        if (saved.plan_id!=t["plan"]["plan_id"] or saved.plan_sha!=t["plan_sha"]
                or saved.ordinal!=step["ordinal"] or body["run_id"]!=saved.run_id):
            raise DesignError("统计Run的计划、步骤或运行编号不匹配。")
        actual=self.a.tools.envelope(t["plan"]["data"]["upload_id"],saved.ref,plan_id=saved.plan_id,
                                     plan_sha=saved.plan_sha,ordinal=saved.ordinal)
        expected_frame_sha=t["plan"]["data"]["frame_sha"]
        if step["step_id"]=="S04":
            # The existing general tool canonicalizes selected group values to 0/1.
            # Verify that exact transformation instead of comparing unlike tables.
            from causalops.general.service import prepare,GeneralDesign
            prepared_frame,_,_=prepare(self.ws.load_upload(t["plan"]["data"]["upload_id"]),GeneralDesign.model_validate({**expected["config"],"assignment":"randomized"}))
            expected_frame_sha=_data_fingerprint(prepared_frame)
        if actual!=saved or saved.data_fingerprint!=expected_frame_sha:
            raise DesignError("统计输出哈希或数据版本与原运行不一致。")
        with self.ws.connection() as c:
            row=c.execute("SELECT state,result,plan_id,ordinal FROM assistant_tasks WHERE id=?",(step["assistant_task_id"],)).fetchone()
        if (not row or row[2]!=saved.plan_id or row[3]!=saved.ordinal or (not reconciling and (row[0]!="completed" or json.loads(row[1])["contract"]!=saved.model_dump(mode="json")))):
            raise DesignError("Run没有属于当前任务的成功执行记录。")
        if step["step_id"]=="S02":
            bundle=self.a.ex.load(saved.run_id)
            if bundle["design"]!=expected["config"] or body["grouped"]!=bundle["summary"]["grouped"]:
                raise DesignError("描述统计配置或分组输出与真实Run不一致。")
            return bundle
        bundle,record=self.ws.bundle(saved.run_id)
        revision=self.ws.repo.get_revision(record.revision_id)
        cfg={**expected["config"],"assignment":"randomized"}
        if revision.research_notes["general_design"]!=cfg:
            raise DesignError("A/B原研究域配置与已批准步骤不同。")
        if not self.ws.repo.get_approval(record.revision_id):
            raise DesignError("A/B缺少原研究域的批准依据。")
        return bundle

    def _audit(self,t):
        p,frame=self._binding(t)
        sc=p.scope;entity,group,outcome=sc["entity"],sc["treatment"],sc["outcome"]
        required=[entity,group,outcome]
        if frame[required].isna().any().any():
            raise DesignError("必要字段含缺失；本阶段不自动删除样本或填补。")
        if frame[entity].duplicated().any():
            raise DesignError("分析单位标识存在重复，不能把记录数视为独立样本数。")
        if set(frame[group].astype(str))!=set(sc["groups"]):
            raise DesignError("两组不完整或存在未批准组别。")
        if not frame[outcome].isin([0,1]).all():
            raise DesignError("结果指标必须为已确认编码映射后的0/1。")
        from causalops.application.research_quality import audit_research
        audit=audit_research(frame,self.s.contracts.latest(t["session_id"])["body"])
        return dict(rows=len(frame),group_counts={str(k):int(len(g)) for k,g in frame.groupby(group)},
                    unique_entities=int(frame[entity].nunique()),missing_required=0,
                    assignment=sc.get("assignment","randomized"),assignment_evidence=sc["assignment_source"],
                    assignment_evidence_type="source_and_human_confirmed_not_inferred_from_groups" if sc.get("assignment","randomized")=="randomized" else "unknown_not_inferred_from_groups",
                    original_source=t["source"],research_audit=audit)

    def _gate(self,t):
        audit=self.evidence(t["id"],"S01")
        desc=self.evidence(t["id"],"S02")
        rows=desc["body"]["grouped"]
        sc=t["plan"]["scope"]
        if len(rows)!=2 or {r["group_value"] for r in rows}!=set(sc["groups"]) or any(r["field"]!=sc["outcome"] for r in rows):
            raise DesignError("上游分组或指标不完整。")
        total=0;variance=0
        for row in rows:
            if row["rows"]!=row["finite_n"] or row["rows"]<2:
                raise DesignError("各组有效样本必须与记录数相同且至少为2。")
            if row["rows"]!=audit["body"]["group_counts"][row["group_value"]]:
                raise DesignError("上游统计样本与S01审计不一致。")
            if not math.isfinite(row["mean"]) or not 0<=row["mean"]<=1 or not math.isfinite(row["std_ddof1"]):
                raise DesignError("分组均值或变异不符合二元A/B要求。")
            total+=row["rows"];variance+=row["std_ddof1"]**2
        if t["plan"].get("research_path")=="descriptive_binary":
            if total!=audit["body"]["rows"]:raise DesignError("描述路径样本与上游审计不一致。")
            return dict(decision="descriptive_only",descriptive_run_id=desc["body"]["run_id"],
                descriptive_evidence_sha=digest(desc),audit_evidence_sha=digest(audit),sample_size=total,
                checks=["same_plan_data_metric_window","two_groups","complete_cases_without_exclusion","same_sample_counts"],significance_used=False)
        if total<10 or total!=audit["body"]["rows"] or variance<=0:
            raise DesignError("样本总量或组内变异不满足现有A/B工具要求。")
        if sc.get("assignment","randomized")!="randomized":
            raise DesignError("随机分配依据未知：已保留真实描述统计，仅可解释描述性比例差；未授权A/B效果分析。请补充设计来源并创建新候选计划重新审核。")
        return dict(decision="proceed",descriptive_run_id=desc["body"]["run_id"],
                    descriptive_evidence_sha=digest(desc),audit_evidence_sha=digest(audit),
                    sample_size=total,checks=["same_plan_data_metric_window","two_groups",
                    "complete_cases_without_exclusion","same_sample_counts","engine_minimum_sample_and_variation"],
                    significance_used=False)

    def _stat(self,t,step,spec,upstreams):
        receipt=self._verify(t)
        if spec["step_id"]=="S04":
            gate=self.evidence(t["id"],"S03")
            if gate["body"]!=self._gate(t) or gate["body"]["decision"]!="proceed":
                raise DesignError("S03门禁未通过或与真实上游证据不符。")
        facts=receipt["facts"].get(spec["step_id"],{})
        inp=digest({"plan_sha":t["plan_sha"],"step":spec,"upstreams":upstreams,"approval":digest(receipt)})
        token,checkpoint=self.a.runtime.claim(step["assistant_task_id"],inp,max_attempts=2)
        self._event(t["id"],spec["step_id"],"statistical_dispatch_authorized",
                    {"approval_id":receipt["approval_id"],"input_sha":inp,"method":spec["config"]["method"]})
        try:
            with self.a.runtime.heartbeat(step["assistant_task_id"],token):
                design,checkpoint=self.a.tools.prepare(t["plan"]["data"]["upload_id"],spec,facts,checkpoint)
                checkpoint.update(automation_task_id=t["id"],automation_plan_sha=t["plan_sha"],step_id=spec["step_id"],
                                  approval_id=receipt["approval_id"])
                self.a.runtime.checkpoint(step["assistant_task_id"],token,checkpoint)
                self._verify(self.task(t["id"]))
                for parent,sha in upstreams.items():
                    if digest(self.evidence(t["id"],parent))!=sha:
                        raise DesignError("派发前上游证据已变化。")
                if self.task(t["id"])["status"] in ("pause_requested","cancel_requested","paused","cancelled"):
                    raise StopBeforeDispatch("收到停止请求，尚未派发统计工具。")
                self._event(t["id"],spec["step_id"],"step_prepared",{"checkpoint_sha":digest(checkpoint)})
                checkpoint["dispatch_started"]=True
                self.a.runtime.checkpoint(step["assistant_task_id"],token,checkpoint)
                env=self.a.tools.execute(t["plan"]["data"]["upload_id"],design,checkpoint)
                env=env.model_copy(update={"plan_id":t["plan"]["plan_id"],"plan_sha":t["plan_sha"],"ordinal":step["ordinal"]})
                result={**env.ref,"method":env.method,"plan_sha":t["plan_sha"],"contract":env.model_dump(mode="json")}
                self.a.runtime.finish(step["assistant_task_id"],token,"completed",result)
                self._fault("stat_committed",t["id"],spec["step_id"])
        except Exception as exc:
            # A run may already exist. Stage one never replays this uncertain attempt.
            current=self.a.runtime.row(step["assistant_task_id"])
            if current and current["token"]==token:
                self.a.runtime.finish(step["assistant_task_id"],token,"interrupted",
                                      {"error_type":type(exc).__name__,"next_action":"manual_reconcile_no_automatic_retry"},type(exc).__name__)
            # finish may already have committed and released its token. Preserve
            # the original uncertainty instead of replacing it with a fencing error.
            raise
        body=dict(run_id=env.run_id,tool_result=env.model_dump(mode="json"),approval_id=receipt["approval_id"])
        if spec["step_id"]=="S02":
            body["grouped"]=self.a.ex.load(env.run_id)["summary"]["grouped"]
        return body

    def _report(self,t):
        if t["plan"].get("research_path")=="descriptive_binary":
            from .configurable_report import descriptive_manifest
            gate=self.evidence(t["id"],"S03")
            if gate["body"]!=self._gate(t) or gate["body"]["decision"]!="descriptive_only":raise DesignError("描述路径门禁不一致。")
            return descriptive_manifest(t,self.evidence(t["id"],"S02"),self.evidence(t["id"],"S01"),self._verify(t))
        from causalops.results.rate_units import rate_contrast
        desc=self.evidence(t["id"],"S02");effect=self.evidence(t["id"],"S04")
        self.evidence(t["id"],"S03")
        bundle,record=self.ws.bundle(effect["body"]["run_id"])
        rates=rate_contrast(bundle)
        if rates is None or rates["ci_pp"] is None:
            raise DesignError("A/B缺少可核对的概率差或原工具区间，报告不能完整交付。")
        actual=bundle.evidence["interpretation_inputs"]["raw_group_summary"]
        groups={str(r["treatment"]):r for r in actual}
        for row in desc["body"]["grouped"]:
            raw=row["group_value"];sc=t["plan"]["scope"]
            key="0" if raw==sc.get("control_value","0") else "1" if raw==sc.get("treated_value","1") else "invalid"
            if key not in groups or row["rows"]!=groups[key]["n"] or not math.isclose(row["mean"],groups[key]["outcome_mean"],rel_tol=0,abs_tol=1e-10):
                raise DesignError("两个统计Run的分组样本或均值不一致，停止整合。")
        audit=self.evidence(t["id"],"S01")
        if bundle.estimate.sample_size!=audit["body"]["rows"]:
            raise DesignError("A/B样本量与审计不一致。")
        receipt=self._verify(t)
        runs=[desc["body"]["run_id"],effect["body"]["run_id"]]
        if is_configurable(t["plan"]):
            from .configurable_report import complete_report
            return complete_report(t,rates,groups,bundle,record,receipt,runs)
        text=(f"研究目标：{t['plan']['objective']}\n"
              f"未发邮件组两周访问率为{rates['control_rate']:.2%}，男装邮件组为{rates['treated_rate']:.2%}。"
              f"绝对差为{rates['pp']:.2f}个百分点，原工具95%置信区间为"
              f"[{rates['ci_pp'][0]:.2f}, {rates['ci_pp'][1]:.2f}]个百分点。\n"
              f"样本量：未发邮件{groups['0']['n']}名、男装邮件{groups['1']['n']}名，总计{bundle.estimate.sample_size}名客户。"
              "估计对象是分配邮件的意向处理访问概率差；采用原A/B独立组均值差及正态近似区间，未修改估计器。\n"
              f"随机分配和两周窗口依据：{SOURCE}，已经使用者核对，不是由两组或样本均衡推断。"
              "未指定基线协变量，未实施协变量平衡检查；程序不证明无干扰等全部识别假设。"
              "结果仅适用于该公开实验两组客户的分配后两周访问，不代表长期利润、总体营销收益或生产级可靠性。\n"
              f"描述统计Run：{runs[0]}；A/B Run：{runs[1]}；计划：{t['plan']['plan_id']} v1；"
              f"批准：{receipt['approval_id']}。")
        return dict(status="complete",objective=t["plan"]["objective"],scope=t["plan"]["scope"],
                    source_runs=runs,sample_size=bundle.estimate.sample_size,group_summary=actual,
                    effect=rates,standard_error=bundle.estimate.standard_error,
                    method="ab_test",interval_method="independent-group mean difference; normal approximation 1.96",
                    design_source=SOURCE,approval_id=receipt["approval_id"],plan_version=1,
                    domain_revision_id=record.revision_id,model_calls=0,text=text)


    def _inputs(self,t,step):
        self._init_control(t["id"]).validate_policy()
        receipt=self._verify(t)
        spec=next(s for s in t["plan"]["steps"] if s["step_id"]==step["step_id"])
        ups={i:digest(self.evidence(t["id"],i)) for i in spec["depends_on"]}
        inp=digest({"plan_sha":t["plan_sha"],"config":spec,"upstreams":ups})
        return receipt,spec,ups,inp

    def _publish(self,t,step,receipt,spec,upstreams,body,seconds):
        output=dict(schema=spec["output_type"],task_id=t["id"],step_id=step["step_id"],
                    plan_id=t["plan"]["plan_id"],plan_sha=t["plan_sha"],data=t["plan"]["data"],
                    contract_ref=t["plan"]["contract_ref"],scope=t["plan"]["scope"],
                    approval_id=receipt["approval_id"],config_sha=digest(spec),upstreams=upstreams,body=body)
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            n=c.execute("UPDATE automation_v2_steps SET status='succeeded',output=?,output_sha=?,finished=?,seconds=? WHERE task_id=? AND step_id=? AND status!='succeeded'",
                      (encoded(output),digest(output),now(),seconds,t["id"],step["step_id"])).rowcount
            if n!=1:raise DesignError("逻辑步骤已有结果，拒绝再次发布。")
            status=c.execute("SELECT status FROM automation_v2_tasks WHERE id=?",(t["id"],)).fetchone()[0]
            final="cancelled" if status=="cancel_requested" else "paused" if status=="pause_requested" else "completed" if step["step_id"]=="S05" else "approved"
            c.execute("UPDATE automation_v2_tasks SET status=?,reason=NULL WHERE id=?",(final,t["id"]))
        self._event(t["id"],step["step_id"],"step_succeeded",{"output_sha":digest(output),"run_id":body.get("run_id"),"seconds":seconds})

    def advance(self,tid,*,expected_step=None):
        # This fixed plan authorizes zero model calls. Unexpected nested model work
        # fails before HTTP rather than escaping the task's policy.
        ledger=self._init_control(tid)
        with ledger.model_scope("fixed_chain_model_disabled",enabled=False):
            return self._advance_once(tid,expected_step=expected_step)

    def _advance_once(self,tid,*,expected_step=None):
        with flow_lock(self.ws.root,tid):
            t=self.task(tid);steps=self.steps(tid)
            if expected_step:
                chosen=next((x for x in steps if x["step_id"]==expected_step),None)
                if chosen and chosen["status"]=="succeeded":
                    self.evidence(tid,expected_step)
                    return t
            if t["status"]=="completed":self.report(tid);return t
            if t["status"] not in ("approved","running"):
                raise DesignError("任务未批准、已停止或结果不确定；请先核查恢复。")
            step=next((x for x in steps if x["status"]!="succeeded"),None)
            if not step or step["status"]!="pending":raise DesignError("在途结果须先调和，不能直接重算。")
            if expected_step and step["step_id"]!=expected_step:raise DesignError("不能跳过上游步骤或直接派发S04。")
            owner=self._claim_owner(tid);started=time.monotonic();attempt=None
            try:
                receipt,spec,upstreams,inp=self._inputs(t,step)
                with self.ws.connection() as c:
                    c.execute("BEGIN IMMEDIATE")
                    status=c.execute("SELECT status FROM automation_v2_tasks WHERE id=?",(tid,)).fetchone()[0]
                    if status not in ("approved","running"):raise StopBeforeDispatch("停止请求已生效。")
                    n=c.execute("UPDATE automation_v2_steps SET status='running',started=?,input_sha=? WHERE task_id=? AND step_id=? AND status='pending'",(now(),inp,tid,step["step_id"])).rowcount
                    if n!=1:raise DesignError("步骤已被领取。")
                    attempt=uuid.uuid4().hex
                    c.execute("INSERT INTO automation_v2_step_attempts VALUES(?,?,?,?,?,?,?,NULL)",(attempt,tid,step["step_id"],inp,"running",None,now()))
                    c.execute("UPDATE automation_v2_tasks SET status='running' WHERE id=?",(tid,))
                self._event(tid,step["step_id"],"step_started",{"input_sha":inp,"upstreams":upstreams,"attempt_id":attempt})
                self._fault("before_step",tid,step["step_id"])
                if spec["kind"]=="statistical":body=self._stat(t,step,spec,upstreams)
                elif step["step_id"]=="S01":body=self._audit(t)
                elif step["step_id"]=="S03":body=self._gate(t)
                else:body=self._report(t)
                # Revalidate after a long tool call; a changed binding never authorizes its descendants.
                self._inputs(self.task(tid),step)
                self._fault("before_publish",tid,step["step_id"])
                self._publish(t,step,receipt,spec,upstreams,body,time.monotonic()-started)
                with self.ws.connection() as c:c.execute("UPDATE automation_v2_step_attempts SET status='succeeded',finished=? WHERE id=?",(now(),attempt))
            except Exception as exc:
                status="blocked" if isinstance(exc,ValueError) else "interrupted"
                reason=str(exc)[:600] if isinstance(exc,DesignError) else "执行未完成："+type(exc).__name__+"；请先调和，不盲目重试。"
                with self.ws.connection() as c:
                    c.execute("BEGIN IMMEDIATE")
                    current=c.execute("SELECT status FROM automation_v2_tasks WHERE id=?",(tid,)).fetchone()[0]
                    final="cancelled" if current=="cancel_requested" else "paused" if isinstance(exc,StopBeforeDispatch) else status
                    c.execute("UPDATE automation_v2_tasks SET status=?,reason=? WHERE id=?",(final,reason,tid))
                    c.execute("UPDATE automation_v2_steps SET status=?,finished=?,seconds=? WHERE task_id=? AND step_id=? AND status!='succeeded'",
                              (status,now(),time.monotonic()-started,tid,step["step_id"]))
                    if attempt:c.execute("UPDATE automation_v2_step_attempts SET status=?,error_type=?,finished=? WHERE id=?",(status,type(exc).__name__,now(),attempt))
                self._event(tid,step["step_id"],status,{"reason":reason,"exception_type":type(exc).__name__})
            except BaseException:
                # Simulated crash or process termination: preserve owner and uncertain state.
                raise
            else:
                self._release_owner(tid,owner)
                return self.task(tid)
            self._release_owner(tid,owner)
            return self.task(tid)

    def run(self,tid):
        t=self.task(tid)
        for _ in range(7):
            if t["status"] not in ("approved","running"):break
            t=self.advance(tid)
            with self.ws.connection() as c:
                last=c.execute("SELECT error_type FROM automation_v2_step_attempts WHERE task_id=? ORDER BY rowid DESC LIMIT 1",(tid,)).fetchone()
            if t["status"]=="interrupted" and last and last[0] in ("TimeoutError","BlockingIOError","ConnectionError"):
                # Recovery, not a second independent retry layer.
                try:t=self.resume(tid,human_confirmed=True,_automatic=True)
                except DesignError:break
        return t

    def report(self,tid):
        return self.evidence(tid,"S05")["body"]

    def pause(self,tid,*,human_confirmed=False):
        return self._control(tid,"paused",human_confirmed)

    def cancel(self,tid,*,human_confirmed=False):
        return self._control(tid,"cancelled",human_confirmed)

    def _control(self,tid,target,confirmed):
        if confirmed is not True:raise DesignError("停止操作需要明确确认。")
        self.task(tid)
        self._init_control(tid)
        # Separate short transaction: does not wait for the tool's OS dispatch lock.
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            status=c.execute("SELECT status FROM automation_v2_tasks WHERE id=?",(tid,)).fetchone()[0]
            if status==target or status=="cancelled":return self.task(tid)
            if status=="completed":raise DesignError("已完成任务不能改写终态。")
            if status=="cancel_requested":
                owner=c.execute("SELECT token,owner_pid,owner_birth FROM automation_v2_owners WHERE task_id=?",(tid,)).fetchone()
                if owner and owner[0] and alive(owner[1],owner[2]):return self.task(tid)
                c.execute("UPDATE automation_v2_tasks SET status='cancelled',reason='旧进程已失效；保留未核清Run供只读核查，不再派发' WHERE id=?",(tid,))
                return {**self.task(tid),"status":"cancelled"}
            running=c.execute("SELECT 1 FROM automation_v2_steps WHERE task_id=? AND status='running'",(tid,)).fetchone()
            state=("pause_requested" if target=="paused" else "cancel_requested") if running else target
            c.execute("UPDATE automation_v2_tasks SET status=?,reason=? WHERE id=?",(state,"用户请求"+target,tid))
        self._event(tid,None,state,{"next_action":"等待当前步骤安全结束" if running else "已停止派发"})
        return self.task(tid)

    def _reconcile_stat(self,t,step,spec,receipt,upstreams,*,automatic=False):
        aid=step["assistant_task_id"];row=self.a.runtime.row(aid)
        if row and row["token"] and alive(row["owner_pid"],row["owner_birth"]):
            raise DesignError("统计工具旧所有者仍然有效或未知，不能重复恢复。")
        cp=json.loads(row["checkpoint"]) if row and row["checkpoint"] else None
        if cp:
            expected=dict(automation_task_id=t["id"],automation_plan_sha=t["plan_sha"],
                          step_id=step["step_id"],approval_id=receipt["approval_id"])
            if any(cp.get(k)!=v for k,v in expected.items()):raise DesignError("检查点来源与获批逻辑步骤不同。")
            expected_input=digest({"plan_sha":t["plan_sha"],"step":spec,"upstreams":upstreams,"approval":digest(receipt)})
            if row["input_sha"]!=expected_input:raise DesignError("统计检查点输入哈希与上游证据不一致。")
            # Detect orphaned files and ambiguous DB records before trusting reconcile().
            if cp["kind"]=="exploration":
                with self.ws.connection() as c:
                    dbids={r[0] for r in c.execute("SELECT run_id FROM exploration_runs WHERE study_id=?",(cp["study_id"],))}
                directory=self.ws.root/"exploration-runs"/cp["study_id"]
                fileids={p.stem for p in directory.glob("*.json")}
                if dbids!={cp["run_id"]} and dbids:raise DesignError("描述步骤存在多个或不同身份的Run，需人工核查。")
            else:
                with self.ws.connection() as c:
                    rows=c.execute("SELECT run_id,status FROM analysis_runs WHERE session_id=?",(cp["study_id"],)).fetchall()
                dbids={r[0] for r in rows}
                directory=self.ws.root/"runs"/cp["study_id"]
                # Match original evidence/run-<id>.json files; reports are separate artifacts.
                fileids={p.stem[4:] for p in (directory/"evidence").glob("run-*.json") if re.fullmatch(r"run-[a-f0-9]{32}",p.stem)}
                if len(rows)>1 or any(r[1]!="completed" for r in rows):raise DesignError("存在多个或不完整的研究Run，需人工核查。")
            if fileids!=dbids or list(directory.rglob("*.pending")) or list(directory.rglob("*.tmp")):
                raise DesignError("SQLite记录与结果文件不一致，需人工核查，禁止重算。")
            env=self.a.tools.reconcile(t["plan"]["data"]["upload_id"],cp)
            if env is not None:
                if automatic:raise DesignError("已发现持久化Run，需要明确确认后恢复关联。")
                env=env.model_copy(update={"plan_id":t["plan"]["plan_id"],"plan_sha":t["plan_sha"],"ordinal":step["ordinal"]})
                result={**env.ref,"method":env.method,"plan_sha":t["plan_sha"],"contract":env.model_dump(mode="json")}
                body=dict(run_id=env.run_id,tool_result=env.model_dump(mode="json"),approval_id=receipt["approval_id"])
                if step["step_id"]=="S02":body["grouped"]=self.a.ex.load(env.run_id)["summary"]["grouped"]
                self._load_stat(t,step,body,reconciling=True)
                if step["step_id"]=="S04" and self.evidence(t["id"],"S03")["body"]!=self._gate(t):
                    raise DesignError("恢复时S03与真实上游证据不同。")
                # Validate all provenance before repairing the dead worker association.
                with self.ws.connection() as c:
                    c.execute("BEGIN IMMEDIATE")
                    c.execute("UPDATE assistant_tasks SET state='completed',result=? WHERE id=?",(encoded(result),aid))
                    c.execute("UPDATE assistant_checkpoints SET token=NULL,last_status='completed' WHERE task_id=?",(aid,))
                    c.execute("UPDATE assistant_attempts SET status='reconciled',finished=? WHERE task_id=? AND finished IS NULL",(time.time(),aid))
                self._load_stat(t,step,body)
                return body
        with self.ws.connection() as c:
            err=c.execute("SELECT error_type FROM automation_v2_step_attempts WHERE task_id=? AND step_id=? ORDER BY rowid DESC LIMIT 1",(t["id"],step["step_id"])).fetchone()
        attempts=(row or {}).get("attempts",0)
        # No checkpoint implies the required pre-dispatch durable write was never reached.
        safe_before_dispatch=not cp or not cp.get("dispatch_started")
        transient=bool(err and err[0] in ("TimeoutError","BlockingIOError","ConnectionError","StopBeforeDispatch"))
        if attempts>=2 or (not safe_before_dispatch and not transient):
            raise DesignError("不能确认可安全重试的临时失败，或两次工具尝试已用尽；请人工核查。")
        with self.ws.connection() as c:
            c.execute("UPDATE assistant_tasks SET state='interrupted' WHERE id=?",(aid,))
            c.execute("UPDATE assistant_checkpoints SET token=NULL,last_status='interrupted' WHERE task_id=?",(aid,))
            c.execute("UPDATE assistant_attempts SET status='interrupted',finished=? WHERE task_id=? AND finished IS NULL",(time.time(),aid))
        return None

    def resume(self,tid,*,human_confirmed=False,_automatic=False):
        if human_confirmed is not True:raise DesignError("恢复需要明确确认。")
        with flow_lock(self.ws.root,tid):
            t=self.task(tid)
            if t["status"]=="completed":self.report(tid);return t
            if t["status"] in ("cancelled","cancel_requested","candidate","blocked"):
                raise DesignError("终态、确定性阻断或未批准任务不能恢复。")
            if t["status"]=="approved" and all(x["status"] in ("pending","succeeded") for x in self.steps(tid)):
                self._verify(t);return t
            owner=self._claim_owner(tid)
            try:
                restored_started=time.monotonic()
                receipt=self._verify(t)
                self._init_control(tid).validate_policy()
                for step in self.steps(tid):
                    if step["status"]=="succeeded":
                        self.evidence(tid,step["step_id"]);continue
                    if step["status"]=="pending":continue
                    receipt,spec,ups,inp=self._inputs(t,step)
                    if step["input_sha"] and step["input_sha"]!=inp:raise DesignError("逻辑步骤输入已经变化。")
                    body=self._reconcile_stat(t,step,spec,receipt,ups,automatic=_automatic) if spec["kind"]=="statistical" else None
                    if body is not None:
                        self._publish(t,step,receipt,spec,ups,body,time.monotonic()-restored_started)
                        self._event(tid,step["step_id"],"run_reconciled",{"run_id":body["run_id"],"recomputed":False})
                    else:
                        with self.ws.connection() as c:c.execute("UPDATE automation_v2_steps SET status='pending' WHERE task_id=? AND step_id=?",(tid,step["step_id"]))
                with self.ws.connection() as c:
                    c.execute("BEGIN IMMEDIATE")
                    status=c.execute("SELECT status FROM automation_v2_tasks WHERE id=?",(tid,)).fetchone()[0]
                    if status in ("cancelled","cancel_requested"):raise DesignError("取消请求已生效，不能恢复。")
                    c.execute("UPDATE automation_v2_tasks SET status=?,reason=NULL WHERE id=?",("completed" if all(s["status"]=="succeeded" for s in self.steps(tid)) else "approved",tid))
                self._event(tid,None,"reconciled_resume",{"automatic_transient_retry":_automatic})
            except Exception as exc:
                with self.ws.connection() as c:
                    c.execute("UPDATE automation_v2_tasks SET status='paused',reason=? WHERE id=? AND status NOT IN ('cancelled','cancel_requested')",
                              ("恢复核查未通过："+(str(exc)[:500] if isinstance(exc,DesignError) else type(exc).__name__)+"；请核对来源、批准和原Run，必要时新建待审任务。",tid))
                self._event(tid,None,"takeover_required",{"reason":str(exc)[:500] if isinstance(exc,DesignError) else type(exc).__name__})
                raise DesignError("恢复核查未通过；已安全暂停，请查看任务原因。") from exc
            finally:self._release_owner(tid,owner)
        return self.task(tid)


class StopBeforeDispatch(DesignError):
    pass
