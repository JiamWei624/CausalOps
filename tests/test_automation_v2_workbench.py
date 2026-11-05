
"""V2 workbench: read-only projection, exact approval and original history."""
import json
import pytest
from test_automation_v2 import archive,system,approved,through_s02,ab_runs
from causalops.general.service import DesignError

def test_snapshot_and_report_are_bound_and_read_only(system):
    from causalops.application.automation_results import snapshot,report_html
    co,t=approved(system);co.run(t["id"])
    before=co.report(t["id"])
    v=snapshot(co,t["id"]);html=report_html(v)
    assert v["report"]==before
    assert all(r in html for r in before["source_runs"])
    assert all(x in html for x in ["18.28%","10.62%","7.66","6.995","8.323","两周","批准"])
    assert ab_runs(co)==1

def test_partial_view_cannot_claim_full_report(system):
    from causalops.application.automation_results import snapshot,report_html
    co,t=through_s02(system);co.cancel(t["id"],human_confirmed=True)
    v=snapshot(co,t["id"])
    assert v["report"] is None and "部分完成" in report_html(v)
    assert v["steps"][1]["run_id"] and ab_runs(co)==0

def test_jobs_do_not_authorize_candidate(system):
    from causalops.application.background import AutomationJobs
    co,t=system
    with pytest.raises(DesignError):AutomationJobs(co.s).submit_task(t["id"])
    assert ab_runs(co)==0



def test_page_refresh_reads_same_saved_report(system,monkeypatch):
    from streamlit.testing.v1 import AppTest
    co,t=approved(system);co.run(t["id"]);before=co.report(t["id"])
    monkeypatch.setenv("CAUSALOPS_HOME",str(co.ws.root))
    app=AppTest.from_string("from causalops.ui.automation_app import render\nrender()",default_timeout=30)
    app.query_params["automation"]=t["id"];app.run()
    assert not app.exception
    assert any("已完成" in str(x.value) for x in app.markdown)
    app.run();assert not app.exception
    assert co.report(t["id"])==before and ab_runs(co)==1

def test_ui_review_requires_explicit_check(system,monkeypatch):
    from streamlit.testing.v1 import AppTest
    co,t=system;monkeypatch.setenv("CAUSALOPS_HOME",str(co.ws.root))
    app=AppTest.from_string("from causalops.ui.automation_app import render\nrender()",default_timeout=30)
    app.query_params["automation"]=t["id"];app.run()
    assert not app.exception
    assert app.button(key="automation_start_"+t["id"]).disabled
    assert not app.checkbox(key="automation_approve_"+t["id"]).value
    assert co.task(t["id"])["status"]=="candidate" and ab_runs(co)==0

def test_invalidated_review_is_disabled(system,monkeypatch):
    from streamlit.testing.v1 import AppTest
    co,t=system
    with co.ws.connection() as c:c.execute("UPDATE general_uploads SET frame_sha='changed' WHERE upload_id=?",(t["plan"]["data"]["upload_id"],))
    monkeypatch.setenv("CAUSALOPS_HOME",str(co.ws.root))
    app=AppTest.from_string("from causalops.ui.automation_app import render\nrender()",default_timeout=30)
    app.query_params["automation"]=t["id"];app.run()
    assert not app.exception
    app.checkbox(key="automation_approve_"+t["id"]).check().run()
    assert app.button(key="automation_start_"+t["id"]).disabled and ab_runs(co)==0

def test_corrupt_evidence_never_exports_full_success(system):
    from causalops.application.automation_results import snapshot,report_html
    co,t=approved(system);co.run(t["id"])
    with co.ws.connection() as c:c.execute("UPDATE automation_v2_steps SET output_sha='changed' WHERE task_id=? AND step_id='S02'",(t["id"],))
    view=snapshot(co,t["id"])
    assert view["report"] is None and view["errors"]
    assert "部分完成说明" in report_html(view)

def test_automation_background_is_idempotent(system):
    import time
    from causalops.application.background import AutomationJobs
    co,t=approved(system);j=AutomationJobs(co.s)
    first=j.submit_task(t["id"])
    try:second=j.submit_task(t["id"])
    except DesignError:second=first  # worker may already have completed
    assert second["id"]==first["id"]
    for _ in range(200):
        if j.jobs(t["id"])[0]["status"] not in ("queued","running"):break
        time.sleep(.05)
    assert co.task(t["id"])["status"]=="completed" and ab_runs(co)==1
    assert len(j.jobs(t["id"]))==1



def test_exception_after_runtime_commit_keeps_original_error_and_run(system,monkeypatch):
    co,t=approved(system)
    def injected(point,tid,step):
        if point=="stat_committed" and step=="S02":raise OSError("controlled error after completed runtime")
    monkeypatch.setattr(co,"_fault",injected)
    assert co.run(t["id"])["status"]=="interrupted"
    with co.ws.connection() as c:assert c.execute("SELECT count(*) FROM exploration_runs").fetchone()[0]==1
    monkeypatch.setattr(co,"_fault",lambda *a:None)
    co.resume(t["id"],human_confirmed=True);co.run(t["id"])
    assert co.task(t["id"])["status"]=="completed" and ab_runs(co)==1
