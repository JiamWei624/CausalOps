"""Configurable two-arm binary research, real registered tools and safety boundaries."""
import copy
import json
import pandas as pd
import pytest
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace, digest
from causalops.general.service import GeneralWorkspace, DesignError


def config(**changes):
    d=dict(objective="比较两个随机分配方案在本期完成行为的比例并报告差异", analysis_unit="独立参与者", entity="subject", record_grain="每名参与者一行", independent_records_confirmed=True,
           treatment="arm",control_value="standard",treated_value="variant",control_label="标准方案",treated_label="新方案",
           outcome="completed",negative_value="no",positive_value="yes",metric="完成比例",unit="概率",window="本次实验的完整观察期",
           assignment="randomized",source_url="https://example.org/public-design",design_evidence="已核对的公开设计说明明确将独立参与者随机分配到两个方案。",source_confirmed=True)
    return {**d,**changes}


def data():
    return pd.DataFrame(dict(subject=range(24),arm=["standard"]*12+["variant"]*12,completed=["yes","no"]*6+["yes","yes","no"]*4))

@pytest.fixture
def co(tmp_path):
    return ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path))).automation_v2()


def create(co, **changes):
    return co.create_configurable(data().to_csv(index=False).encode(), name="uploaded.csv", configuration=config(**changes), request_id="request", human_confirmed=True)


def approve(co,t):
    return co.approve(t["id"],expected_plan_sha=t["plan_sha"],human_confirmed=True)


def test_real_user_fields_two_runs_and_report(co):
    t=create(co);approve(co,t)
    assert co.run(t["id"])["status"]=="completed"
    d=co.evidence(t["id"],"S02");g=co.evidence(t["id"],"S03");r=co.report(t["id"])
    assert g["body"]["descriptive_run_id"]==d["body"]["run_id"]
    assert len(set(r["source_runs"]))==2
    assert r["effect"]["control_rate"]==pytest.approx(.5)
    assert r["effect"]["treated_rate"]==pytest.approx(2/3)
    assert r["effect"]["pp"]==pytest.approx(100/6)
    assert all(s in r["text"] for s in ["标准方案","新方案","百分点","独立参与者","本次实验","未验证"])
    assert "Hillstrom" not in r["text"] and "两周" not in r["text"]
    assert co.evidence(t["id"],"S04")["body"]["run_id"]==r["source_runs"][1]
    before=digest(co.steps(t["id"]));co.run(t["id"])
    assert digest(co.steps(t["id"]))==before


def test_unknown_design_keeps_actual_description_and_blocks_effect(co):
    t=create(co,assignment="unknown",design_evidence="",source_confirmed=False);approve(co,t)
    assert co.run(t["id"])["status"]=="blocked"
    assert co.evidence(t["id"],"S01")["body"]["assignment"]=="unknown"
    assert co.evidence(t["id"],"S02")["body"]["run_id"]
    assert next(x for x in co.steps(t["id"]) if x["step_id"]=="S04")["status"]=="pending"
    with co.ws.connection() as c:assert c.execute("SELECT count(*) FROM analysis_runs").fetchone()[0]==0
    from causalops.application.automation_results import snapshot,report_html
    text=report_html(snapshot(co,t["id"]))
    assert "50.00%" in text and "66.67%" in text and "百分点" in text and "未执行" in text
    assert "随机分配依据未知" in text


@pytest.mark.parametrize("bad",[dict(treatment="absent"),dict(outcome="arm"),dict(control_value="missing"),dict(positive_value="no"),dict(window=""),dict(entity=None,independent_records_confirmed=False),dict(source_confirmed=False),dict(design_evidence="")])
def test_bad_contract_cannot_create_plan(co,bad):
    with pytest.raises(ValueError):create(co,**bad)
    with co.ws.connection() as c:assert c.execute("SELECT count(*) FROM automation_v2_tasks").fetchone()[0]==0


@pytest.mark.parametrize("fault",["missing","duplicate","third_group","nonbinary"])
def test_invalid_data_rejected(co,fault):
    f=data()
    if fault=="missing":f.loc[0,"completed"]=None
    elif fault=="duplicate":f.loc[1,"subject"]=0
    elif fault=="third_group":f.loc[0,"arm"]="other"
    else:f.loc[0,"completed"]="maybe"
    with pytest.raises(ValueError):co.create_configurable(f.to_csv(index=False).encode(),name="bad.csv",configuration=config(),request_id="bad",human_confirmed=True)


def test_no_approval_no_skipping_and_receipts_separate(co):
    t=create(co)
    with pytest.raises(DesignError):co.advance(t["id"],expected_step="S04")
    r=approve(co,t);assert r["schema_version"]=="configurable-research-approval-1"
    with pytest.raises(DesignError):co.advance(t["id"],expected_step="S04")
    with pytest.raises(DesignError):co.a.execute(t["plan"]["plan_id"],permit=True)
    assert r["facts"]=={"S04":{"assignment":"randomized"}}


