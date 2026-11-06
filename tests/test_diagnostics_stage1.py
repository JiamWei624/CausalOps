"""Counterexamples precede implementation; no model and no private datasets."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from pydantic import ValidationError
from test_automation_v2 import archive
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace, digest
from causalops.general.service import GeneralWorkspace, DesignError
from causalops.application.diagnostics import DiagnosticService
from causalops.application.diagnostics.contracts import DiagnosticFinding

def clone_native(original,target):
    """A controlled copy must relocate its native absolute RunRecord paths."""
    import shutil,sqlite3
    shutil.copytree(original.ws.root,target)
    with sqlite3.connect(target/"research.sqlite3") as db:
        for rid,bundle,report in db.execute("SELECT run_id,result_bundle_path,report_path FROM analysis_runs").fetchall():
            mapped=[str((target/Path(p).resolve().relative_to(original.ws.root)).resolve()) for p in (bundle,report)]
            db.execute("UPDATE analysis_runs SET result_bundle_path=?,report_path=? WHERE run_id=?",(*mapped,rid))

@pytest.fixture
def native(tmp_path):
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path)))
    sid=s.create_task(payload=b"customer,arm,visited\n1,0,0\n2,0,1\n3,1,1\n4,1,0\n",name="public-synthetic.csv")
    s.contracts.save(sid,dict(purpose="causal",analysis_unit="customer",entity="customer",
        treatment="arm",control_value="0",treated_value="1",outcome="visited",
        metric_label="visit rate",metric_kind="binary",metric_unit="probability",metric_window="14 days"),
        human_confirmed=True)
    return s,sid

@pytest.fixture(scope="module")
def completed(tmp_path_factory,archive):
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path_factory.mktemp("real-diagnostics"))))
    co=s.automation_v2()
    t=co.create_hillstrom(archive,request_id="real-native-chain",source_confirmed=True)
    co.approve(t["id"],expected_plan_sha=t["plan_sha"],human_confirmed=True)
    assert co.run(t["id"])["status"]=="completed"
    return s,t

def by_rule(a,r):return next(f for f in a.findings if f.rule.id==r)

def counts(s):
    with s.ws.connection() as c:
        return {t:c.execute("SELECT count(*) FROM "+t).fetchone()[0]
                for t in ("analysis_runs","exploration_runs","assistant_plans","workflow_approvals","automation_v2_approvals")
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone()}

def evidence_before(s,t):
    with s.ws.connection() as c:
        return [tuple(r) for r in c.execute("SELECT * FROM automation_v2_steps WHERE task_id=? ORDER BY ordinal",(t["id"],))],counts(s)

def test_preflight_unknown_is_not_violation_or_randomization(native):
    s,sid=native;before=counts(s)
    a=DiagnosticService(s).preflight(sid)
    f=by_rule(a,"PD-02")
    assert f.status=="unknown" and f.severity.level=="major" and f.result.missing_items
    assert f.impact.claim_effect=="conditional_causal_only"
    assert a.context.plan_ref is None and not a.context.run_refs
    assert a.observations["data"]["group_field_present"] is True
    assert a.observations["data"]["nonmissing_group_count"]==2
    assert by_rule(a,"PD-07").status=="not_checked"
    assert counts(s)==before and a.model_requests==0

def test_preflight_no_contract_is_specific_unknown(native):
    s,_=native
    sid=s.create_task(payload=b"x\n1\n2\n",name="standalone.csv")
    a=DiagnosticService(s).preflight(sid)
    assert a.context.contract_ref is None
    assert by_rule(a,"PD-02").status=="unknown"
    assert "DataContract" in by_rule(a,"PD-02").result.missing_items

def test_exploratory_design_not_applicable(native):
    s,sid=native;row=s.contracts.latest(sid)
    s.contracts.save(sid,{**row["body"],"purpose":"exploratory"},expected_sha=row["sha"],human_confirmed=True)
    a=DiagnosticService(s).preflight(sid)
    f=by_rule(a,"PD-02")
    assert f.status=="not_applicable" and not f.check_performed

def test_native_declaration_without_verifiable_source_is_unknown(native):
    s,sid=native;row=s.contracts.latest(sid)
    row["body"]["method_facts"]={"ab_test":{"assignment":"randomized"}}
    s.contracts.save(sid,row["body"],expected_sha=row["sha"],human_confirmed=True)
    assert by_rule(DiagnosticService(s).preflight(sid),"PD-02").status=="unknown"

def test_real_two_runs_and_readonly_idempotence(completed):
    s,t=completed;before=evidence_before(s,t)
    engine=DiagnosticService(s);a=engine.assess(t["id"],session_id=t["session_id"])
    assert len(a.context.run_refs)==2 and all(f.status=="verified" for f in a.findings)
    assert by_rule(a,"PD-02").source.origin=="human_declaration"
    assert a.limitations and "PD-11" in a.coverage.not_implemented
    assert engine.assess(t["id"],session_id=t["session_id"])==a
    assert engine.get(a.assessment_id,session_id=t["session_id"])==a
    assert evidence_before(s,t)==before
    assert engine.evidence(a.assessment_id,by_rule(a,"PD-07").finding_id,session_id=t["session_id"])["inputs"]
    assert a.model_requests==0 and not a.execution_authorized

def test_snapshot_is_immutable_and_isolated(native):
    s,sid=native;d=DiagnosticService(s);a=d.preflight(sid)
    with pytest.raises(ValidationError):a.assessment_id="overwrite"
    with pytest.raises(DesignError):d.get(a.assessment_id,session_id="f"*32)
    with pytest.raises(DesignError):d.evidence(a.assessment_id,"not-a-finding",session_id=sid)
    a.observations["data"]["nonmissing_group_count"]=99
    assert d.get(a.assessment_id,session_id=sid).observations["data"]["nonmissing_group_count"]==2

def test_changed_contract_new_snapshot_preserves_old(native):
    s,sid=native;d=DiagnosticService(s);old=d.preflight(sid);row=s.contracts.latest(sid)
    s.contracts.save(sid,{**row["body"],"metric_window":"7 days"},expected_sha=row["sha"],human_confirmed=True)
    new=d.preflight(sid)
    assert old.assessment_id!=new.assessment_id and old.context.contract_ref!=new.context.contract_ref
    assert d.get(old.assessment_id,session_id=sid)==old

@pytest.mark.parametrize("damage",["missing_output","hash","run_ref","metric","window","gate","report_run","report_unit","report_metric","report_window","sample","desc_file","effect_file","missing_file"])
def test_persisted_conflicts_are_not_accepted(completed,tmp_path,damage):
    import shutil
    original,t=completed
    clone_native(original,tmp_path/"copy")
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/"copy")));co=s.automation_v2()
    assert all(f.status=="verified" for f in DiagnosticService(s).assess(t["id"],session_id=t["session_id"]).findings)
    if damage in ("desc_file","effect_file","missing_file"):
        rid=co.evidence(t["id"],"S02" if damage!="effect_file" else "S04")["body"]["run_id"]
        if damage!="effect_file":
            with s.ws.connection() as c:
                rel=c.execute("SELECT path FROM exploration_runs WHERE run_id=?",(rid,)).fetchone()[0]
            artifact=s.ws.root/rel
        else:
            artifact=Path(s.ws.repo.get_analysis_run(rid).result_bundle_path)
        if damage=="missing_file":artifact.unlink()
        else:artifact.write_text("controlled corrupt result",encoding="utf8")
        before=counts(s);a=DiagnosticService(s).assess(t["id"],session_id=t["session_id"])
        assert by_rule(a,"PD-01").status in ("issue","unknown")
        assert a.conclusion_policy=="hide_integrated_estimate" and counts(s)==before
        return
    step="S03" if damage=="gate" else "S05" if damage.startswith("report") else "S02"
    with s.ws.connection() as c:
        raw=c.execute("SELECT output,output_sha FROM automation_v2_steps WHERE task_id=? AND step_id=?",(t["id"],step)).fetchone()
        e=json.loads(raw[0])
        if damage=="missing_output":out=None;sha=raw[1]
        elif damage=="hash":out=raw[0];sha="0"*64
        else:
            if damage=="run_ref":e["body"]["run_id"]="f"*32
            elif damage=="metric":e["scope"]["outcome"]="other_metric"
            elif damage=="window":e["scope"]["window"]="another window"
            elif damage=="gate":e["body"]["sample_size"]+=1
            elif damage=="report_run":e["body"]["source_runs"]=["f"*32]*2
            elif damage=="report_metric":e["body"]["scope"]["outcome"]="different_metric"
            elif damage=="report_window":e["body"]["scope"]["window"]="other_window"
            elif damage=="sample":e["body"]["grouped"][0]["rows"]+=1
            else:e["body"]["effect"]["pp"]=e["body"]["effect"]["raw"]
            out=json.dumps(e);sha=digest(e)
        c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id=?",(out,sha,t["id"],step))
        if damage=="gate":
            # Preserve hash-link consistency so PD-07, rather than PD-01, must
            # reject a saved gate whose semantic sample count is wrong.
            changed={"S03":sha}
            for child in ("S04","S05"):
                body=json.loads(c.execute("SELECT output FROM automation_v2_steps WHERE task_id=? AND step_id=?",(t["id"],child)).fetchone()[0])
                body["upstreams"].update({k:v for k,v in changed.items() if k in body["upstreams"]})
                changed[child]=digest(body)
                c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id=?",(json.dumps(body),digest(body),t["id"],child))
    before=evidence_before(s,t)
    a=DiagnosticService(s).assess(t["id"],session_id=t["session_id"])
    expected_rule={"gate":"PD-07","report_run":"PD-14","report_unit":"PD-09","report_metric":"PD-14","report_window":"PD-14"}.get(damage,"PD-01")
    assert by_rule(a,expected_rule).status in ("issue","unknown")
    assert a.conclusion_policy=="hide_integrated_estimate"
    assert evidence_before(s,t)==before
    assert DiagnosticService(s).assess(t["id"],session_id=t["session_id"]).assessment_id==a.assessment_id

def test_wrong_selected_task_and_requested_window(completed):
    s,t=completed;d=DiagnosticService(s)
    with pytest.raises(DesignError):d.assess(t["id"],session_id="f"*32)
    a=d.assess(t["id"],session_id=t["session_id"],requested_window="7 days")
    assert by_rule(a,"PD-06").status=="issue" and a.conclusion_policy=="hide_integrated_estimate"

def test_cross_task_same_values_are_not_interchangeable(completed,tmp_path,archive):
    import shutil
    original,t=completed;clone_native(original,tmp_path/"copy")
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/"copy")));co=s.automation_v2()
    other=co.create_hillstrom(archive,request_id="other-task",source_confirmed=True)
    co.approve(other["id"],expected_plan_sha=other["plan_sha"],human_confirmed=True);co.run(other["id"])
    wrong=co.evidence(other["id"],"S02")
    with s.ws.connection() as c:c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S02'",(json.dumps(wrong),digest(wrong),t["id"]))
    a=DiagnosticService(s).assess(t["id"],session_id=t["session_id"])
    assert by_rule(a,"PD-01").status=="issue"
    assert other["id"] not in a.model_dump_json() and other["session_id"] not in a.model_dump_json()

def test_five_status_contract(completed):
    s,t=completed;a=DiagnosticService(s).assess(t["id"],session_id=t["session_id"])
    original=by_rule(a,"PD-01").model_dump(mode="json")
    for state in ("verified","issue","unknown","not_applicable","not_checked"):
        b=json.loads(json.dumps(original));b["status"]=state
        b["check_performed"]=state in ("verified","issue","unknown")
        b["applicability"]="not_applicable" if state=="not_applicable" else "applicable"
        b["result"]["missing_items"]=["source"] if state=="unknown" else []
        assert DiagnosticFinding.model_validate(b).status==state
    for state in ("passed","failed","not_tested"):
        with pytest.raises(ValidationError):DiagnosticFinding.model_validate({**original,"status":state})
    with pytest.raises(ValidationError):DiagnosticFinding.model_validate({**original,"status":"not_checked","check_performed":True})

def test_rule_and_schema_upgrade_make_new_snapshot(native,monkeypatch):
    from causalops.application.diagnostics import service as module
    s,sid=native;d=DiagnosticService(s);old=d.preflight(sid)
    monkeypatch.setattr(module,"RULE_PACK_VERSION","stage1-test-upgrade")
    new=d.preflight(sid)
    assert old.assessment_id!=new.assessment_id
    assert d.get(old.assessment_id,session_id=sid)==old

def test_concurrent_preflight_creates_one_snapshot(native):
    s,sid=native;d=DiagnosticService(s)
    with ThreadPoolExecutor(max_workers=2) as pool:
        out=list(pool.map(lambda _:d.preflight(sid),range(2)))
    assert out[0]==out[1]
    with s.ws.connection() as c:
        assert c.execute("SELECT count(*) FROM diagnostic_assessments").fetchone()[0]==1

def test_immutable_storage(native):
    import sqlite3
    s,sid=native;a=DiagnosticService(s).preflight(sid)
    with pytest.raises(sqlite3.IntegrityError):
        with s.ws.connection() as c:c.execute("UPDATE diagnostic_assessments SET body='{}' WHERE id=?",(a.assessment_id,))
    assert DiagnosticService(s).get(a.assessment_id,session_id=sid)==a

def test_no_model_or_statistical_calls_during_diagnostics(completed,monkeypatch):
    s,t=completed
    def forbidden(*args,**kwargs):raise AssertionError("diagnostics must not execute or approve")
    monkeypatch.setattr(s.a.tools,"execute",forbidden)
    monkeypatch.setattr(s.a.tools,"prepare",forbidden)
    monkeypatch.setattr(s.a,"execute",forbidden)
    a=DiagnosticService(s).assess(t["id"],session_id=t["session_id"])
    assert a.model_requests==0 and all(f.status=="verified" for f in a.findings)

def test_historical_read_does_not_reauthorize(completed,monkeypatch):
    from causalops.application.diagnostics import service as module
    s,t=completed
    monkeypatch.setattr(module,"execution_source_sha",lambda:"e"*64)
    a=DiagnosticService(s).assess(t["id"],session_id=t["session_id"])
    assert all(f.status=="verified" for f in a.findings)
    assert a.context.provenance.reading_mode=="historical_read_only"
    assert a.context.provenance.recorded_execution_source_sha!=a.context.provenance.diagnostic_source_sha
    assert not a.execution_authorized

def test_pending_and_partial_states_do_not_claim_complete(tmp_path,archive):
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path)));co=s.automation_v2()
    t=co.create_hillstrom(archive,request_id="pending",source_confirmed=True)
    a=DiagnosticService(s).assess(t["id"],session_id=t["session_id"])
    assert by_rule(a,"PD-14").status=="not_checked" and not a.context.run_refs
    with pytest.raises(DesignError):co.advance(t["id"],expected_step="S04")
    assert co.task(t["id"])["status"]=="candidate" and counts(s)["analysis_runs"]==0

def test_observational_declaration_is_issue_not_unknown(native):
    s,sid=native;row=s.contracts.latest(sid);body=row["body"]
    body["method_facts"]={"ab_test":{"assignment":"observational"}}
    s.contracts.save(sid,body,expected_sha=row["sha"],human_confirmed=True)
    f=by_rule(DiagnosticService(s).preflight(sid),"PD-02")
    assert f.status=="issue" and f.severity.level=="major"

def test_source_statement_conflict_is_not_verified(completed,tmp_path):
    import shutil
    original,t=completed;clone_native(original,tmp_path/"copy")
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/"copy")))
    with s.ws.connection() as c:
        row=c.execute("SELECT output FROM automation_v2_steps WHERE task_id=? AND step_id='S01'",(t["id"],)).fetchone()
        ev=json.loads(row[0]);ev["body"]["assignment"]="observational"
        c.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S01'",(json.dumps(ev),digest(ev),t["id"]))
    a=DiagnosticService(s).assess(t["id"],session_id=t["session_id"])
    assert by_rule(a,"PD-01").status=="issue" and a.conclusion_policy=="hide_integrated_estimate"

def test_old_contract_read_is_not_new_execution_permission(completed,tmp_path):
    import shutil
    original,t=completed;clone_native(original,tmp_path/"copy")
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/"copy")));d=DiagnosticService(s)
    old=d.assess(t["id"],session_id=t["session_id"]);row=s.contracts.latest(t["session_id"])
    s.contracts.save(t["session_id"],{**row["body"],"metric_window":"another registered window"},
        expected_sha=row["sha"],human_confirmed=True)
    new=d.assess(t["id"],session_id=t["session_id"])
    assert old.assessment_id!=new.assessment_id
    assert new.context.contract_ref==old.context.contract_ref
    assert all(f.status=="verified" for f in new.findings)
    with pytest.raises(DesignError):s.automation_v2()._verify(s.automation_v2().task(t["id"]))
    assert d.get(old.assessment_id,session_id=t["session_id"])==old

def test_changed_invalid_artifact_makes_new_snapshot(completed,tmp_path):
    import shutil
    original,t=completed;clone_native(original,tmp_path/"copy")
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/"copy")));co=s.automation_v2()
    rid=co.evidence(t["id"],"S02")["body"]["run_id"]
    with s.ws.connection() as c:rel=c.execute("SELECT path FROM exploration_runs WHERE run_id=?",(rid,)).fetchone()[0]
    p=s.ws.root/rel;d=DiagnosticService(s)
    p.write_text("corrupt revision one",encoding="utf8");a=d.assess(t["id"],session_id=t["session_id"])
    p.write_text("corrupt revision two",encoding="utf8");b=d.assess(t["id"],session_id=t["session_id"])
    assert a.assessment_id!=b.assessment_id
    assert by_rule(a,"PD-01").status==by_rule(b,"PD-01").status=="issue"
