"""Real Streamlit state tests for explicit decisions and bound histories."""
import pytest
from streamlit.testing.v1 import AppTest
from test_diagnostics_stage1 import native,completed,counts
from test_automation_v2 import archive
from causalops.application.diagnostics.reports import DiagnosticReportService
from causalops.application.diagnostics.decisions import ResearchDecisionService
from causalops.application.diagnostics.workbench import DiagnosticWorkbench
from causalops.ui.decision_memory import render_memory

def app(s,sid,report,monkeypatch,mode="preflight",task=None):
 monkeypatch.setenv("CAUSALOPS_HOME",str(s.ws.root))
 a=AppTest.from_string("from causalops.ui.diagnostics_app import render\nrender()",default_timeout=40)
 a.query_params.update(diagnostic_mode=mode,diagnostic_task=task or sid,diagnostic_report=report.report_id)
 return a.run()

def test_ui_only_explicit_submit_and_refresh(native,monkeypatch):
 s,sid=native;r=DiagnosticReportService(s).preflight(sid);su=r.suggestions[0]
 a=app(s,sid,r,monkeypatch);before=counts(s)
 assert not a.exception and a.button(key="decision_save_"+r.report_id+"_"+su.suggestion_id).disabled
 assert any("尚无研究决定" in x.value for x in a.info)
 a.selectbox(key="decision_type_"+r.report_id+"_"+su.suggestion_id).set_value("deferred")
 a.checkbox(key="decision_confirm_"+r.report_id+"_"+su.suggestion_id).check().run()
 a.text_area(key="decision_reason_"+r.report_id+"_"+su.suggestion_id).set_value("先补设计来源，不自动执行")
 a.button(key="decision_save_"+r.report_id+"_"+su.suggestion_id).click().run()
 assert not a.exception
 m=ResearchDecisionService(DiagnosticWorkbench(s));row=m.history("preflight",sid)[0].decision
 assert row.decision_type=="deferred" and row.reason=="先补设计来源，不自动执行"
 b=app(s,sid,r,monkeypatch)
 assert not b.exception and any(row.reason in x.value for x in b.text)
 assert counts(s)==before
 a.button(key="decision_save_"+r.report_id+"_"+su.suggestion_id).click().run()
 assert len(m.history("preflight",sid))==1

def test_ui_note_without_suggestions_and_literal_text(completed,monkeypatch):
 s,t=completed;r=DiagnosticReportService(s).post_run(t["id"],session_id=t["session_id"])
 a=app(s,t["session_id"],r,monkeypatch,"post_run",t["id"])
 assert not a.exception and not r.suggestions
 key=r.report_id+"_note"
 a.checkbox(key="decision_confirm_"+key).check().run()
 a.text_area(key="decision_reason_"+key).set_value("<img src='not-a-request'>仅解释两周")
 a.button(key="decision_save_"+key).click().run()
 assert not a.exception and any("<img" in x.value for x in a.text)
 assert not any(b.label=="立即执行建议" for b in a.button)

def test_ui_stale_source_disables_save_but_preserves_history(native,monkeypatch):
 s,sid=native;r=DiagnosticReportService(s).preflight(sid);su=r.suggestions[0]
 m=ResearchDecisionService(DiagnosticWorkbench(s))
 m.save("preflight",sid,r.report_id,"deferred","历史决定",suggestion_id=su.suggestion_id,human_confirmed=True)
 c=s.contracts.latest(sid);s.contracts.save(sid,{**c["body"],"notes":"来源更新"},expected_sha=c["sha"],human_confirmed=True)
 a=app(s,sid,r,monkeypatch)
 assert not a.exception and a.button(key="decision_save_"+r.report_id+"_"+su.suggestion_id).disabled
 assert any("历史决定" in x.value for x in a.text)

def test_ui_cross_task_report_does_not_show_old_history(native,monkeypatch):
 s,sid=native;r=DiagnosticReportService(s).preflight(sid)
 other=s.create_task(payload=b"x\n1\n2\n",name="different.csv")
 a=app(s,other,r,monkeypatch)
 assert not a.exception and a.error
 assert not any("decision_save_" in (b.key or "") for b in a.button)
