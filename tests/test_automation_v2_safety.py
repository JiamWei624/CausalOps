"""Additional boundary checks use actual public-data tools; no product fixtures changed."""
import json
from pathlib import Path

import pytest
from test_automation_v2 import archive, system, approved, through_s02, ab_runs
from causalops.assistant.service import digest
from causalops.general.service import DesignError


@pytest.mark.parametrize("change",["contract","gate","desc_file","revoked"])
def test_midchain_change_stops_s04(system,change):
    co,t=through_s02(system)
    co.advance(t["id"],expected_step="S03")
    if change=="contract":
        row=co.s.contracts.latest(t["session_id"])
        row["body"]["metric_window"]="另一个窗口"
        co.s.contracts.save(t["session_id"],row["body"],expected_sha=row["sha"],human_confirmed=True)
    elif change=="desc_file":
        rid=co.evidence(t["id"],"S02")["body"]["run_id"]
        with co.ws.connection() as db:
            path=db.execute("SELECT path FROM exploration_runs WHERE run_id=?",(rid,)).fetchone()[0]
        (co.ws.root/path).write_text("corrupt",encoding="utf8")
    else:
        with co.ws.connection() as db:
            if change=="revoked":
                db.execute("UPDATE automation_v2_approvals SET revoked=1 WHERE task_id=?",(t["id"],))
            else:
                e=co.evidence(t["id"],"S03");e["body"]["decision"]="blocked"
                db.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S03'",
                           (json.dumps(e),digest(e),t["id"]))
    assert co.run(t["id"])["status"]=="blocked"
    assert ab_runs(co)==0


def test_cross_task_run_cannot_replace_upstream(system,archive):
    co,t=through_s02(system)
    other=co.create_hillstrom(archive,request_id="second",source_confirmed=True)
    co.approve(other["id"],expected_plan_sha=other["plan_sha"],human_confirmed=True)
    co.advance(other["id"]);co.advance(other["id"])
    wrong=co.evidence(other["id"],"S02")
    with co.ws.connection() as db:
        db.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S02'",
                   (json.dumps(wrong),digest(wrong),t["id"]))
    assert co.run(t["id"])["status"]=="blocked"
    assert ab_runs(co)==0


def test_legacy_receipt_cannot_authorize_v2(system):
    co,t=system
    with co.ws.connection() as db:
        body={"schema_version":"legacy","plan_sha":t["plan_sha"]}
        db.execute("INSERT INTO automation_v2_approvals VALUES(?,?,?,?,0)",
                   (t["id"],"fake",json.dumps(body),digest(body)))
        db.execute("UPDATE automation_v2_tasks SET status='approved' WHERE id=?",(t["id"],))
    assert co.run(t["id"])["status"]=="blocked"
    assert ab_runs(co)==0
    with pytest.raises(DesignError):co.a.accept(t["plan"]["plan_id"],t["plan_sha"])


def test_pending_task_does_not_compute(system):
    co,t=system
    assert co.run(t["id"])["status"]=="candidate"
    assert not any(s["status"]=="succeeded" for s in co.steps(t["id"]))
    assert ab_runs(co)==0


def test_duplicate_dispatch_os_lock(system):
    from causalops.application.locking import flow_lock
    co,t=approved(system)
    with flow_lock(co.ws.root,t["id"]):
        with pytest.raises(DesignError,match="不会并行重复"):
            co.advance(t["id"])
    assert co.steps(t["id"])[0]["status"]=="pending"


def test_original_domain_gate_still_runs(system,monkeypatch):
    co,t=through_s02(system)
    co.advance(t["id"])
    calls=[]
    def reject(**kwargs):
        calls.append(kwargs)
        raise DesignError("controlled domain authorization rejection")
    monkeypatch.setattr(co.ws.repo,"assert_execution_authorized",reject)
    co.advance(t["id"],expected_step="S04")
    assert calls, "must reach original domain gate, not a parallel estimator"
    assert co.task(t["id"])["status"]=="blocked"
    assert ab_runs(co)==0


@pytest.mark.parametrize("fault",["nonbinary","duplicate","missing","one_group"])
def test_audit_explicit_rules_not_only_fingerprint(system,monkeypatch,fault):
    co,t=system
    plan,frame=co._binding(t);frame=frame.copy()
    if fault=="nonbinary":frame.loc[0,"visit"]=2
    elif fault=="duplicate":frame.loc[1,"entity_id"]=frame.loc[0,"entity_id"]
    elif fault=="missing":frame.loc[0,"visit"]=float("nan")
    else:frame["assigned"]=0
    monkeypatch.setattr(co,"_binding",lambda _: (plan,frame))
    with pytest.raises(DesignError):co._audit(t)
    assert ab_runs(co)==0


def test_completed_report_independent_of_new_task(system,archive):
    co,t=approved(system);co.run(t["id"]);report=co.report(t["id"])
    other=co.create_hillstrom(archive,request_id="new-study",source_confirmed=True)
    assert other["id"]!=t["id"]
    assert co.report(t["id"])==report
    assert ab_runs(co)==1

def test_upstream_approval_binding_cannot_be_relabelled(system):
    co,t=through_s02(system)
    e=co.evidence(t["id"],"S02")
    e["body"]["approval_id"]="different-approval"
    with co.ws.connection() as db:
        db.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S02'",
                   (json.dumps(e),digest(e),t["id"]))
    assert co.run(t["id"])["status"]=="blocked"
    assert ab_runs(co)==0
