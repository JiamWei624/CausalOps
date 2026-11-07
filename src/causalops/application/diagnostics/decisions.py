"""Append-only local decisions and conservative, evidence-bound historical reminders."""
from dataclasses import dataclass
import json,sqlite3
from causalops.assistant.service import digest
from causalops.general.service import DesignError
from causalops.application.data_contracts import DataContract
from .decision_contracts import ResearchDecision,TYPE_LABELS,make_decision,decision_content
from .report_contracts import STATE_LABELS

@dataclass(frozen=True)
class DecisionHistoryEntry:
    decision:ResearchDecision
    origin_verified:bool
    origin_error:str|None
    superseded_by:str|None

@dataclass(frozen=True)
class DecisionReminder:
    decision_id:str
    prior_report_id:str
    current_report_id:str
    rule_id:str
    kind:str
    current_status:str|None
    message:str

class DecisionRepository:
    def __init__(self,ws):
        self.ws=ws
        with ws.connection() as c:
            c.executescript("""
              CREATE TABLE IF NOT EXISTS research_decisions(
                id TEXT PRIMARY KEY,session_id TEXT NOT NULL,task_id TEXT NOT NULL,
                report_id TEXT NOT NULL,suggestion_id TEXT,supersedes_id TEXT UNIQUE,
                body TEXT NOT NULL,body_sha TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS research_decisions_task ON research_decisions(session_id,task_id);
              CREATE TRIGGER IF NOT EXISTS research_decisions_no_update
                BEFORE UPDATE ON research_decisions BEGIN SELECT RAISE(ABORT,'immutable research decision'); END;
              CREATE TRIGGER IF NOT EXISTS research_decisions_no_delete
                BEFORE DELETE ON research_decisions BEGIN SELECT RAISE(ABORT,'immutable research decision'); END;
            """)

    @staticmethod
    def decode(row):
        body=json.loads(row[6])
        if digest(body)!=row[7]:raise DesignError("研究决定指纹不一致，未使用其内容。")
        d=ResearchDecision.model_validate(body)
        if ((d.decision_id,d.context.task_ref.session_id,d.context.task_ref.task_id,d.report_id,d.suggestion_id,d.supersedes_id)!=tuple(row[:6])
            or d.decision_id!=digest({"research_decision_v1":decision_content(d)})):
            raise DesignError("研究决定身份或来源列冲突。")
        return d

    def get(self,identifier,sid,tid):
        with self.ws.connection() as c:
            row=c.execute("SELECT * FROM research_decisions WHERE id=? AND session_id=? AND task_id=?",(identifier,sid,tid)).fetchone()
        if row is None:raise DesignError("研究决定不存在或不属于当前任务。")
        return self.decode(row)

    def list(self,sid,tid):
        with self.ws.connection() as c:
            rows=c.execute("SELECT * FROM research_decisions WHERE session_id=? AND task_id=? ORDER BY rowid",(sid,tid)).fetchall()
        return [self.decode(r) for r in rows]

    def append(self,c,value):
        d=value;ref=d.context.task_ref
        old=c.execute("SELECT * FROM research_decisions WHERE id=?",(d.decision_id,)).fetchone()
        if old:
            old=self.decode(old)
            if decision_content(old)!=decision_content(d):raise DesignError("重复请求的决定内容冲突。")
            return old
        if d.suggestion_id:
            head=c.execute("SELECT * FROM research_decisions WHERE session_id=? AND task_id=? AND report_id=? AND suggestion_id=? ORDER BY rowid DESC LIMIT 1",
                (ref.session_id,ref.task_id,d.report_id,d.suggestion_id)).fetchone()
            if head and self.decode(head).decision_id!=d.supersedes_id:
                raise DesignError("本报告的建议已有决定，修订必须指向当前记录，不能创建冲突分支。")
        if d.supersedes_id:
            previous=c.execute("SELECT * FROM research_decisions WHERE id=? AND session_id=? AND task_id=?",
                               (d.supersedes_id,ref.session_id,ref.task_id)).fetchone()
            if previous is None:raise DesignError("被修订决定不属于当前任务。")
            previous=self.decode(previous)
            if (previous.report_id==d.report_id and previous.suggestion_id==d.suggestion_id
                and previous.decision_type==d.decision_type and previous.reason==d.reason):
                return previous
            if c.execute("SELECT 1 FROM research_decisions WHERE supersedes_id=?",(d.supersedes_id,)).fetchone():
                raise DesignError("该决定已有后继修订，请核对当前记录。")
        elif d.suggestion_id and c.execute(
            "SELECT 1 FROM research_decisions WHERE session_id=? AND task_id=? AND report_id=? AND suggestion_id=?",
            (ref.session_id,ref.task_id,d.report_id,d.suggestion_id)).fetchone():
            raise DesignError("当前建议已有决定；修改时须明确关联被修订记录。")
        body=d.model_dump(mode="json")
        c.execute("INSERT INTO research_decisions VALUES(?,?,?,?,?,?,?,?)",
            (d.decision_id,ref.session_id,ref.task_id,d.report_id,d.suggestion_id,d.supersedes_id,
             json.dumps(body,ensure_ascii=False,allow_nan=False),digest(body)))
        return d

