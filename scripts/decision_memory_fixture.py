"""Isolated public/synthetic browser controller; never a product memory API."""
from pathlib import Path
import argparse,json,hashlib
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace,digest
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.application.diagnostics.reports import DiagnosticReportService
from causalops.application.diagnostics.workbench import DiagnosticWorkbench
from causalops.application.diagnostics.decisions import ResearchDecisionService
from causalops.assistant.runtime import execution_source_sha

def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf8")
def service(root):return ResearchService(AssistantWorkspace(GeneralWorkspace(root/"workspace")))
def protected(s):
 with s.ws.connection() as c:
  tables={n:digest([list(r) for r in c.execute("SELECT * FROM "+n)]) for n in
   ("analysis_runs","exploration_runs","assistant_plans","workflow_approvals","automation_v2_tasks","automation_v2_approvals")}
 files={p.relative_to(s.ws.root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
   for folder in ("runs","exploration-runs") for p in (s.ws.root/folder).rglob("*") if p.is_file()}
 return {"tables":tables,"statistical_files":files}
def prepare(root,archive):
 root.mkdir(parents=True,exist_ok=False);s=service(root);co=s.automation_v2();r=DiagnosticReportService(s);cases={}
 for label in ("A","C"):
  t=co.create_hillstrom(archive.read_bytes(),request_id="memory-"+label,source_confirmed=True)
  co.approve(t["id"],expected_plan_sha=t["plan_sha"],human_confirmed=True)
  assert co.run(t["id"])["status"]=="completed"
  if label=="C":
   good=co.evidence(t["id"],"S05");dump(root/"C-original-S05.json",good)
   bad=json.loads(json.dumps(good));bad["body"]["scope"]["window"]="受控错误窗口"
   with s.ws.connection() as c:c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S05'",(json.dumps(bad),digest(bad),t["id"]))
  report=r.post_run(t["id"],session_id=t["session_id"])
  cases[label]={"mode":"post_run","task":t["id"],"session":t["session_id"],"report":report.report_id,
    "runs":[x.run_id for x in report.context.run_refs],"suggestions":[x.model_dump(mode="json") for x in report.suggestions]}
 for label in ("B","D"):
  sid=s.create_task(payload=b"customer,arm,visited\n1,0,0\n2,0,1\n3,1,1\n4,1,0\n",name="memory-public-synthetic.csv",title="研究决策演示 · "+label)
  s.contracts.save(sid,dict(purpose="causal",analysis_unit="客户",entity="customer",treatment="arm",outcome="visited",
   control_value="0",treated_value="1",control_label="未接受处理",treated_label="接受处理",metric_label="访问率",
   metric_kind="binary",metric_unit="概率",metric_window="登记14天窗口"),human_confirmed=True)
  report=r.preflight(sid)
  cases[label]={"mode":"preflight","task":sid,"session":sid,"report":report.report_id,
    "suggestions":[x.model_dump(mode="json") for x in report.suggestions]}
 with s.ws.connection() as c:
  old={x[0]:x[1] for x in c.execute("SELECT id,body_sha FROM diagnostic_reports")}
 snapshot={"source_sha":execution_source_sha(),"cases":cases,"protected":protected(s),"old_reports":old}
 dump(root/"fixture.json",snapshot);return snapshot
def inspect(root):
 f=json.loads((root/"fixture.json").read_text(encoding="utf8"));s=service(root);m=ResearchDecisionService(DiagnosticWorkbench(s))
 with s.ws.connection() as c:
  records=[json.loads(r[0]) for r in c.execute("SELECT body FROM research_decisions ORDER BY rowid")]
  reports=[{"id":r[0],"version":r[1],"body_sha":r[2]} for r in c.execute("SELECT id,version,body_sha FROM diagnostic_reports")]
  cnt={n:c.execute("SELECT count(*) FROM "+n).fetchone()[0] for n in
   ("analysis_runs","exploration_runs","assistant_plans","workflow_approvals","automation_v2_approvals","diagnostic_request_drafts","research_decisions","diagnostic_reports")}
 denied=[]
 for d in records:
  try:s.a.accept(d["decision_id"],"0"*64)
  except DesignError:old_gate=True
  else:old_gate=False
  try:s.automation_v2().run(d["decision_id"])
  except DesignError:new_gate=True
  else:new_gate=False
  assert old_gate and new_gate
  denied.append({"decision":d["decision_id"],"legacy_approval_denied":old_gate,"automation_execution_denied":new_gate})
 return {"source_sha":execution_source_sha(),"counts":cnt,"records":records,"reports":reports,
   "protected_unchanged":protected(s)==f["protected"],
   "old_reports_preserved":all(next(x for x in reports if x["id"]==key)["body_sha"]==value for key,value in f["old_reports"].items()),
   "execution_gates":denied}
def mutate(root,mode):
 f=json.loads((root/"fixture.json").read_text(encoding="utf8"));s=service(root)
 label={"next-B":"B","restore-C":"C","stale-D":"D"}[mode];item=f["cases"][label]
 if mode=="restore-C":
  good=json.loads((root/"C-original-S05.json").read_text(encoding="utf8"))
  with s.ws.connection() as c:c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S05'",(json.dumps(good),digest(good),item["task"]))
 else:
  old=s.contracts.latest(item["session"])
  s.contracts.save(item["session"],{**old["body"],"notes":"后续资料复核，未自动补充分配设计事实。"},expected_sha=old["sha"],human_confirmed=True)
 return {"actor":"explicit_test_controller","action":mode,"task":item["task"],"new_statistical_run":False}
def main():
 p=argparse.ArgumentParser();p.add_argument("mode",choices=["prepare","inspect","next-B","restore-C","stale-D"]);p.add_argument("--root",type=Path,required=True);p.add_argument("--archive",type=Path);a=p.parse_args()
 value=prepare(a.root,a.archive) if a.mode=="prepare" else inspect(a.root) if a.mode=="inspect" else mutate(a.root,a.mode)
 print(json.dumps(value,ensure_ascii=False))
if __name__=="__main__":main()
