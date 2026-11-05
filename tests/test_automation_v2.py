"""V2 stage-one contracts and real registered-tool acceptance; public data only."""
import json
import math
import os
from pathlib import Path

import pytest

from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace, digest
from causalops.general.service import GeneralWorkspace, DesignError


@pytest.fixture(scope="module")
def archive():
    p = os.environ.get("CAUSALOPS_HILLSTROM_ARCHIVE")
    if not p:
        pytest.skip("Set CAUSALOPS_HILLSTROM_ARCHIVE for real public-data acceptance")
    return Path(p).read_bytes()


@pytest.fixture
def system(tmp_path, archive):
    service = ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path)))
    coordinator = service.automation_v2()
    task = coordinator.create_hillstrom(archive, request_id="test-request", source_confirmed=True)
    return coordinator, task


def approved(system):
    co, t = system
    co.approve(t["id"], expected_plan_sha=t["plan_sha"], human_confirmed=True)
    return co, t


def through_s02(system):
    co, t = approved(system)
    co.advance(t["id"], expected_step="S01")
    co.advance(t["id"], expected_step="S02")
    return co, t


def ab_runs(co):
    with co.ws.connection() as c:
        return c.execute("SELECT count(*) FROM analysis_runs").fetchone()[0]


def test_create_idempotent_and_fixed_contract(system, archive):
    from causalops.application.automation_contracts import PlanV2
    co, t = system
    again = co.create_hillstrom(archive, request_id="test-request", source_confirmed=True)
    assert again["id"] == t["id"]
    plan = PlanV2.model_validate(t["plan"])
    assert [s.step_id for s in plan.steps] == ["S01","S02","S03","S04","S05"]
    assert [s.tool for s in plan.steps if s.kind == "statistical"] == ["exploration","research"]
    assert plan.steps[3].depends_on == ("S03",)
    assert co.steps(t["id"])[0]["status"] == "pending"
    assert ab_runs(co) == 0


@pytest.mark.parametrize("mutation", ["dependency", "tool", "expression", "scope"])
def test_contract_rejects_arbitrary_graph(system, mutation):
    from causalops.application.automation_contracts import PlanV2
    _, t = system
    plan = json.loads(json.dumps(t["plan"]))
    if mutation == "dependency": plan["steps"][3]["depends_on"] = []
    elif mutation == "tool": plan["steps"][3]["tool"] = "python"
    elif mutation == "expression": plan["steps"][2]["config"]["expression"] = "eval('anything')"
    else: plan["steps"][3]["config"]["outcome"] = "orders"
    with pytest.raises(ValueError):
        PlanV2.model_validate(plan)


def test_no_approval_and_no_direct_s04(system):
    co, t = system
    with pytest.raises(DesignError):
        co.advance(t["id"], expected_step="S04")
    with pytest.raises(DesignError):
        co.approve(t["id"], expected_plan_sha=t["plan_sha"], human_confirmed=False)
    with pytest.raises(DesignError):
        co.a.execute(t["plan"]["plan_id"], permit=True)
    assert ab_runs(co) == 0


def test_approved_cannot_skip_gate(system):
    co,t = approved(system)
    with pytest.raises(DesignError):
        co.advance(t["id"], expected_step="S04")
    assert ab_runs(co) == 0


def test_real_chain_and_domain_approval(system):
    from causalops.results.rate_units import rate_contrast
    co,t = approved(system)
    co.approve(t["id"], expected_plan_sha=t["plan_sha"], human_confirmed=True)
    result = co.run(t["id"])
    assert result["status"] == "completed"
    steps = co.steps(t["id"])
    assert all(s["status"] == "succeeded" for s in steps)
    desc = co.evidence(t["id"], "S02")
    gate = co.evidence(t["id"], "S03")
    effect = co.evidence(t["id"], "S04")
    assert gate["body"]["descriptive_run_id"] == desc["body"]["run_id"]
    assert desc["body"]["run_id"] != effect["body"]["run_id"]
    bundle, record = co.ws.bundle(effect["body"]["run_id"])
    rates = rate_contrast(bundle)
    c, tr = 2262/21306, 3894/21307
    assert rates["raw"] == pytest.approx(tr-c)
    assert bundle.estimate.standard_error == pytest.approx(math.sqrt(c*(1-c)/(21306-1)+tr*(1-tr)/(21307-1)))
    assert co.ws.repo.get_approval(record.revision_id)
    report = co.report(t["id"])
    assert report["source_runs"] == [desc["body"]["run_id"], effect["body"]["run_id"]]
    assert report["sample_size"] == 42613
    assert report["effect"]["pp"] == pytest.approx(100*(tr-c))
    assert all(v in report["text"] for v in ["10.62%", "18.28%", "7.66", "百分点", "两周", "未实施"])
    with co.ws.connection() as db:
        assert db.execute("SELECT count(*) FROM automation_v2_approvals").fetchone()[0] == 1


@pytest.mark.parametrize("fault", ["missing_field","missing_value","one_group","duplicate_entity","nonbinary"])
def test_audit_blocks_before_statistics(system, monkeypatch, fault):
    co,t = approved(system)
    original = co.ws.load_upload
    def modified(uid):
        f=original(uid).copy()
        if fault=="missing_field": return f.drop(columns=["visit"])
        if fault=="missing_value": f.loc[0,"visit"]=float("nan")
        if fault=="one_group": f["assigned"]=0
        if fault=="duplicate_entity": f.loc[1,"entity_id"]=f.loc[0,"entity_id"]
        if fault=="nonbinary": f.loc[0,"visit"]=2
        return f
    monkeypatch.setattr(co.ws,"load_upload",modified)
    result=co.run(t["id"])
    assert result["status"]=="blocked"
    assert ab_runs(co)==0
    assert all(s["status"]=="pending" for s in co.steps(t["id"])[1:])