def test_request_id_cannot_reuse_different_configuration(co):
    t=create(co);assert create(co)["id"]==t["id"]
    with pytest.raises(DesignError):create(co,window="另一观察期")


@pytest.mark.parametrize("change",[dict(metric="另一指标名称"),dict(control_label="另一比较对象")])
def test_successor_needs_new_approval_and_keeps_history(co,change):
    t=create(co);approve(co,t);co.run(t["id"]);old=co.report(t["id"])
    newer=co.revise_configurable(t["id"],configuration=config(**change),request_id="revision",human_confirmed=True)
    assert newer["plan"]["version"]==2 and newer["status"]=="candidate"
    with pytest.raises(DesignError):co._verify(co.task(t["id"]))
    with pytest.raises(DesignError):co.advance(newer["id"])
    assert co.evidence(t["id"],"S05")["body"]==old
    approve(co,newer);assert co.run(newer["id"])["status"]=="completed"
    assert not set(old["source_runs"]) & set(co.report(newer["id"])["source_runs"])


def test_changed_contract_invalidates_approval(co):
    t=create(co);approve(co,t);row=co.s.contracts.latest(t["session_id"])
    co.s.contracts.save(t["session_id"],{**row["body"],"metric_window":"不同窗口"},expected_sha=row["sha"],human_confirmed=True)
    assert co.advance(t["id"])["status"]=="blocked"
    assert all(x["status"]!="succeeded" for x in co.steps(t["id"]))


def test_technical_record_key_is_explicit_not_person_identity(co):
    t=create(co,entity=None);approve(co,t);co.run(t["id"])
    assert "用户确认" in co.report(t["id"])["text"]


def test_parquet_and_equal_values_keep_field_binding(co):
    from io import BytesIO
    f=data();f["other"]=f.completed;buf=BytesIO();f.to_parquet(buf,index=False)
    t=co.create_configurable(buf.getvalue(),name="input.parquet",configuration=config(outcome="other"),request_id="pq",human_confirmed=True)
    approve(co,t);co.run(t["id"])
    assert co.report(t["id"])["scope"]["outcome"]=="other"


def test_preflight_and_decision_never_grant_statistical_authority(co):
    from causalops.application.diagnostics.service import DiagnosticService
    t=create(co,assignment="unknown",design_evidence="",source_confirmed=False)
    a=DiagnosticService(co.s).preflight(t["session_id"])
    assert a
    with co.ws.connection() as c:
        assert c.execute("SELECT count(*) FROM automation_v2_approvals").fetchone()[0]==0
        assert c.execute("SELECT count(*) FROM analysis_runs").fetchone()[0]==0


def test_new_window_requires_real_new_table_and_approval(co):
    t=create(co);approve(co,t)
    with pytest.raises(DesignError):co.revise_configurable(t["id"],configuration=config(window="新观察期"),request_id="w1",human_confirmed=True)
    with pytest.raises(DesignError):co.revise_configurable(t["id"],configuration=config(window="新观察期"),request_id="w2",human_confirmed=True,payload=data().to_csv(index=False).encode(),name="same.csv")
    newdata=data().iloc[1:].copy()
    u=co.revise_configurable(t["id"],configuration=config(window="新观察期"),request_id="w3",human_confirmed=True,payload=newdata.to_csv(index=False).encode(),name="new.csv")
    with pytest.raises(DesignError):co._verify(co.task(t["id"]))
    assert u["status"]=="candidate"
    approve(co,u);assert co.run(u["id"])["status"]=="completed"
    assert co.report(u["id"])["scope"]["window"]=="新观察期"

def test_new_task_decision_is_readonly_and_unknown_is_not_passed(co):
    from causalops.application.diagnostics.reports import DiagnosticReportService
    from causalops.application.diagnostics.workbench import DiagnosticWorkbench
    from causalops.application.diagnostics.decisions import ResearchDecisionService
    t=create(co,assignment="unknown",design_evidence="",source_confirmed=False)
    r=DiagnosticReportService(co.s).preflight(t["session_id"])
    suggestion=next(x for x in r.suggestions if x.rule_id=="PD-02")
    memory=ResearchDecisionService(DiagnosticWorkbench(co.s))
    d=memory.save("preflight",t["session_id"],r.report_id,"deferred","尚缺设计来源，不把描述差异解释为因果效应",suggestion_id=suggestion.suggestion_id,human_confirmed=True)
    assert d.finding_status=="unknown" and not d.execution_authorized
    assert memory.save("preflight",t["session_id"],r.report_id,"deferred",d.reason,suggestion_id=suggestion.suggestion_id,human_confirmed=True)==d
    assert memory.history("preflight",t["session_id"])[0].decision==d
    with pytest.raises(DesignError):co.a.execute(d.decision_id,permit=True)
    with co.ws.connection() as db:
        assert db.execute("SELECT count(*) FROM analysis_runs").fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM automation_v2_approvals").fetchone()[0]==0


