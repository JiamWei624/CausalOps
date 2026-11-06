"""UI states and evidence-bound projection precede workbench implementation."""
import json
import pytest
from streamlit.testing.v1 import AppTest
from test_diagnostics_stage1 import native,completed,clone_native,counts,evidence_before
from test_automation_v2 import archive
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace,digest
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.application.diagnostics.reports import DiagnosticReportService
from causalops.application.diagnostics.workbench import DiagnosticWorkbench
from causalops.ui.diagnostics_app import report_html,ordered_findings

def ui(s,mode,task):
    import os
    os.environ["CAUSALOPS_HOME"]=str(s.ws.root)
    app=AppTest.from_string("from causalops.ui.diagnostics_app import render\nrender()",default_timeout=40)
    app.query_params.update(diagnostic_mode=mode,diagnostic_task=task)
    return app.run()

def test_empty_workbench_has_no_implicit_report(tmp_path,monkeypatch):
    monkeypatch.setenv("CAUSALOPS_HOME",str(tmp_path))
    app=AppTest.from_string("from causalops.ui.diagnostics_app import render\nrender()")
    app.run()
    assert not app.exception and any("没有可诊断" in i.value for i in app.info)
    assert not any(b.label in ("检查研究条件","检查研究证据") for b in app.button)

def test_preflight_only_on_click_and_refresh_is_readonly(native,monkeypatch):
    s,sid=native;before=counts(s);monkeypatch.setenv("CAUSALOPS_HOME",str(s.ws.root))
    app=ui(s,"preflight",sid)
    with s.ws.connection() as c:assert c.execute("SELECT count(*) FROM diagnostic_reports").fetchone()[0]==0
    app.button(key="diag_check_preflight_"+sid).click().run()
    assert not app.exception
    rid=app.query_params["diagnostic_report"]
    html=report_html(DiagnosticWorkbench(s).load("preflight",sid,rid))
    assert "未知" in html and "尚无正式统计运行" in html and "总体可信度" not in html
    app.run();assert not app.exception
    with s.ws.connection() as c:
        assert c.execute("SELECT count(*) FROM diagnostic_reports").fetchone()[0]==1
        assert c.execute("SELECT count(*) FROM diagnostic_request_drafts").fetchone()[0]==0
    assert counts(s)==before

def test_snapshot_binding_rejects_other_subject(native):
    s,sid=native;w=DiagnosticWorkbench(s);r=w.create("preflight",sid)
    other=s.create_task(payload=b"x\n1\n2\n",name="another.csv")
    with pytest.raises(DesignError):w.load("preflight",other,r.report_id)

def test_stale_report_no_numbers_or_draft(native):
    s,sid=native;w=DiagnosticWorkbench(s);r=w.create("preflight",sid);row=s.contracts.latest(sid)
    s.contracts.save(sid,{**row["body"],"metric_window":"7 days"},expected_sha=row["sha"],human_confirmed=True)
    v=w.load("preflight",sid,r.report_id)
    assert not v.source_current and "来源已变化" in report_html(v)
    with pytest.raises(DesignError):
        w.save("preflight",sid,r.report_id,r.suggestions[0].suggestion_id,"补充设计依据",confirmed=True)
    with s.ws.connection() as c:assert c.execute("SELECT count(*) FROM diagnostic_request_drafts").fetchone()[0]==0

def test_form_requires_check_and_deduplicates(native,monkeypatch):
    s,sid=native;monkeypatch.setenv("CAUSALOPS_HOME",str(s.ws.root));w=DiagnosticWorkbench(s)
    r=w.create("preflight",sid);a=r.suggestions[0];before=counts(s)
    app=ui(s,"preflight",sid);app.query_params["diagnostic_report"]=r.report_id;app.run()
    key="diag_save_"+r.report_id+"_"+a.suggestion_id
    assert app.button(key=key).disabled
    app.text_area(key="diag_intent_"+r.report_id+"_"+a.suggestion_id).set_value("补充设计来源及适用人群").run()
    app.checkbox(key="diag_confirm_"+r.report_id+"_"+a.suggestion_id).check().run()
    app.button(key=key).click().run();assert not app.exception
    app.button(key=key).click().run();assert not app.exception
    with s.ws.connection() as c:assert c.execute("SELECT count(*) FROM diagnostic_request_drafts").fetchone()[0]==1
    assert counts(s)==before
    draft=w.drafts("preflight",sid,r.report_id)[0]
    assert not draft.execution_authorized and draft.status=="needs_information"
    refreshed=ui(s,"preflight",sid);refreshed.query_params["diagnostic_report"]=r.report_id;refreshed.run()
    assert refreshed.text_area(key="diag_intent_"+r.report_id+"_"+a.suggestion_id).value==draft.user_intent
    refreshed.checkbox(key="diag_confirm_"+r.report_id+"_"+a.suggestion_id).check().run()
    refreshed.button(key=key).click().run()
    with s.ws.connection() as c:assert c.execute("SELECT count(*) FROM diagnostic_request_drafts").fetchone()[0]==1
    with pytest.raises(DesignError):s.a.accept(draft.draft_id,"0"*64)

