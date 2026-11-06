"""Controller-only public/synthetic fixture setup and read-only browser scoring.

No tested user action is substituted with a backend call. C mutations are
explicit isolated fixture injections before the user-facing diagnostic request.
"""
from __future__ import annotations
import argparse,json,sqlite3,hashlib
from pathlib import Path
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace,digest
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.application.diagnostics.reports import DiagnosticReportService
from causalops.assistant.runtime import execution_source_sha

def service(home):return ResearchService(AssistantWorkspace(GeneralWorkspace(home)))
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf8")
def guards(s):
    with s.ws.connection() as c:
        tables=("analysis_runs","exploration_runs","assistant_plans","workflow_approvals",
                "automation_v2_tasks","automation_v2_steps","automation_v2_approvals","assistant_tasks")
        marks={name:digest([list(r) for r in c.execute("SELECT * FROM "+name)]) for name in tables}
    files={p.relative_to(s.ws.root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for folder in ("runs","exploration-runs") for p in (s.ws.root/folder).rglob("*") if p.is_file()}
    return {"tables":marks,"statistical_files":files}

def prepare(root,archive):
    root.mkdir(parents=True,exist_ok=False);s=service(root/"workspace");co=s.automation_v2()
    payload=archive.read_bytes();cases={}
    def native(name):
        t=co.create_hillstrom(payload,request_id=name,source_confirmed=True)
        co.approve(t["id"],expected_plan_sha=t["plan_sha"],human_confirmed=True)
        assert co.run(t["id"])["status"]=="completed"
        return t
    a=native("browser-A-existing")
    cases["A"]={"task":a["id"],"session":a["session_id"],"runs":co.report(a["id"])["source_runs"],"effect":co.report(a["id"])["effect"]}
    r=DiagnosticReportService(s)
    for damage in ("foreign","metric","unit","window","hash"):
        t=native("browser-C-"+damage)
        good=r.post_run(t["id"],session_id=t["session_id"])
        step="S02" if damage in ("hash","foreign") else "S05"
        raw=co.evidence(a["id"] if damage=="foreign" else t["id"],step)
        if damage=="metric":raw["body"]["scope"]["outcome"]="wrong_target"
        if damage=="unit":raw["body"]["effect"]["pp"]=raw["body"]["effect"]["raw"]
        if damage=="window":raw["body"]["scope"]["window"]="wrong_window"
        sha="0"*64 if damage=="hash" else digest(raw)
        with s.ws.connection() as c:
            c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id=?",(json.dumps(raw),sha,t["id"],step))
        cases["C-"+damage]={"task":t["id"],"session":t["session_id"],"old_report":good.report_id,"injection":damage}
    sid=s.create_task(payload=b"customer,arm,visited\n1,0,0\n2,0,1\n3,1,1\n4,1,0\n",
        name="synthetic-design-source.csv",title="合成研究：待补充分配设计来源")
    s.contracts.save(sid,dict(purpose="causal",analysis_unit="客户",entity="customer",treatment="arm",
        control_value="0",treated_value="1",control_label="未接受处理",treated_label="接受处理",
        outcome="visited",metric_label="访问率",metric_kind="binary",metric_unit="概率",metric_window="登记的14天窗口"),
        human_confirmed=True)
    cases["B"]={"task":sid,"session":sid,"synthetic":True,"assignment_evidence":"unknown"}
    snapshot={"source_sha":execution_source_sha(),"workspace":"workspace","cases":cases,
              "setup_mode":"controller_fixture_only_not_browser_actions","baseline":guards(s)}
    save(root/"fixture.json",snapshot);return snapshot

def inspect(root):
    fixture=json.loads((root/"fixture.json").read_text(encoding="utf8"));s=service(root/"workspace")
    with s.ws.connection() as c:
        counts={name:c.execute("SELECT count(*) FROM "+name).fetchone()[0] for name in
            ("analysis_runs","exploration_runs","automation_v2_approvals","assistant_plans","workflow_approvals","diagnostic_reports","diagnostic_request_drafts")}
        reports=[json.loads(x[0]) for x in c.execute("SELECT body FROM diagnostic_reports ORDER BY rowid")]
        drafts=[json.loads(x[0]) for x in c.execute("SELECT body FROM diagnostic_request_drafts ORDER BY rowid")]
    authority=[]
    for d in drafts:
        denied=False
        try:s.a.accept(d["draft_id"],"0"*64)
        except DesignError:denied=True
        authority.append({"draft_id":d["draft_id"],"legacy_plan_gate_denied":denied,"execution_authorized":d["execution_authorized"]})
        assert denied and not d["execution_authorized"]
    return {"counts":counts,"guards":guards(s),"reports":reports,"drafts":drafts,"draft_authority":authority,
            "fixture_source_sha":fixture["source_sha"],"source_sha":execution_source_sha()}

def stale(root):
    fixture=json.loads((root/"fixture.json").read_text(encoding="utf8"));s=service(root/"workspace");sid=fixture["cases"]["B"]["session"]
    old=s.contracts.latest(sid)
    new=s.contracts.save(sid,{**old["body"],"metric_window":"受控变更后的7天窗口"},expected_sha=old["sha"],human_confirmed=True)
    return {"actor":"controller_injection","case":"B-stale-source","old_contract":old["id"],"new_contract":new["id"],
            "no_statistical_execution":True}

def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["prepare","inspect","stale"])
    p.add_argument("--root",type=Path,required=True);p.add_argument("--archive",type=Path)
    a=p.parse_args();value=prepare(a.root.resolve(),a.archive) if a.mode=="prepare" else inspect(a.root.resolve()) if a.mode=="inspect" else stale(a.root.resolve())
    print(json.dumps(value,ensure_ascii=False))
if __name__=="__main__":main()