@pytest.mark.parametrize("fault",["hash","group","run_failure"])
def test_upstream_damage_never_creates_effect_run(co,monkeypatch,fault):
    t=create(co);approve(co,t);co.advance(t["id"])
    if fault=="run_failure":
        def broken(*a,**k):raise OSError("controlled tool failure")
        monkeypatch.setattr(co.a.tools,"execute",broken)
        assert co.advance(t["id"])["status"]=="interrupted"
    else:
        co.advance(t["id"])
        with co.ws.connection() as db:
            if fault=="hash":db.execute("UPDATE automation_v2_steps SET output_sha='invalid' WHERE task_id=? AND step_id='S02'",(t["id"],))
            else:
                e=co.evidence(t["id"],"S02");e["body"]["grouped"][0]["group_value"]="other"
                db.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S02'",(json.dumps(e),digest(e),t["id"]))
        assert co.advance(t["id"])["status"]=="blocked"
    with co.ws.connection() as db:assert db.execute("SELECT count(*) FROM analysis_runs").fetchone()[0]==0


def test_configurable_pause_restore_cancel_and_local_events(co,monkeypatch):
    monkeypatch.setenv("CAUSALOPS_EVENT_ORIGIN","fixed_browser_test")
    t=create(co);approve(co,t);co.advance(t["id"]);co.advance(t["id"])
    rid=co.evidence(t["id"],"S02")["body"]["run_id"]
    co.pause(t["id"],human_confirmed=True);co.resume(t["id"],human_confirmed=True)
    co.run(t["id"]);assert co.evidence(t["id"],"S02")["body"]["run_id"]==rid
    with co.ws.connection() as db:
        events=db.execute("SELECT action,origin FROM configurable_user_events WHERE task_id=?",(t["id"],)).fetchall()
    assert all(r[1]=="fixed_browser_test" for r in events)
    assert {r[0] for r in events} >= {"data_imported","conditions_confirmed","plan_created","review_submitted","execution_started","research_completed"}
    newer=co.revise_configurable(t["id"],configuration=config(outcome="completed",metric="另一个显示口径"),request_id="cancel",human_confirmed=True)
    approve(co,newer);co.cancel(newer["id"],human_confirmed=True)
    with pytest.raises(DesignError):co.resume(newer["id"],human_confirmed=True)

def test_partial_report_does_not_call_completed_ab_unexecuted(co):
    from causalops.application.automation_results import snapshot,report_html
    t=create(co);approve(co,t)
    for step in ("S01","S02","S03","S04"):co.advance(t["id"],expected_step=step)
    text=report_html(snapshot(co,t["id"]))
    assert "A/B未执行" not in text
    assert co.evidence(t["id"],"S04")["body"]["run_id"] in text


@pytest.mark.parametrize("mutation",["step","scope","approval"])
def test_configurable_binding_rejects_plan_or_legacy_receipt(co,mutation):
    t=create(co);approve(co,t)
    with co.ws.connection() as db:
        if mutation=="approval":
            raw=db.execute("SELECT body FROM automation_v2_approvals WHERE task_id=?",(t["id"],)).fetchone()[0]
            r=json.loads(raw);r["schema_version"]="automation-v2-approval-1"
            db.execute("UPDATE automation_v2_approvals SET body=?,sha=? WHERE task_id=?",(json.dumps(r),digest(r),t["id"]))
        else:
            p=copy.deepcopy(t["plan"])
            if mutation=="step":p["steps"][3]["config"]["outcome"]="subject"
            else:p["scope"]["window"]="未经审核的新窗口"
            db.execute("UPDATE automation_v2_tasks SET plan_json=?,plan_sha=? WHERE id=?",(json.dumps(p),digest(p),t["id"]))
    assert co.advance(t["id"])["status"]=="blocked"
    assert not any(x["status"]=="succeeded" for x in co.steps(t["id"]))


def test_changing_comparison_direction_is_new_plan_not_old_effect(co):
    t=create(co);approve(co,t);co.run(t["id"]);old=co.report(t["id"])
    change=config(control_value="variant",treated_value="standard",control_label="新方案",treated_label="标准方案")
    u=co.revise_configurable(t["id"],configuration=change,request_id="groups",human_confirmed=True)
    approve(co,u);co.run(u["id"])
    assert co.report(u["id"])["effect"]["raw"]==pytest.approx(-old["effect"]["raw"])
    assert co.report(t["id"])==old

def test_superseded_partial_history_remains_readable(co):
    from causalops.application.automation_results import snapshot,report_html
    t=create(co,assignment="unknown",design_evidence="",source_confirmed=False);approve(co,t);co.run(t["id"])
    before=co.evidence(t["id"],"S02")
    co.revise_configurable(t["id"],configuration=config(assignment="unknown",design_evidence="",source_confirmed=False,metric="重新命名的指标"),request_id="new-scope",human_confirmed=True)
    assert co.evidence(t["id"],"S02")==before
    text=report_html(snapshot(co,t["id"]))
    assert "50.00%" in text and "66.67%" in text and before["body"]["run_id"] in text
