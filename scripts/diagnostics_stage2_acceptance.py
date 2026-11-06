"""Public real-run and isolated negative acceptance for P1 report service."""
from __future__ import annotations
import argparse
import json
import shutil
import sqlite3
import time
from pathlib import Path
from causalops.application.diagnostics.reports import DiagnosticReportService
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace, digest
from causalops.general.service import GeneralWorkspace, DesignError

def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf8")

def service(root):
    return ResearchService(AssistantWorkspace(GeneralWorkspace(root)))

def markers(s):
    with s.ws.connection() as c:
        return {name:digest([list(r) for r in c.execute("SELECT * FROM "+name)])
                for name in ("analysis_runs","exploration_runs","assistant_plans","automation_v2_tasks",
                             "automation_v2_steps","automation_v2_approvals","assistant_tasks")}

def clone(s, root):
    shutil.copytree(s.ws.root,root)
    with sqlite3.connect(root/"research.sqlite3") as c:
        for rid,bundle,report in c.execute("SELECT run_id,result_bundle_path,report_path FROM analysis_runs").fetchall():
            paths=[str((root/Path(p).resolve().relative_to(s.ws.root)).resolve()) for p in (bundle,report)]
            c.execute("UPDATE analysis_runs SET result_bundle_path=?,report_path=? WHERE run_id=?",(*paths,rid))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); root=args.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    s=service(root/"A");co=s.automation_v2()
    t=co.create_hillstrom(args.archive.read_bytes(),request_id="p1-stage2",source_confirmed=True)
    co.approve(t["id"],expected_plan_sha=t["plan_sha"],human_confirmed=True)
    assert co.run(t["id"])["status"]=="completed"
    before=markers(s);r=DiagnosticReportService(s)
    report=r.post_run(t["id"],session_id=t["session_id"])
    original=co.report(t["id"])
    assert report.results.effect==original["effect"] and not report.suggestions
    assert r.get(report.report_id,session_id=t["session_id"])==report
    assert r.post_run(t["id"],session_id=t["session_id"])==report
    assert before==markers(s)
    save(root/"A-report.json",report.model_dump(mode="json"))
    save(root/"A-checks.json",{"exact_original_effect":original["effect"],"unchanged_markers":before,
                              "two_run_ids":original["source_runs"],"repeat_equal":True})
    b=service(root/"B")
    sid=b.create_task(payload=b"customer,arm,visited\n1,0,0\n2,0,1\n3,1,1\n4,1,0\n",name="synthetic-design-missing.csv")
    b.contracts.save(sid,dict(purpose="causal",analysis_unit="customer",entity="customer",
        treatment="arm",control_value="0",treated_value="1",outcome="visited",
        metric_label="visit rate",metric_kind="binary",metric_unit="probability",metric_window="14 days"),
        human_confirmed=True)
    rb=DiagnosticReportService(b)
    unknown=rb.preflight(sid)
    assert unknown.results.estimate is None and unknown.suggestions[0].rule_id=="PD-02"
    with b.ws.connection() as c:
        no_drafts=c.execute("SELECT count(*) FROM diagnostic_request_drafts").fetchone()[0]==0
        no_runs=c.execute("SELECT count(*) FROM analysis_runs").fetchone()[0]==0
    assert no_drafts and no_runs
    draft=rb.save_draft(unknown.report_id,unknown.suggestions[0].suggestion_id,session_id=sid,
        user_intent="用户明确保存：待补充随机分配设计来源",request_id="explicit-save-1",human_confirmed=True)
    assert draft.execution_authorized is False
    save(root/"B-report.json",unknown.model_dump(mode="json"))
    save(root/"B-draft.json",draft.model_dump(mode="json"))
    save(root/"B-checks.json",{"no_automatic_draft":no_drafts,"no_statistical_runs":no_runs,"explicit_draft_only":True})
    cases=[]
    for damage in ("foreign_run","metric","unit","window","hash"):
        target=root/("C-"+damage);clone(s,target);c=service(target);cc=c.automation_v2()
        good=DiagnosticReportService(c).post_run(t["id"],session_id=t["session_id"])
        foreign=None
        if damage=="foreign_run":
            foreign=cc.create_hillstrom(args.archive.read_bytes(),request_id="foreign-owned-run",source_confirmed=True)
            cc.approve(foreign["id"],expected_plan_sha=foreign["plan_sha"],human_confirmed=True)
            assert cc.run(foreign["id"])["status"]=="completed"
        step="S02" if damage in ("hash","foreign_run") else "S05"
        raw=cc.evidence(foreign["id"] if foreign else t["id"],step)
        if damage=="metric":raw["body"]["scope"]["outcome"]="different_metric"
        if damage=="unit":raw["body"]["effect"]["pp"]=raw["body"]["effect"]["raw"]
        if damage=="window":raw["body"]["scope"]["window"]="7 days"
        sha="0"*64 if damage=="hash" else digest(raw)
        with c.ws.connection() as db:
            db.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id=?",
                       (json.dumps(raw),sha,t["id"],step))
        prior=markers(c);rc=DiagnosticReportService(c)
        blocked=rc.post_run(t["id"],session_id=t["session_id"])
        assert blocked.results.status=="restricted" and blocked.results.effect is None
        assert blocked.suggestions and blocked.version>good.version
        assert prior==markers(c) and rc.get(good.report_id,session_id=t["session_id"])==good
        if foreign:
            assert foreign["id"] not in blocked.model_dump_json()
            assert foreign["session_id"] not in blocked.model_dump_json()
        save(root/("C-"+damage+"-report.json"),blocked.model_dump(mode="json"))
        save(root/("C-"+damage+"-checks.json"),{"original_markers_preserved":prior,"prior_report_preserved":True})
        cases.append({"variant":damage,"report_id":blocked.report_id,"no_statistical_side_effects":True})
    assert markers(s)==before
    summary={"scope":"service_acceptance_not_browser_or_human_test","seconds":time.perf_counter()-start,
             "A_report_id":report.report_id,"B_report_id":unknown.report_id,"C":cases,
             "original_A_preserved":True,"model_requests":0}
    save(root/"summary.json",summary)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=="__main__":
    main()

