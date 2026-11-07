"""Research decisions: counterexamples before implementation, public/synthetic data only."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from pydantic import ValidationError
from test_diagnostics_stage1 import native,completed,clone_native,counts
from test_automation_v2 import archive
from causalops.general.service import DesignError,GeneralWorkspace
from causalops.assistant.service import AssistantWorkspace
from causalops.application.research_service import ResearchService
from causalops.assistant.service import digest
from causalops.application.diagnostics.workbench import DiagnosticWorkbench
from causalops.application.diagnostics.reports import DiagnosticReportService
from causalops.application.diagnostics.decisions import ResearchDecisionService
from causalops.application.diagnostics.decision_contracts import ResearchDecision

def service(s):return ResearchDecisionService(DiagnosticWorkbench(s))
def pre(s,sid):return DiagnosticReportService(s).preflight(sid)
def advice(r,rule="PD-02"):return next(x for x in r.suggestions if x.rule_id==rule)
def save(m,sid,r,kind="deferred",reason="补充来源后再考虑因果解释",**kw):
 return m.save("preflight",sid,r.report_id,kind,reason,suggestion_id=advice(r).suggestion_id,human_confirmed=True,**kw)
def revised(s,sid,**fields):
 c=s.contracts.latest(sid)
 s.contracts.save(sid,{**c["body"],**fields},expected_sha=c["sha"],human_confirmed=True)
 return pre(s,sid)
def record_count(s):
 with s.ws.connection() as c:return c.execute("SELECT count(*) FROM research_decisions").fetchone()[0]
def guards(s):
 with s.ws.connection() as c:
  names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
  return {n:digest([list(r) for r in c.execute("SELECT * FROM "+n)]) for n in
    ("analysis_runs","exploration_runs","assistant_plans","workflow_approvals","automation_v2_tasks","automation_v2_approvals","diagnostic_assessments","diagnostic_reports","diagnostic_request_drafts") if n in names}

@pytest.mark.parametrize("kind",["accepted","deferred","rejected"])
def test_explicit_decision_binds_original_evidence(native,kind):
 s,sid=native;m=service(s);r=pre(s,sid);before=guards(s)
 with pytest.raises(DesignError):m.save("preflight",sid,r.report_id,kind,"",suggestion_id=advice(r).suggestion_id)
 d=save(m,sid,r,kind)
 assert d.context==r.context and d.report_sha==digest(r.model_dump(mode="json"))
 assert d.report_id==r.report_id and d.assessment_id==r.assessment_id
 assert d.rule.id=="PD-02" and d.suggestion_id==advice(r).suggestion_id
 assert d.finding_status=="unknown" and d.evidence_refs and not d.execution_authorized
 assert d.actor=="explicit_user_submit" and guards(s)==before
 assert m.get("preflight",sid,d.decision_id)==d
 assert m.history("preflight",sid)[0].decision==d

def test_no_suggestion_real_report_allows_explicit_note(completed):
 s,t=completed;m=service(s);r=DiagnosticReportService(s).post_run(t["id"],session_id=t["session_id"]);before=guards(s)
 assert not r.suggestions
 d=m.save("post_run",t["id"],r.report_id,"note","仅解释登记窗口，不外推长期利润",human_confirmed=True)
 assert len(d.context.run_refs)==2 and d.suggestion_id is None and d.rule is None
 assert guards(s)==before and not d.execution_authorized
 with pytest.raises(ValidationError):ResearchDecision.model_validate({**d.model_dump(mode="json"),"execution_authorized":True})

def test_duplicate_trimmed_submission_and_revision_preserve_original(native):
 s,sid=native;m=service(s);r=pre(s,sid);d=save(m,sid,r)
 assert save(m,sid,r,reason="  "+d.reason+"  ")==d
 with pytest.raises(DesignError):save(m,sid,r,"accepted","已有新依据")
 new=save(m,sid,r,"accepted","准备补充来源；不等于批准",supersedes_id=d.decision_id)
 assert new.supersedes_id==d.decision_id and new.decision_id!=d.decision_id
 assert m.get("preflight",sid,d.decision_id)==d and record_count(s)==2
 assert save(m,sid,r,"accepted",new.reason,supersedes_id=d.decision_id)==new
 assert m.history("preflight",sid)[0].superseded_by==new.decision_id
 with pytest.raises(DesignError):save(m,sid,r,"rejected","不处理",supersedes_id=d.decision_id)

def test_custom_notes_are_not_semantically_interpreted(native):
 s,sid=native;m=service(s);r=pre(s,sid)
 d=m.save("preflight",sid,r.report_id,"note","已经随机化且所有假设成立（仅测试用户文字）",human_confirmed=True)
 r2=revised(s,sid,notes="一次新的证据检查")
 assert m.reminders("preflight",sid,r2.report_id)==[]
 assert m.history("preflight",sid)[0].decision==d
 assert next(f for f in r2.quality.findings if f.rule.id=="PD-02").status=="unknown"
 with pytest.raises(DesignError):m.save("preflight",sid,r2.report_id,"note"," ",human_confirmed=True)

def test_new_report_reliably_reminds_same_unknown_without_authority(native):
 s,sid=native;m=service(s);r=pre(s,sid);d=save(m,sid,r)
 r2=revised(s,sid,notes="补充说明，随机化来源仍未知")
 before=guards(s);items=m.reminders("preflight",sid,r2.report_id)
 assert len(items)==1 and items[0].kind=="still_open" and items[0].decision_id==d.decision_id
 assert items[0].current_status=="unknown" and guards(s)==before
 assert m.history("preflight",sid)[0].origin_verified
 assert not DiagnosticWorkbench(s).load("preflight",sid,r.report_id).source_current
 with pytest.raises(DesignError):save(m,sid,r)

def test_cross_report_explicit_revision_is_append_only(native):
 s,sid=native;m=service(s);r=pre(s,sid);d=save(m,sid,r)
 r2=revised(s,sid,notes="新报告")
 new=save(m,sid,r2,"rejected","暂不继续此方向",supersedes_id=d.decision_id)
 assert new.report_id==r2.report_id and new.supersedes_id==d.decision_id
 assert m.get("preflight",sid,d.decision_id)==d
 assert not m.reminders("preflight",sid,r.report_id)

@pytest.mark.parametrize("change",[{"outcome":"arm","treatment":"visited"},{"analysis_unit":"试样记录"},{"metric_unit":"百分数"},{"metric_window":"7 days"},{"control_value":"1","treated_value":"0"}])
def test_changed_scope_requires_review_not_false_recall(native,change):
 s,sid=native;m=service(s);r=pre(s,sid);d=save(m,sid,r)
 r2=revised(s,sid,**change)
 items=m.reminders("preflight",sid,r2.report_id)
 assert len(items)==1 and items[0].kind=="needs_review"
 with pytest.raises(DesignError):save(m,sid,r2,"accepted","不能跨口径覆盖",supersedes_id=d.decision_id)

def test_changed_requested_window_is_not_problem_resolved(native):
 s,sid=native;m=service(s);r=DiagnosticReportService(s).preflight(sid,requested_window="7 days")
 d=m.save("preflight",sid,r.report_id,"deferred","先核对用户请求窗口",suggestion_id=advice(r,"PD-06").suggestion_id,human_confirmed=True)
 current=pre(s,sid);rem=m.reminders("preflight",sid,current.report_id)
 assert rem[0].kind=="needs_review" and rem[0].decision_id==d.decision_id
 assert rem[0].current_status=="verified"

def test_changed_diagnostic_reason_is_not_same_missing_condition(native):
 s,sid=native;m=service(s);r=pre(s,sid);save(m,sid,r)
 current=revised(s,sid,method_facts={"ab_test":{"assignment":"observational"}})
 rem=m.reminders("preflight",sid,current.report_id)
 assert rem[0].kind=="changed" and rem[0].current_status=="issue"

def test_real_repaired_window_evidence_shows_current_check_not_user_resolution(completed,tmp_path):
 base,t=completed;clone_native(base,tmp_path/"case");s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/"case")));m=service(s);co=s.automation_v2()
 good=co.evidence(t["id"],"S05");bad=json.loads(json.dumps(good));bad["body"]["scope"]["window"]="受控错误窗口"
 def put(value):
  with s.ws.connection() as c:c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S05'",(json.dumps(value),digest(value),t["id"]))
 put(bad);old=DiagnosticReportService(s).post_run(t["id"],session_id=t["session_id"])
 d=m.save("post_run",t["id"],old.report_id,"deferred","先核对窗口冲突，不使用联合结论",suggestion_id=advice(old,"PD-06").suggestion_id,human_confirmed=True)
 put(good);current=DiagnosticReportService(s).post_run(t["id"],session_id=t["session_id"]);before=guards(s)
 rem=m.reminders("post_run",t["id"],current.report_id)
 assert rem[0].kind=="current_verified" and rem[0].current_status=="verified"
 assert m.get("post_run",t["id"],d.decision_id)==d and guards(s)==before

def test_other_task_and_wrong_suggestion_cannot_link(native):
 s,sid=native;m=service(s);r=pre(s,sid);d=save(m,sid,r)
 other=s.create_task(payload=b"x\n1\n2\n",name="other.csv");r2=pre(s,other)
 assert not m.history("preflight",other) and not m.reminders("preflight",other,r2.report_id)
 with pytest.raises(DesignError):m.get("preflight",other,d.decision_id)
 with pytest.raises(DesignError):m.save("preflight",other,r.report_id,"note","跨研究",human_confirmed=True)
 with pytest.raises(DesignError):m.save("preflight",sid,r.report_id,"accepted","",suggestion_id="f"*64,human_confirmed=True)
 with pytest.raises(DesignError):m.save("preflight",other,r2.report_id,"note","不能引用其他研究决定",supersedes_id=d.decision_id,human_confirmed=True)

def test_storage_immutable_and_notes_do_not_grant_execution(native):
 s,sid=native;m=service(s);r=pre(s,sid);d=save(m,sid,r);co=s.automation_v2();before=counts(s)
 for sql in ("UPDATE research_decisions SET body='{}'","DELETE FROM research_decisions"):
  with pytest.raises(Exception):
   with s.ws.connection() as c:c.execute(sql)
 with pytest.raises(DesignError):s.a.accept(d.decision_id,"0"*64)
 with pytest.raises(DesignError):co.run(d.decision_id)
 assert m.get("preflight",sid,d.decision_id)==d and counts(s)==before

def test_concurrent_duplicate_and_competing_revision(native):
 s,sid=native;m=service(s);r=pre(s,sid)
 with ThreadPoolExecutor(max_workers=3) as p:rows=list(p.map(lambda _:save(m,sid,r),range(3)))
 assert len({x.decision_id for x in rows})==1 and record_count(s)==1
 old=rows[0]
 def revise(kind):
  try:return save(m,sid,r,kind,kind,supersedes_id=old.decision_id)
  except DesignError:return None
 with ThreadPoolExecutor(max_workers=2) as p:rows=list(p.map(revise,["accepted","rejected"]))
 assert sum(x is not None for x in rows)==1 and record_count(s)==2

def test_stale_current_report_does_not_produce_positive_reminder(native):
 s,sid=native;m=service(s);r=pre(s,sid);save(m,sid,r)
 r2=revised(s,sid,notes="第二版");revised(s,sid,notes="第三版")
 rem=m.reminders("preflight",sid,r2.report_id)
 assert rem and all(x.kind=="needs_review" for x in rem)
 with pytest.raises(DesignError):save(m,sid,r2)

def test_broken_original_report_is_history_warning_not_evidence(native):
 s,sid=native;m=service(s);r=pre(s,sid);save(m,sid,r);r2=revised(s,sid,notes="后继")
 with s.ws.connection() as c:
  c.execute("DROP TRIGGER diagnostic_reports_no_update")
  c.execute("UPDATE diagnostic_reports SET body_sha=? WHERE id=?",("0"*64,r.report_id))
 entries=m.history("preflight",sid)
 assert not entries[0].origin_verified
 assert m.reminders("preflight",sid,r2.report_id)[0].kind=="needs_review"

def test_current_report_decision_cannot_fork_via_another_historical_parent(native):
 s,sid=native;m=service(s);r1=pre(s,sid);d1=save(m,sid,r1)
 r2=revised(s,sid,notes="第二次");d2=save(m,sid,r2)
 r3=revised(s,sid,notes="第三次")
 d3=save(m,sid,r3,"accepted","当前决定",supersedes_id=d1.decision_id)
 with pytest.raises(DesignError):save(m,sid,r3,"rejected","不能另起冲突分支",supersedes_id=d2.decision_id)
 assert record_count(s)==3 and m.get("preflight",sid,d3.decision_id)==d3

def test_source_changed_during_save_is_not_committed(native,monkeypatch):
 s,sid=native;m=service(s);r=pre(s,sid);original=m._fields
 def changed(*a,**kw):
  result=original(*a,**kw);c=s.contracts.latest(sid)
  s.contracts.save(sid,{**c["body"],"notes":"提交时发生版本变化"},expected_sha=c["sha"],human_confirmed=True)
  return result
 monkeypatch.setattr(m,"_fields",changed)
 with pytest.raises(DesignError):save(m,sid,r)
 assert record_count(s)==0