class _ChangedDuringCheck(Exception):pass

class ResearchDecisionService:
    def __init__(self,workbench):
        self.w=workbench
        self.repo=DecisionRepository(workbench.s.ws)

    def _comparison_key(self,r):
        ctx=r.context
        a=self.w.reports.diagnostics.get(r.assessment_id,session_id=ctx.task_ref.session_id)
        key={"comparable":False,"kind":ctx.task_ref.kind,
             "data":ctx.data_ref.model_dump(mode="json") if ctx.data_ref else None,
             "plan":ctx.plan_ref.model_dump(mode="json") if ctx.plan_ref else None,
             "scope":ctx.scope.model_dump(mode="json"),
             "requested_window":a.input_manifest["native_inputs"]["requested_window"]}
        if not ctx.contract_ref:return key
        row=self.w.reports.diagnostics.reader.contract_row(ctx.task_ref.session_id,ctx.contract_ref)
        if row is None:raise DesignError("原数据合同版本不可读取，不能关联决定。")
        body=DataContract.model_validate_json(row[4]).model_dump(mode="json")
        if (digest(body)!=row[5] or row[0]!=ctx.contract_ref.id or row[2]!=ctx.contract_ref.version
            or row[5]!=ctx.contract_ref.sha or not ctx.data_ref or row[3]!=ctx.data_ref.frame_sha):
            raise DesignError("决定所引用的数据合同身份不一致。")
        fields=("purpose","analysis_unit","entity","time","treatment_time","treatment","outcome",
                "control_value","treated_value","metric_kind","metric_label","metric_unit","metric_window",
                "structure","calendar_rule","calendar_start","calendar_end","measurement","fields",
                "predictors","covariates","instruments","running","cutoff","cohort")
        key["definition"]={name:body[name] for name in fields}
        key["definition"]["research_scope"]={name:body["research"][name] for name in
            ("population","inclusion","comparison","estimand","observation_period")}
        key["comparable"]=bool(ctx.data_ref and all(body[name] is not None and str(body[name]).strip()
            for name in ("analysis_unit","entity","treatment","outcome","control_value","treated_value","metric_label","metric_unit"))
            and body["control_value"]!=body["treated_value"])
        return key

    def _fields(self,r,kind,reason,suggestion_id,supersedes_id):
        suggestion=None;finding=None
        if kind!="note":
            suggestion=next((s for s in r.suggestions if s.suggestion_id==suggestion_id),None)
            if suggestion is None:raise DesignError("只能对本报告实际存在的建议作出决定。")
            finding=next(f for f in r.quality.findings if f.finding_id==suggestion.diagnostic_id)
        elif suggestion_id is not None:raise DesignError("自主研究备注不能冒充建议决定。")
        refs=finding.evidence_refs if finding else tuple({digest(ref.model_dump(mode="json")):ref
            for f in r.quality.findings for ref in f.evidence_refs}.values())
        return dict(context=r.context,report_id=r.report_id,report_version=r.version,
            report_sha=digest(r.model_dump(mode="json")),assessment_id=r.assessment_id,assessment_sha=r.assessment_sha,
            suggestion_id=suggestion.suggestion_id if suggestion else None,
            diagnostic_id=finding.finding_id if finding else None,rule=finding.rule if finding else None,
            finding_status=finding.status if finding else None,finding_result=finding.result.model_dump(mode="json") if finding else None,
            suggestion_action=suggestion.action if suggestion else None,decision_type=kind,reason=reason,
            evidence_refs=refs,comparison_key=self._comparison_key(r),supersedes_id=supersedes_id)

    def _verify_origin(self,d):
        r=self.w.reports.get(d.report_id,session_id=d.context.task_ref.session_id)
        expected=make_decision(self._fields(r,d.decision_type,d.reason,d.suggestion_id,d.supersedes_id))
        if decision_content(expected)!=decision_content(d):raise DesignError("历史决定与原报告、建议或证据不一致。")
        return r

    def history(self,mode,subject):
        item=self.w.subject(mode,subject)
        rows=self.repo.list(item["session_id"],subject)
        successors={d.supersedes_id:d.decision_id for d in rows if d.supersedes_id}
        out=[]
        for d in rows:
            try:
                r=self._verify_origin(d);self.w._binding(r,mode,item)
                ok,error=True,None
            except (ValueError,RuntimeError,OSError,KeyError) as exc:
                ok,error=False,"原报告或合同引用不可核验（"+type(exc).__name__+"）；仅保留历史，不作为当前证据。"
            out.append(DecisionHistoryEntry(d,ok,error,successors.get(d.decision_id)))
        return out

    def get(self,mode,subject,identifier):
        item=self.w.subject(mode,subject)
        d=self.repo.get(identifier,item["session_id"],subject)
        self.w._binding(self._verify_origin(d),mode,item)
        return d

    @staticmethod
    def _compatible(d,r,key):
        if not d.comparison_key.get("comparable") or not key.get("comparable"):return False
        if d.comparison_key!=key:return False
        current={x.run_id:x for x in r.context.run_refs}
        return all(current.get(x.run_id)==x for x in d.context.run_refs)

    def can_supersede(self,entry,r,suggestion_id):
        if not entry.origin_verified or entry.superseded_by:return False
        d=entry.decision
        if d.context.task_ref!=r.context.task_ref or d.report_version>r.version:return False
        s=next((s for s in r.suggestions if s.suggestion_id==suggestion_id),None)
        if suggestion_id is None:
            if d.decision_type!="note":return False
        else:
            if d.rule is None or s is None:return False
            f=next(f for f in r.quality.findings if f.finding_id==s.diagnostic_id)
            if d.rule!=f.rule:return False
        return d.report_id==r.report_id or self._compatible(d,r,self._comparison_key(r))

    def save(self,mode,subject,report_id,decision_type,reason,*,suggestion_id=None,supersedes_id=None,human_confirmed=False):
        if human_confirmed is not True:raise DesignError("研究决定需要用户明确提交，不会自动采纳。")
        if decision_type not in TYPE_LABELS or not isinstance(reason,str) or len(reason)>2000:
            raise DesignError("请提供受支持的决定类型和不超过2000字的原因。")
        reason=reason.strip()
        if decision_type=="note" and not reason:raise DesignError("请填写自主研究决定。")
        # Same-connection data_version detects commits during read validation.
        # The final write lock prevents DB changes before append. Native files are
        # immutable by the application; no grant is created by this transaction.
        for attempt in range(3):
            try:
                with self.w.s.ws.connection() as c:
                    marker=c.execute("PRAGMA data_version").fetchone()[0]
                    view=self.w.load(mode,subject,report_id)
                    if not view.source_current:raise DesignError("报告来源已变化，不能据旧报告保存新决定；请先重新检查。")
                    r=view.report
                    fields=self._fields(r,decision_type,reason,suggestion_id,supersedes_id)
                    d=make_decision(fields)
                    if supersedes_id:
                        previous=self.repo.get(supersedes_id,r.context.task_ref.session_id,subject)
                        old=next(x for x in self.history(mode,subject) if x.decision.decision_id==previous.decision_id)
                        # A repeated request may legitimately name an already revised parent.
                        existing=next((x.decision for x in self.history(mode,subject) if x.decision.decision_id==d.decision_id),None)
                        if not existing and not self.can_supersede(old,r,suggestion_id):
                            raise DesignError("不能跨任务、不同口径或已被替代的决定建立修订关系。")
                    c.execute("BEGIN IMMEDIATE")
                    if c.execute("PRAGMA data_version").fetchone()[0]!=marker:raise _ChangedDuringCheck()
                    return self.repo.append(c,d)
            except _ChangedDuringCheck:
                continue
            except sqlite3.IntegrityError as exc:
                raise DesignError("决定已由另一次提交修订，请刷新核对；原记录保留。") from exc
        raise DesignError("来源在提交期间发生变化，未保存混合记录；请重新核对。")

    def reminders(self,mode,subject,report_id):
        view=self.w.load(mode,subject,report_id);r=view.report
        key=self._comparison_key(r)
        findings={f.rule.id:f for f in r.quality.findings}
        seen=set();out=[]
        for entry in reversed(self.history(mode,subject)):
            d=entry.decision
            if entry.superseded_by or d.rule is None or d.report_version>=r.version:continue
            identity=(d.rule.id,digest(d.comparison_key))
            if identity in seen:continue
            seen.add(identity);f=findings.get(d.rule.id);current=f.status if f else None
            kind="needs_review"
            message="需要人工核对：来源、数据／计划、请求范围、口径或规则版本无法可靠对应；历史决定不作为当前证据。"
            if view.source_current and entry.origin_verified and f and d.rule==f.rule and self._compatible(d,r,key):
                if f.status=="verified":
                    kind="current_verified";message="当前报告此项已核验满足；只说明本次检查结果，原决定及其证据仍保留，不代表全部研究假设成立。"
                elif f.status in ("issue","unknown") and f.result.model_dump(mode="json")==d.finding_result:
                    kind="still_open";message="此前用户选择"+TYPE_LABELS[d.decision_type]+"；本次检查仍为"+STATE_LABELS[f.status]+"，此项尚未核验满足。"
                else:
                    kind="changed";message="本次检查结果或原因已变化，请核对当前证据；不能把旧决定当作新事实。"
            out.append(DecisionReminder(d.decision_id,d.report_id,r.report_id,d.rule.id,kind,current,message))
        return out
