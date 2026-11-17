"""Upgrade summary is recoverable only after native research and history validation."""
from dataclasses import replace
from test_react_insights_api import api,generate
from test_react_insights import co
from test_configurable_diagnostics import guards
from causalops.application.diagnostics.workbench import DiagnosticWorkbench

def test_stale_verified_diagnostic_keeps_report_and_exposes_explicit_recheck(api,monkeypatch):
    c,h,cid,t,co,_=api;old=generate(c,h,cid);before=guards(co)
    original=DiagnosticWorkbench.load
    def stale(self,*args,**kwargs):
        return replace(original(self,*args,**kwargs),source_current=False,source_error='原生证据已变化，请生成新的诊断快照；旧报告仍可只读查看。')
    monkeypatch.setattr(DiagnosticWorkbench,'load',stale)
    result=c.get(f'/api/chats/{cid}/artifacts')
    assert result.status_code==200
    value=result.json();assert value['diagnostic'] is None
    assert value['diagnostic_status']=='recheck_required'
    assert value['diagnostic_message']=='研究诊断需要重新核验，原有报告和历史记录已保留。'
    assert c.get(f'/api/chats/{cid}/report').status_code==200
    assert guards(co)==before

def test_corrupt_native_report_is_not_translated_to_diagnostic_upgrade(api):
    c,h,cid,t,co,_=api;generate(c,h,cid)
    with co.ws.connection() as db:
        db.execute("UPDATE automation_v2_steps SET output_sha=? WHERE task_id=? AND step_id='S05'",('0'*64,t['id']))
    result=c.get(f'/api/chats/{cid}/artifacts')
    assert result.status_code==409 and result.json()['error']['code']=='source_conflict'
    assert '需要重新核验，原有报告' not in result.text

def test_corrupt_diagnostic_body_is_not_a_recheckable_history(api,monkeypatch):
    c,h,cid,t,co,_=api;v=generate(c,h,cid)
    from causalops.application.diagnostics.reports import DiagnosticReportService
    from causalops.general.service import DesignError
    def broken(*args,**kwargs):raise DesignError('诊断报告内容哈希不一致。')
    monkeypatch.setattr(DiagnosticReportService,'get',broken)
    result=c.get(f'/api/chats/{cid}/artifacts')
    assert result.status_code==409 and 'diagnostic_status' not in result.json()
