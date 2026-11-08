from streamlit.testing.v1 import AppTest
from test_constrained_planning import co,task,approve
from causalops.application.diagnostics.reports import DiagnosticReportService
from causalops.application.diagnostics.workbench import DiagnosticWorkbench
from causalops.ui.diagnostics_app import report_html


def test_candidate_modes_are_explicit_and_missing_model_cannot_be_used(co,monkeypatch):
    t=task(co);monkeypatch.setenv('CAUSALOPS_HOME',str(co.ws.root))
    app=AppTest.from_string('from causalops.ui.automation_app import render\nrender()',default_timeout=30)
    app.query_params['automation']=t['id'];app.run();assert not app.exception
    app.radio(key='planning_mode_'+t['id']).set_value('使用模型辅助生成候选计划').run()
    assert not app.exception
    assert app.button(key='planning_generate_'+t['id']).disabled
    app.checkbox(key='automation_approve_'+t['id']).check().run()
    assert app.button(key='automation_start_'+t['id']).disabled
    app.radio(key='planning_mode_'+t['id']).set_value('使用受限研究模板').run()
    assert not app.button(key='automation_start_'+t['id']).disabled


def test_three_layers_do_not_label_other_metrics_as_customer_visits(co):
    t=task(co);approve(co,t);co.run(t['id']);r=DiagnosticReportService(co.s).post_run(t['id'],session_id=t['session_id'])
    view=DiagnosticWorkbench(co.s).load('post_run',t['id'],r.report_id);text=report_html(view)
    assert all(x in text for x in ['完成比例','50.00%','66.67%','第一层','第二层','第三层'])
    assert '名客户' not in text and '访问率' not in text
    assert 'descriptive' not in r.results.model_dump() # legacy serializer omits absent added field


def test_descriptive_three_layers_show_one_run_and_no_effect_interval(co):
    t=task(co,configuration=dict(assignment='unknown',source_confirmed=False,design_evidence=''));approve(co,t);co.run(t['id'])
    r=DiagnosticReportService(co.s).post_run(t['id'],session_id=t['session_id']);v=DiagnosticWorkbench(co.s).load('post_run',t['id'],r.report_id)
    text=report_html(v)
    assert '真实描述统计' in text and '50.00%' in text and '66.67%' in text
    assert r.results.effect is None and len(r.results.runs)==1
    assert 'descriptive' in r.results.model_dump()
