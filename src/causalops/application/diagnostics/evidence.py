"""Resolve native evidence without calling execution, approval, models or report generation."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path

from causalops.application.automation_contracts import PlanV2
from causalops.application.data_contracts import DataContract
from causalops.assistant.service import digest
from causalops.general.service import DesignError
from causalops.sample_data.hillstrom import ARCHIVE_SHA, SOURCE, contract as fixed_contract

@dataclass
class EvidenceCollection:
    context: dict
    manifest: dict
    contract: dict | None
    task: dict | None = None
    co: object | None = None
    evidence: dict = field(default_factory=dict)
    bundles: dict = field(default_factory=dict)
    inputs: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    data: dict = field(default_factory=dict)

class NativeEvidenceReader:
    """Workspace-local ownership. This is not a multi-user authorization system."""
    def __init__(self, service):
        self.s, self.ws = service, service.ws

    def rows(self, query, args=()):
        with self.ws.connection() as c:
            return [list(r) for r in c.execute(query,args)]

    def session(self,sid):
        if not isinstance(sid,str) or not __import__("re").fullmatch(r"[a-f0-9]{32}",sid):
            raise DesignError("诊断会话标识不合法。")
        rows=self.rows("SELECT id,upload_id FROM assistant_sessions WHERE id=?",(sid,))
        if not rows:raise DesignError("研究任务不可用或不属当前会话。")
        return rows[0][1]

    def file_mark(self,path,base):
        p=Path(path)
        if not p.is_absolute():p=self.ws.root/p
        p=p.resolve()
        if not p.is_relative_to((self.ws.root/base).resolve()):return "invalid_path"
        try:return hashlib.sha256(p.read_bytes()).hexdigest()
        except FileNotFoundError:return "missing"
        except OSError:return "unavailable"

    def contract_row(self,sid,ref=None):
        if ref:
            rows=self.rows("SELECT id,session_id,version,data_sha,body,sha FROM workflow_data_contracts WHERE id=? AND session_id=?",(ref["id"],sid))
        else:
            rows=self.rows("SELECT id,session_id,version,data_sha,body,sha FROM workflow_data_contracts WHERE session_id=? ORDER BY version DESC LIMIT 1",(sid,))
        return rows[0] if rows else None

    def _native(self,sid,*,bound_contract=None):
        uid=self.session(sid)
        rows=self.rows("SELECT frame_sha,parquet_sha,relative_path FROM general_uploads WHERE upload_id=?",(uid,))
        if not rows:raise DesignError("原生上传记录不存在。")
        frame_sha,parquet_sha,path=rows[0]
        manifest={"upload_record_sha":digest(rows),"upload_file_sha":self.file_mark(path,"uploads")}
        errors=[];data={"group_field_present":False,"nonmissing_group_count":None}
        try:frame=self.ws.load_upload(uid)
        except (ValueError,OSError,KeyError) as exc:
            frame=None;errors.append({"code":"data_integrity_unavailable","missing":isinstance(exc,FileNotFoundError)})
        row=self.contract_row(sid,bound_contract)
        manifest["contract_row_sha"]=digest(row)
        body=None;ref=None
        if row:
            try:
                body=DataContract.model_validate_json(row[4]).model_dump(mode="json")
                if digest(body)!=row[5] or row[3]!=frame_sha:raise ValueError("contract binding")
                ref=dict(id=row[0],version=row[2],sha=row[5],data_sha=row[3])
                if bound_contract and ref!=bound_contract:raise ValueError("contract version")
            except (ValueError,TypeError,KeyError):
                body=None;ref=None;errors.append({"code":"contract_integrity_conflict","missing":False})
        elif bound_contract:
            errors.append({"code":"bound_contract_missing","missing":True})
        if frame is not None and body:
            g=body["treatment"]
            data["group_field_present"]=bool(g and g in frame)
            if data["group_field_present"]:
                data["nonmissing_group_count"]=int(frame[g].nunique(dropna=True))
                data["missing_group_records"]=int(frame[g].isna().sum())
                # Read-only structural observation, not a statistical Run or design inference.
                observed={str(v) for v in frame[g].dropna().unique()}
                data["declared_groups_present"]={body["control_value"],body["treated_value"]} <= observed if body["control_value"] is not None and body["treated_value"] is not None else None
        return dict(uid=uid,frame_sha=frame_sha,ref=ref,body=body,manifest=manifest,errors=errors,data=data)

    @staticmethod
    def scope(body,automation=False):
        body=body or {}
        return dict(analysis_unit=body.get("analysis_unit") or None,outcome_field=body.get("outcome") or None,
            metric_label=body.get("metric_label") or None,statistic_type="risk_difference" if automation else None,
            unit=body.get("metric_unit") or None,observation_window=body.get("metric_window") or None,
            group_labels=[v for v in (body.get("control_label"),body.get("treated_label")) if v],
            numerator="各组访问客户数" if automation else None,denominator="各分配组客户数" if automation else None,
            aggregation="组内比例与概率差" if automation else None)

    def preflight(self,sid,requested_window,code_sha):
        n=self._native(sid)
        context=dict(task_ref=dict(kind="research_session",task_id=sid,session_id=sid),plan_ref=None,
            no_plan_reason="只读预诊断；未建立正式统计计划或运行。",
            data_ref=dict(upload_id=n["uid"],frame_sha=n["frame_sha"]),contract_ref=n["ref"],run_refs=[],
            scope=self.scope(n["body"]),phase="preflight",provenance=dict(recorded_execution_source_sha=None,
            diagnostic_source_sha=code_sha,reading_mode="preflight"))
        inputs=[dict(artifact_kind="data_contract",artifact_id=n["ref"]["id"],sha=n["ref"]["sha"])] if n["ref"] else []
        manifest={**n["manifest"],"requested_window":requested_window,"context":context,"errors":n["errors"],"data":n["data"]}
        return EvidenceCollection(context,manifest,n["body"],inputs=inputs,errors=n["errors"],data=n["data"])

    def _run_marks(self,task,steps):
        """Hash only original assistant-owned results; never open a substituted foreign run."""
        marks={}
        for step in steps:
            aid=step["assistant_task_id"]
            if not aid:continue
            rows=self.rows("SELECT plan_id,ordinal,state,result FROM assistant_tasks WHERE id=?",(aid,))
            marks[step["step_id"]]=dict(record=digest(rows))
            if not rows:continue
            plan,ordinal,state,raw=rows[0]
            if plan!=task["plan"]["plan_id"] or ordinal!=step["ordinal"] or state!="completed":continue
            try:
                tr=json.loads(raw)["contract"]
                if tr["plan_id"]!=plan or tr["ordinal"]!=ordinal:continue
                rid=tr["run_id"]
                if step["step_id"]=="S02":
                    records=self.rows("SELECT * FROM exploration_runs WHERE run_id=?",(rid,))
                    if records:marks[step["step_id"]].update(run_record=digest(records),file=self.file_mark(records[0][3],"exploration-runs"))
                else:
                    records=self.rows("SELECT * FROM analysis_runs WHERE run_id=?",(rid,))
                    if records:
                        marks[step["step_id"]].update(run_record=digest(records),file=self.file_mark(records[0][5],"runs"))
                        revision_rows=self.rows("SELECT * FROM draft_revisions WHERE revision_id=?",(records[0][2],))
                        marks[step["step_id"]]["revision"]=digest(revision_rows)
                        marks[step["step_id"]]["domain_approval"]=digest(str(self.ws.repo.get_approval(records[0][2])))
            except (ValueError,KeyError,TypeError,OSError):
                marks[step["step_id"]]["unavailable"]=True
        return marks

    def post_run(self,tid,sid,requested_window,code_sha):
        # Check session identity before even reading another task's statistical artifacts.
        co=self.s.automation_v2()
        t=co.task(tid)
        if t["session_id"]!=sid:raise DesignError("研究任务不可用或不属当前会话。")
        self.session(sid)
        p=t["plan"];steps=co.steps(tid)
        receipts=self.rows("SELECT id,body,sha,revoked FROM automation_v2_approvals WHERE task_id=?",(tid,))
        errors=[]
        try:
            PlanV2.model_validate(p)
            if digest(p)!=t["plan_sha"] or digest(t["source"])!=p["source_sha"]:raise ValueError("identity")
        except (ValueError,KeyError,TypeError):
            errors.append({"code":"plan_or_source_identity_conflict","missing":False})
        n=self._native(sid,bound_contract=p.get("contract_ref"))
        errors.extend(n["errors"])
        if n["body"] and n["body"]!=DataContract.model_validate(fixed_contract()).model_dump(mode="json"):
            errors.append({"code":"fixed_contract_scope_conflict","missing":False})
        source=t["source"]
        if (source.get("archive_sha256")!=ARCHIVE_SHA or source.get("source_url")!=SOURCE
                or source.get("derived_data")!=p.get("data") or source.get("scope")!=p.get("scope")):
            errors.append({"code":"public_source_identity_conflict","missing":False})
        if p.get("data",{}).get("upload_id")!=n["uid"] or p.get("data",{}).get("frame_sha")!=n["frame_sha"]:
            errors.append({"code":"data_identity_conflict","missing":False})
        recorded=source.get("adapter_source_sha")
        receipt=None
        if receipts:
            try:
                receipt=json.loads(receipts[0][1])
                expected=dict(task_id=tid,session_id=sid,plan_id=p["plan_id"],plan_sha=t["plan_sha"],
                    data=p["data"],contract_ref=p["contract_ref"],scope=p["scope"],source_sha=p["source_sha"],
                    execution_source_sha=recorded,actor="explicit_human_whole_plan_review",
                    facts={"S04":{"assignment":"randomized"}})
                if (digest(receipt)!=receipts[0][2] or receipt.get("approval_id")!=receipts[0][0]
                    or receipt.get("schema_version")!="automation-v2-approval-1"
                    or any(receipt.get(k)!=v for k,v in expected.items())):raise ValueError("receipt")
            except (ValueError,KeyError,TypeError):
                errors.append({"code":"original_approval_binding_conflict","missing":False})
        elif any(x["status"]=="succeeded" for x in steps):
            errors.append({"code":"original_approval_missing","missing":True})
        if not isinstance(recorded,str) or not __import__("re").fullmatch("[0-9a-f]{64}",recorded):
            errors.append({"code":"recorded_execution_version_missing","missing":True});recorded=None
        context=dict(task_ref=dict(kind="automation_v2",task_id=tid,session_id=sid),
            plan_ref=dict(id=p["plan_id"],version=p["version"],sha=t["plan_sha"]),
            no_plan_reason=None,data_ref=dict(upload_id=n["uid"],frame_sha=n["frame_sha"]),
            contract_ref=n["ref"],run_refs=[],scope=self.scope(n["body"],True),
            phase="post_run" if t["status"]=="completed" else "partial_run",
            provenance=dict(recorded_execution_source_sha=recorded,diagnostic_source_sha=code_sha,
                reading_mode="historical_read_only"))
        ev={};bundles={};inputs=[]
        if n["ref"]:inputs.append(dict(artifact_kind="data_contract",artifact_id=n["ref"]["id"],sha=n["ref"]["sha"]))
        inputs.append(dict(artifact_kind="source_record",artifact_id=tid,sha=digest(source)))
        # Co.evidence is independent of current-code execution permission.
        if not errors:
            for step in steps:
                if step["status"]!="succeeded":continue
                name=step["step_id"]
                if not step["output"]:
                    errors.append({"code":"step_output_missing","step":name,"missing":True});continue
                try:
                    raw=json.loads(step["output"])
                    if digest(raw)!=step["output_sha"]:raise ValueError("output hash")
                    if step["assistant_task_id"]:
                        owned=self.rows("SELECT plan_id,ordinal,state,result FROM assistant_tasks WHERE id=?",(step["assistant_task_id"],))
                        if not owned or owned[0][:3]!=[p["plan_id"],step["ordinal"],"completed"]:
                            raise ValueError("statistical ownership")
                        saved=json.loads(owned[0][3])["contract"]
                        if saved!=raw["body"]["tool_result"]:raise ValueError("foreign result substitution")
                    checked=co.evidence(tid,name)
                    ev[name]=checked
                    inputs.append(dict(artifact_kind="step_evidence",artifact_id=tid+":"+name,sha=step["output_sha"]))
                    if step["assistant_task_id"]:
                        tr=checked["body"]["tool_result"]
                        context["run_refs"].append(dict(run_id=tr["run_id"],kind=tr["kind"],plan_id=tr["plan_id"],result_fingerprint=tr["result_fingerprint"]))
                        bundles[name]=co._load_stat(t,step,checked["body"])
                        inputs.append(dict(artifact_kind="run_bundle",artifact_id=tr["run_id"],sha=tr["result_fingerprint"]))
                except FileNotFoundError:
                    errors.append({"code":"run_artifact_missing","step":name,"missing":True})
                except (ValueError,KeyError,TypeError,OSError) as exc:
                    errors.append({"code":"step_or_run_integrity_conflict","step":name,"missing":False})
        if errors:
            # Incomplete/foreign evidence is never advertised as a usable Run or check result.
            context["run_refs"]=[];ev={};bundles={};inputs=[]
        manifest={**n["manifest"],"task_sha":digest(t),"steps_sha":digest(steps),
            "original_approval_sha":digest(receipts),"current_contract_ref_sha":digest(self.rows("SELECT id,version,sha,data_sha FROM workflow_data_contracts WHERE session_id=? ORDER BY version DESC LIMIT 1",(sid,))),"run_artifacts":self._run_marks(t,steps),
            "context":context,"requested_window":requested_window,"errors":errors}
        return EvidenceCollection(context,manifest,n["body"],task=t,co=co,evidence=ev,bundles=bundles,
            inputs=inputs,errors=errors,data=n["data"])