def test_real_report_values_and_original_run_sources(completed):
    s,t=completed;before=evidence_before(s,t);w=DiagnosticWorkbench(s);r=w.create("post_run",t["id"])
    v=w.load("post_run",t["id"],r.report_id);html=report_html(v)
    assert all(x in html for x in ["18.28%","10.62%","7.66","6.995","8.323",t["id"],r.report_id])
    assert all(x["run_id"] in html for x in r.results.runs)
    assert "未实现的八项" in html and not r.suggestions and v.source_current
    assert evidence_before(s,t)==before

def test_stale_saved_success_does_not_fill_conflict(completed,tmp_path):
    s0,t=completed;clone_native(s0,tmp_path/"copy")
    s=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path/"copy")));w=DiagnosticWorkbench(s)
    good=w.create("post_run",t["id"])
    with s.ws.connection() as c:
        c.execute("UPDATE automation_v2_steps SET output_sha=? WHERE task_id=? AND step_id='S02'",("0"*64,t["id"]))
    old=w.load("post_run",t["id"],good.report_id)
    assert not old.source_current and "18.28%" not in report_html(old)
    conflict=w.create("post_run",t["id"])
    html=report_html(w.load("post_run",t["id"],conflict.report_id))
    assert conflict.results.status=="restricted" and "18.28%" not in html and "限制" in html
    assert DiagnosticReportService(s).get(good.report_id,session_id=t["session_id"])==good

def test_risk_order_preserves_facts(native):
    s,sid=native;r=DiagnosticReportService(s).preflight(sid)
    before=r.model_dump_json();items=ordered_findings(r)
    assert items[0].rule.id=="PD-02" and items[0].status=="unknown"
    assert r.model_dump_json()==before

def test_invalid_report_does_not_select_another(native,monkeypatch):
    s,sid=native;monkeypatch.setenv("CAUSALOPS_HOME",str(s.ws.root))
    w=DiagnosticWorkbench(s);w.create("preflight",sid)
    app=ui(s,"preflight",sid);app.query_params["diagnostic_report"]="f"*64;app.run()
    assert not app.exception and app.error
    with s.ws.connection() as c:assert c.execute("SELECT count(*) FROM diagnostic_reports").fetchone()[0]==1

def test_no_contract_preflight_is_rendered_without_computation(native):
    s,_=native;sid=s.create_task(payload=b"measure\n1\n2\n",name="unregistered.csv")
    w=DiagnosticWorkbench(s);before=counts(s);r=w.create("preflight",sid)
    assert "证据" in report_html(w.load("preflight",sid,r.report_id))
    assert r.context.contract_ref is None and counts(s)==before

def test_mode_and_history_isolation(native):
    s,sid=native;w=DiagnosticWorkbench(s);r=w.create("preflight",sid)
    assert w.history("preflight",sid)[0]["id"]==r.report_id
    with pytest.raises(DesignError):w.load("post_run",sid,r.report_id)
    assert not w.subjects("post_run")

@pytest.mark.parametrize("damage",["schema","hash","observation"])
def test_corrupt_historical_report_has_no_success_fallback(native,monkeypatch,damage):
    s,sid=native;monkeypatch.setenv("CAUSALOPS_HOME",str(s.ws.root))
    w=DiagnosticWorkbench(s);r=w.create("preflight",sid)
    with s.ws.connection() as c:
        if damage=="observation":
            c.execute("DROP TRIGGER diagnostic_observations_no_update")
            c.execute("UPDATE diagnostic_observations SET body_sha=? WHERE assessment_id=?",("0"*64,r.assessment_id))
        else:
            c.execute("DROP TRIGGER diagnostic_reports_no_update")
            row=c.execute("SELECT body FROM diagnostic_reports WHERE id=?",(r.report_id,)).fetchone()
            body=json.loads(row[0])
            if damage=="schema":body["schema_version"]="unknown-version"
            sha="0"*64 if damage=="hash" else digest(body)
            c.execute("UPDATE diagnostic_reports SET body=?,body_sha=? WHERE id=?",(json.dumps(body),sha,r.report_id))
    app=ui(s,"preflight",sid);app.query_params["diagnostic_report"]=r.report_id;app.run()
    assert not app.exception
    assert app.error or damage=="observation"
    assert counts(s)["analysis_runs"]==0

def test_changing_subject_clears_report_without_generation(native,monkeypatch):
    s,sid=native;monkeypatch.setenv("CAUSALOPS_HOME",str(s.ws.root))
    other=s.create_task(payload=b"value\n3\n4\n",name="other.csv")
    w=DiagnosticWorkbench(s);r=w.create("preflight",sid)
    app=ui(s,"preflight",sid);app.query_params["diagnostic_report"]=r.report_id;app.run()
    app.selectbox(key="diag_subject_preflight_"+sid).select(other).run()
    assert app.query_params.get("diagnostic_report","")==""
    with s.ws.connection() as c:assert c.execute("SELECT count(*) FROM diagnostic_reports").fetchone()[0]==1
    assert not app.exception

def test_failed_explicit_check_clears_loading_instead_of_showing_old_success(native,monkeypatch):
    s,sid=native;monkeypatch.setenv("CAUSALOPS_HOME",str(s.ws.root))
    def fail(*args,**kwargs):raise DesignError("受控的证据核验失败，请保留原记录。")
    monkeypatch.setattr(DiagnosticWorkbench,"create",fail)
    before=counts(s);app=ui(s,"preflight",sid)
    app.button(key="diag_check_preflight_"+sid).click().run()
    assert not app.exception and app.error
    assert not any("正在核对" in x.value for x in app.info)
    assert counts(s)==before
