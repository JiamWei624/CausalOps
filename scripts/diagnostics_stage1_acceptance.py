"""Finite service-level acceptance; creates only public/synthetic isolated workspaces.

Usage: python scripts/diagnostics_stage1_acceptance.py --archive <verified.gz> --output <new-directory>
No browser, model, remote service, or production workspace is used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sqlite3
import time
from datetime import datetime,timezone
from pathlib import Path

from causalops.application.diagnostics import DiagnosticService
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace,digest
from causalops.general.service import GeneralWorkspace
from causalops.sample_data.hillstrom import SOURCE,ARCHIVE_SHA,DOWNLOAD
from causalops.results.rate_units import rate_contrast
from causalops.assistant.runtime import execution_source_sha

def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf8")

def service(root):
    return ResearchService(AssistantWorkspace(GeneralWorkspace(root)))

def counts(s):
    with s.ws.connection() as c:
        return {table:c.execute("SELECT count(*) FROM "+table).fetchone()[0]
            for table in ("analysis_runs","exploration_runs","assistant_plans","workflow_approvals","automation_v2_approvals")
            if c.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone()}

def markers(s,tid):
    with s.ws.connection() as c:
        records={t:digest([list(r) for r in c.execute("SELECT * FROM "+t)])
                 for t in ("analysis_runs","exploration_runs","automation_v2_tasks","automation_v2_steps","automation_v2_approvals","assistant_tasks")}
    co=s.automation_v2()
    records["step_evidence"]={step["step_id"]:digest(co.evidence(tid,step["step_id"])) for step in co.steps(tid)}
    return records

def clone(s,target):
    shutil.copytree(s.ws.root,target)
    with sqlite3.connect(target/"research.sqlite3") as db:
        for rid,bundle,report in db.execute("SELECT run_id,result_bundle_path,report_path FROM analysis_runs").fetchall():
            mapped=[str((target/Path(p).resolve().relative_to(s.ws.root)).resolve()) for p in (bundle,report)]
            db.execute("UPDATE analysis_runs SET result_bundle_path=?,report_path=? WHERE run_id=?",(*mapped,rid))
    return service(target)

def main():
    p=argparse.ArgumentParser(description="P1诊断事实层：三类有限服务验收")
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError("输出目录已存在，拒绝覆盖首次证据；请选择新目录。")
    payload=args.archive.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=ARCHIVE_SHA:raise ValueError("公开压缩包指纹不符。")
    args.output.mkdir(parents=True)
    begin=time.perf_counter();root=args.output.resolve();results=[]
    # A: original registered tools, original whole-plan and per-step approval.
    a=service(root/"A-workspace");co=a.automation_v2()
    t=co.create_hillstrom(payload,request_id="stage1-acceptance",source_confirmed=True)
    co.approve(t["id"],expected_plan_sha=t["plan_sha"],human_confirmed=True)
    assert co.run(t["id"])["status"]=="completed"
    before=markers(a,t["id"]);before_counts=counts(a)
    d=DiagnosticService(a);assessment=d.assess(t["id"],session_id=t["session_id"])
    assert len(assessment.context.run_refs)==2 and all(f.status=="verified" for f in assessment.findings)
    assert d.assess(t["id"],session_id=t["session_id"])==assessment
    assert d.get(assessment.assessment_id,session_id=t["session_id"])==assessment
    assert before==markers(a,t["id"]) and counts(a)==before_counts
    runs=co.report(t["id"])["source_runs"];bundle,_=a.ws.bundle(runs[1])
    save(root/"A-input.json",{"source_url":SOURCE,"download_url":DOWNLOAD,"archive_sha256":ARCHIVE_SHA,
        "task_id":t["id"],"plan":t["plan"],"approval_id":co.evidence(t["id"],"S01")["approval_id"]})
    save(root/"A-output.json",assessment.model_dump(mode="json"))
    save(root/"A-checks.json",{"unchanged_markers":before,"run_counts":before_counts,
        "actual_rates":rate_contrast(bundle),"idempotent":True,"all_six_rules_verified":True,
        "unimplemented_rules":list(assessment.coverage.not_implemented)})
    results.append({"scenario":"A","status":"通过","task_id":t["id"],"assessment_id":assessment.assessment_id,
                    "runs":runs,"unchanged":True})
    # B: independent synthetic data, unknown assignment; no V2 Plan or native Run.
    b=service(root/"B-workspace")
    synthetic=b"customer,arm,visited\n1,0,0\n2,0,1\n3,1,1\n4,1,0\n"
    sid=b.create_task(payload=synthetic,name="public-synthetic.csv")
    contract=dict(purpose="causal",analysis_unit="customer",entity="customer",treatment="arm",
        control_value="0",treated_value="1",outcome="visited",metric_label="visit rate",
        metric_unit="probability",metric_kind="binary",metric_window="14 days")
    b.contracts.save(sid,contract,human_confirmed=True)
    before=counts(b);pre=DiagnosticService(b).preflight(sid)
    finding=next(f for f in pre.findings if f.rule.id=="PD-02")
    assert finding.status=="unknown" and finding.severity.level=="major"
    assert before==counts(b) and not pre.context.run_refs and pre.context.plan_ref is None
    save(root/"B-input.json",{"synthetic_csv":synthetic.decode(),"registered_contract":contract})
    save(root/"B-output.json",pre.model_dump(mode="json"))
    save(root/"B-checks.json",{"before":before,"after":counts(b),"no_plan_approval_or_run_created":True})
    results.append({"scenario":"B","status":"正确澄清","assessment_id":pre.assessment_id,"unchanged":True})
    # C: controlled copies; first prove valid, then inject each conflict without touching A.
    for damage in ("foreign_run","report_metric","report_window","content_hash"):
        c=clone(a,root/("C-"+damage+"-workspace"));cc=c.automation_v2();dd=DiagnosticService(c)
        assert all(f.status=="verified" for f in dd.assess(t["id"],session_id=t["session_id"]).findings)
        foreign=None
        if damage=="foreign_run":
            foreign=cc.create_hillstrom(payload,request_id="independent-task",source_confirmed=True)
            cc.approve(foreign["id"],expected_plan_sha=foreign["plan_sha"],human_confirmed=True)
            assert cc.run(foreign["id"])["status"]=="completed"
        step="S02" if damage in ("foreign_run","content_hash") else "S05"
        raw=cc.evidence(t["id"],step)
        if damage=="foreign_run":raw=cc.evidence(foreign["id"],"S02")
        elif damage=="report_metric":raw["body"]["scope"]["outcome"]="unmatched_target"
        elif damage=="report_window":raw["body"]["scope"]["window"]="unmatched_window"
        sha="0"*64 if damage=="content_hash" else digest(raw)
        with c.ws.connection() as db:
            db.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id=?",
                (json.dumps(raw),sha,t["id"],step))
        prior=counts(c);out=dd.assess(t["id"],session_id=t["session_id"])
        assert out.conclusion_policy=="hide_integrated_estimate" and prior==counts(c)
        if foreign:assert foreign["id"] not in out.model_dump_json() and foreign["session_id"] not in out.model_dump_json()
        save(root/("C-"+damage+"-input.json"),{"controlled_copy":True,"damage":damage,"step":step,"original_task_id":t["id"],
            "copy_paths_relocated_before_injection":True})
        save(root/("C-"+damage+"-output.json"),out.model_dump(mode="json"))
        results.append({"scenario":"C","variant":damage,"status":"正确限制结论","assessment_id":out.assessment_id,
                        "no_additional_statistics":True})
    # Compare A again, using its saved check manifest, after all C copy operations.
    assert markers(a,t["id"])==json.loads((root/"A-checks.json").read_text(encoding="utf8"))["unchanged_markers"]
    summary={"timestamp":datetime.now(timezone.utc).isoformat(),"execution_source_sha":execution_source_sha(),
        "scope":"service_acceptance_not_browser_or_human_user_test","model_requests":0,
        "seconds":time.perf_counter()-begin,"results":results,"original_A_preserved":True}
    save(root/"summary.json",summary);print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":main()
