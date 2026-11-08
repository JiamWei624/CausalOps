from test_configurable_research import co,create,approve
from streamlit.testing.v1 import AppTest


def page(monkeypatch,co,t):
    monkeypatch.setenv('CAUSALOPS_HOME',str(co.ws.root))
    app=AppTest.from_string('from causalops.ui.automation_app import render\nrender()',default_timeout=30)
    app.query_params['automation']=t['id'];return app.run()


def test_configurable_plan_shows_actual_fields_and_explicit_approval(co,monkeypatch):
    t=create(co);app=page(monkeypatch,co,t)
    assert not app.exception
    text=' '.join(str(x.value) for x in app.markdown)
    assert 'completed' in text and '本次实验' in text and '标准方案' in text
    assert app.button(key='automation_start_'+t['id']).disabled
    assert co.task(t['id'])['status']=='candidate'


def test_report_refresh_uses_same_runs_and_bound_diagnostics(co,monkeypatch):
    t=create(co);approve(co,t);co.run(t['id']);r=co.report(t['id'])
    app=page(monkeypatch,co,t);app.run()
    assert not app.exception and co.report(t['id'])==r
    assert any(b.label=='查看当前研究的证据诊断' for b in app.button)
    assert any(b.label=='检查当前数据的研究条件' for b in app.button)


def test_new_task_has_bound_post_run_diagnostic_subject(co):
    from causalops.application.diagnostics.workbench import DiagnosticWorkbench
    t=create(co);w=DiagnosticWorkbench(co.s)
    assert any(x['id']==t['id'] for x in w.subjects('post_run'))
    assert any(x['id']==t['session_id'] for x in w.subjects('preflight'))

def test_explicit_new_research_resets_only_unsubmitted_editor_state():
    app=AppTest.from_string("import streamlit as st\nfrom causalops.ui.automation_app import _new\nst.button('新建',on_click=_new)")
    app.session_state['cfg_new_data_request']='old-submit'
    app.session_state['config_import_new_data']='old-import'
    app.session_state['cfg_historicaltask_data_request']='keep-old-history'
    app.run();app.button[0].click().run()
    assert not app.exception
    assert 'cfg_new_data_request' not in app.session_state
    assert 'config_import_new_data' not in app.session_state
    assert app.session_state['cfg_historicaltask_data_request']=='keep-old-history'
