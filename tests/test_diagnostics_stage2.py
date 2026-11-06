"""Service acceptance for evidence-bound reports and explicit non-executable drafts."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from pydantic import ValidationError
from test_diagnostics_stage1 import native, completed, clone_native, counts, evidence_before, by_rule
from test_automation_v2 import archive
from causalops.application.diagnostics import DiagnosticService
from causalops.application.diagnostics.reports import DiagnosticReportService
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace, digest
from causalops.general.service import GeneralWorkspace, DesignError

def test_preflight_missing_design_no_statistics(native):
    s,sid=native; before=counts(s); reports=DiagnosticReportService(s)
    report=reports.preflight(sid)
    assert report.results.status=="not_run" and report.results.estimate is None
    assert report.context.plan_ref is None and not report.results.runs
    assert next(f for f in report.quality.findings if f.rule.id=="PD-02").status=="unknown"
    assert len(report.suggestions)==1
    assert report.suggestions[0].rule_id=="PD-02"
    assert not report.execution_authorized and report.model_requests==0
    assert counts(s)==before
    with s.ws.connection() as c: assert c.execute("SELECT count(*) FROM diagnostic_request_drafts").fetchone()[0]==0

def test_real_report_binds_original_facts(completed):
    s,t=completed; before=evidence_before(s,t); r=DiagnosticReportService(s)
    out=r.post_run(t["id"],session_id=t["session_id"])
    assert out.results.status=="available" and len(out.results.runs)==2
    original=s.automation_v2().report(t["id"])
    assert out.results.effect==original["effect"]
    assert out.results.sample_size==original["sample_size"]
    assert out.results.original_manifest["sha"]==next(
        r.sha for r in out.quality.findings[0].evidence_refs
        if r.artifact_kind=="step_evidence" and r.artifact_id.endswith(":S05"))
    assert out.results.approval["id"]==original["approval_id"]
    assert out.results.group_summary==tuple(original["group_summary"])
    assert out.quality.unimplemented_rules and not out.suggestions
    assert r.get(out.report_id,session_id=t["session_id"])==out
    assert r.post_run(t["id"],session_id=t["session_id"])==out
    assert evidence_before(s,t)==before

def test_unknown_not_applicable_not_checked_preserved(native):
    s,sid=native;r=DiagnosticReportService(s)
    old=r.preflight(sid)
    row=s.contracts.latest(sid)
    s.contracts.save(sid,{**row["body"],"purpose":"exploratory"},expected_sha=row["sha"],human_confirmed=True)
    new=r.preflight(sid)
    assert {f.status for f in new.quality.findings}=={"verified","not_applicable","not_checked"}
    assert not new.suggestions and new.report_id!=old.report_id and new.version==old.version+1
    assert r.get(old.report_id,session_id=sid)==old
    with pytest.raises(DesignError): r.generate(old.assessment_id,session_id=sid)

def test_draft_requires_explicit_operation_and_binds_evidence(native):
    s,sid=native;r=DiagnosticReportService(s);out=r.preflight(sid);a=out.suggestions[0]; before=counts(s)
    with pytest.raises(DesignError):r.save_draft(out.report_id,a.suggestion_id,session_id=sid,user_intent="补充设计来源",request_id="one",human_confirmed=False)
    draft=r.save_draft(out.report_id,a.suggestion_id,session_id=sid,user_intent="补充设计来源",request_id="one",human_confirmed=True)
    assert draft.status=="needs_information" and not draft.execution_authorized
    assert draft.diagnostic_id==a.diagnostic_id and draft.report_id==out.report_id
    assert r.save_draft(out.report_id,a.suggestion_id,session_id=sid,user_intent="补充设计来源",request_id="one",human_confirmed=True)==draft
    assert r.get_draft(draft.draft_id,session_id=sid)==draft and counts(s)==before
    with pytest.raises(DesignError):r.save_draft(out.report_id,a.suggestion_id,session_id=sid,user_intent="改成已解决",request_id="one",human_confirmed=True)
    with pytest.raises(DesignError):r.save_draft(out.report_id,"invented",session_id=sid,user_intent="其他方法",request_id="two",human_confirmed=True)

def test_isolation_and_immutable_storage(native):
    s,sid=native;r=DiagnosticReportService(s);out=r.preflight(sid)
    with pytest.raises(DesignError):r.get(out.report_id,session_id="f"*32)
    with s.ws.connection() as c:
        with pytest.raises(Exception):c.execute("DELETE FROM diagnostic_reports WHERE id=?",(out.report_id,))
    assert r.get(out.report_id,session_id=sid)==out
    out.results.design_observations["nonmissing_group_count"]=99
    assert r.get(out.report_id,session_id=sid).results.design_observations["nonmissing_group_count"]==2

def test_report_concurrency_one_version(native):
    s,sid=native;r=DiagnosticReportService(s);a=r.diagnostics.preflight(sid)
    with ThreadPoolExecutor(max_workers=3) as pool:
        items=list(pool.map(lambda _:r.generate(a.assessment_id,session_id=sid),range(3)))
    assert len({x.report_id for x in items})==1 and all(x.version==1 for x in items)

def test_rejects_caller_manufactured_findings(native):
    from causalops.application.diagnostics.report_contracts import ResearchSuggestion
    s,sid=native;r=DiagnosticReportService(s);out=r.preflight(sid)
    b=out.suggestions[0].model_dump(mode="json");b["execution_authorized"]=True
    with pytest.raises(ValidationError):ResearchSuggestion.model_validate(b)
    with pytest.raises(DesignError):r.generate("unregistered",session_id=sid)
    assert r.capabilities()["model_enabled"] is False

@pytest.mark.parametrize("damage,rule",[("hash","PD-01"),("window","PD-06"),("unit","PD-09"),("foreign","PD-14"),("sample","PD-07")])
def test_conflict_blocks_numeric_report_and_preserves_history(completed,tmp_path,damage,rule):
    original,t=completed;clone_native(original,tmp_path/"isolated")
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/"isolated")));r=DiagnosticReportService(s)
    good=r.post_run(t["id"],session_id=t["session_id"])
    step="S03" if damage=="sample" else "S05"
    with s.ws.connection() as c:
        row=c.execute("SELECT output,output_sha FROM automation_v2_steps WHERE task_id=? AND step_id=?",(t["id"],step)).fetchone()
        e=json.loads(row[0])
        if damage=="window":e["body"]["scope"]["window"]="7 days"
        if damage=="unit":e["body"]["effect"]["pp"]=e["body"]["effect"]["raw"]
        if damage=="foreign":e["body"]["source_runs"]=["f"*32]*2
        if damage=="sample":e["body"]["sample_size"]+=1
        sha="0"*64 if damage=="hash" else digest(e)
        c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id=?",(json.dumps(e),sha,t["id"],step))
        if damage=="sample":
            changed={"S03":sha}
            for child in ("S04","S05"):
                b=json.loads(c.execute("SELECT output FROM automation_v2_steps WHERE task_id=? AND step_id=?",(t["id"],child)).fetchone()[0])
                b["upstreams"].update({k:v for k,v in changed.items() if k in b["upstreams"]})
                changed[child]=digest(b)
                c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id=?",(json.dumps(b),digest(b),t["id"],child))
    before=evidence_before(s,t);out=r.post_run(t["id"],session_id=t["session_id"])
    assert out.results.status=="restricted" and out.results.effect is None and out.results.estimate is None
    assert any(f.rule.id==rule and f.status=="issue" for f in out.quality.findings)
    assert out.suggestions and all(a.diagnostic_id in {f.finding_id for f in out.quality.findings} for a in out.suggestions)
    assert evidence_before(s,t)==before and out.version==good.version+1
    assert r.get(good.report_id,session_id=t["session_id"])==good



def test_report_contract_rejects_unrelated_or_unperformed_suggestion(native):
    from causalops.application.diagnostics.report_contracts import DiagnosticReportManifest
    s,sid=native;out=DiagnosticReportService(s).preflight(sid)
    for key,value in (("diagnostic_id","0"*64),("rule_id","PD-11"),("reason_code","invented")):
        body=out.model_dump(mode="json");body["suggestions"][0][key]=value
        with pytest.raises(ValidationError):DiagnosticReportManifest.model_validate(body)
    body=out.model_dump(mode="json")
    body["suggestions"][0]["diagnostic_id"]=out.quality.findings[0].finding_id
    with pytest.raises(ValidationError):DiagnosticReportManifest.model_validate(body)

def test_stale_draft_cannot_change_design_and_old_report_readable(native):
    s,sid=native;r=DiagnosticReportService(s);out=r.preflight(sid)
    row=s.contracts.latest(sid)
    s.contracts.save(sid,{**row["body"],"metric_window":"7 days"},expected_sha=row["sha"],human_confirmed=True)
    with pytest.raises(DesignError):
        r.save_draft(out.report_id,out.suggestions[0].suggestion_id,session_id=sid,user_intent="补充依据",
                     request_id="stale",human_confirmed=True)
    assert r.get(out.report_id,session_id=sid)==out
    with s.ws.connection() as c:assert c.execute("SELECT count(*) FROM diagnostic_request_drafts").fetchone()[0]==0

def test_damaged_observation_aborts_report_without_changing_run_state(native):
    s,sid=native;r=DiagnosticReportService(s);a=r.diagnostics.preflight(sid);before=counts(s)
    with s.ws.connection() as c:
        c.execute("DROP TRIGGER diagnostic_observations_no_update")
        c.execute("UPDATE diagnostic_observations SET body_sha=? WHERE assessment_id=?",("0"*64,a.assessment_id))
    with pytest.raises(DesignError):r.generate(a.assessment_id,session_id=sid)
    assert counts(s)==before
    with s.ws.connection() as c:assert c.execute("SELECT count(*) FROM diagnostic_reports").fetchone()[0]==0

def test_requested_window_conflict_is_not_resolved_by_saving_draft(completed,tmp_path):
    original,t=completed;clone_native(original,tmp_path/"copy")
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/"copy")));r=DiagnosticReportService(s)
    report=r.post_run(t["id"],session_id=t["session_id"],requested_window="7 days")
    f=next(f for f in report.quality.findings if f.rule.id=="PD-06")
    assert f.status=="issue" and report.results.status=="restricted"
    suggestion=next(x for x in report.suggestions if x.diagnostic_id==f.finding_id)
    before=evidence_before(s,t)
    r.save_draft(report.report_id,suggestion.suggestion_id,session_id=t["session_id"],
                 user_intent="核对七天指标是否可获得",request_id="window",human_confirmed=True)
    assert r.get(report.report_id,session_id=t["session_id"])==report
    assert evidence_before(s,t)==before