def test_s02_failure_stops_downstream(system, monkeypatch):
    co,t = approved(system)
    real=co.a.tools.execute
    def fail(uid, design, cp):
        if cp["kind"]=="exploration": raise OSError("controlled tool failure")
        return real(uid,design,cp)
    monkeypatch.setattr(co.a.tools,"execute",fail)
    assert co.run(t["id"])["status"] == "interrupted"
    assert ab_runs(co)==0
    assert co.steps(t["id"])[2]["status"]=="pending"
    with pytest.raises(DesignError): co.advance(t["id"])
    assert ab_runs(co)==0


@pytest.mark.parametrize("damage", ["missing_output","wrong_hash","wrong_run","sample_mismatch","wrong_metric","wrong_window"])
def test_persisted_upstream_damage_prevents_s04(system, damage):
    co,t=through_s02(system)
    e=co.evidence(t["id"],"S02")
    with co.ws.connection() as db:
        if damage=="missing_output":
            db.execute("UPDATE automation_v2_steps SET output=NULL WHERE task_id=? AND step_id='S02'",(t["id"],))
        elif damage=="wrong_hash":
            db.execute("UPDATE automation_v2_steps SET output_sha='bad' WHERE task_id=? AND step_id='S02'",(t["id"],))
        else:
            if damage=="wrong_run": e["body"]["run_id"]="a"*32
            elif damage=="sample_mismatch": e["body"]["grouped"][0]["rows"]+=1
            elif damage=="wrong_metric": e["scope"]["outcome"]="orders"
            else: e["scope"]["window"]="四周"
            db.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S02'",(json.dumps(e),digest(e),t["id"]))
    assert co.run(t["id"])["status"]=="blocked"
    assert ab_runs(co)==0


@pytest.mark.parametrize("change", ["plan","contract","data"])
def test_changed_binding_invalidates_approval(system, change):
    co,t=approved(system)
    with co.ws.connection() as db:
        if change=="plan":
            p=t["plan"];p["objective"]="更换研究目标"
            db.execute("UPDATE automation_v2_tasks SET plan_json=?,plan_sha=? WHERE id=?",(json.dumps(p),digest(p),t["id"]))
        elif change=="contract":
            row=co.s.contracts.latest(t["session_id"]);row["body"]["metric_window"]="四周"
            # simulate valid new contract version via the existing human fact entry
        else: db.execute("UPDATE general_uploads SET frame_sha='changed' WHERE upload_id=?",(t["plan"]["data"]["upload_id"],))
    if change=="contract":
        co.s.contracts.save(t["session_id"],row["body"],expected_sha=row["sha"],human_confirmed=True)
    assert co.run(t["id"])["status"]=="blocked"
    assert ab_runs(co)==0


def test_repeat_submission_completed_step_and_history(system):
    co,t=approved(system)
    co.advance(t["id"],expected_step="S01")
    first=co.evidence(t["id"],"S01")
    co.advance(t["id"],expected_step="S01")
    assert co.evidence(t["id"],"S01")==first
    co.run(t["id"])
    runs=co.report(t["id"])["source_runs"]
    before=[co.a.tools.envelope(t["plan"]["data"]["upload_id"],co.evidence(t["id"],sid)["body"]["tool_result"]["ref"]).result_fingerprint for sid in ("S02","S04")]
    co.run(t["id"]);co.advance(t["id"],expected_step="S04")
    assert co.report(t["id"])["source_runs"]==runs and ab_runs(co)==1
    after=[co.a.tools.envelope(t["plan"]["data"]["upload_id"],co.evidence(t["id"],sid)["body"]["tool_result"]["ref"]).result_fingerprint for sid in ("S02","S04")]
    assert before==after


def test_uncertain_success_not_replayed(system, monkeypatch):
    co,t=approved(system)
    co.advance(t["id"])
    real=co.a.tools.execute
    calls=[]
    def lost_reply(*args):
        out=real(*args);calls.append(out.run_id)
        raise OSError("reply lost after persisted run")
    monkeypatch.setattr(co.a.tools,"execute",lost_reply)
    assert co.run(t["id"])["status"]=="interrupted"
    with pytest.raises(DesignError): co.advance(t["id"])
    assert len(calls)==1
    assert co.a.ex.load(calls[0])
    assert ab_runs(co)==0


def test_cancel_terminal_and_pause_boundary(system):
    co,t=approved(system)
    co.advance(t["id"])
    co.pause(t["id"],human_confirmed=True)
    with pytest.raises(DesignError): co.advance(t["id"])
    co.resume(t["id"],human_confirmed=True)
    co.cancel(t["id"],human_confirmed=True)
    with pytest.raises(DesignError): co.resume(t["id"],human_confirmed=True)
    with pytest.raises(DesignError): co.advance(t["id"])
    assert co.evidence(t["id"],"S01")


def test_unverified_archive_and_model_entry_closed(tmp_path, archive):
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path)))
    co=s.automation_v2()
    with pytest.raises(ValueError):
        co.create_hillstrom(b"not public verified data",request_id="x",source_confirmed=True)
    with pytest.raises(DesignError):
        co.create_hillstrom(archive,request_id="x",source_confirmed=False)
    s.model=object()
    with pytest.raises(DesignError): s.automation_v2()
