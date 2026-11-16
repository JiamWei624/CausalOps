"""Presentation regressions using real registered-tool snapshots; no fixture answers."""
import copy
import json
from pathlib import Path

import pytest
from test_configurable_research import co, create, approve
from causalops.application.automation_results import snapshot, export_json
from causalops.assistant.service import digest
from causalops.ui.report_view import render_report
from causalops.ui.workspace_navigation import study_catalog, resolve_study


def finished(co, **changes):
    t = create(co, **changes)
    approve(co, t)
    co.run(t['id'])
    return t, snapshot(co, t['id'])


def test_real_report_visuals_keep_original_precision_and_sources(co):
    t, view = finished(co)
    before = digest(view)
    html = render_report(view)
    r = view['report']
    assert f'{r["effect"]["pp"]:+.2f}' in html
    assert all(f'{n:.2f}' in html for n in r['effect']['ci_pp'])
    assert '个百分点' in html and '非相对增长' in html
    assert all(rid in html for rid in r['source_runs'])
    assert json.dumps(r['effect'], ensure_ascii=False, indent=2) in __import__('html').unescape(html)
    assert view['task']['plan_sha'] in html
    assert digest(view) == before
    assert json.loads(export_json(view)) == view


def test_unknown_assignment_never_shows_ab_interval(co):
    _, view = finished(co, assignment='unknown', design_evidence='', source_confirmed=False)
    html = render_report(view)
    assert '随机分配依据未知' in html and '描述' in html
    assert '50.00%' in html and '66.67%' in html
    assert 'data-interval="unavailable"' in html
    assert 'data-interval="available"' not in html
    assert '未执行' in html


def test_candidate_has_no_fabricated_numeric_report(co):
    t = create(co)
    html = render_report(snapshot(co, t['id']))
    assert '尚无通过核验的统计结果' in html
    assert 'class="co-report-metrics"' not in html
    with co.ws.connection() as db:
        assert db.execute('SELECT count(*) FROM analysis_runs').fetchone()[0] == 0


@pytest.mark.parametrize('fault', ['source_run', 'metric', 'window', 'version'])
def test_conflicting_report_identity_hides_numbers(co, fault):
    _, view = finished(co)
    if fault == 'source_run': view['report']['source_runs'][0] = 'another-task-run'
    elif fault == 'version': view['report']['plan_version'] += 1
    else: view['report']['scope'][{'metric':'outcome','window':'window'}[fault]] = 'other'
    html = render_report(view)
    assert '来源冲突' in html
    assert 'class="co-report-metrics"' not in html


def test_damaged_hash_not_patched_with_another_run(co):
    t, _ = finished(co)
    with co.ws.connection() as db:
        db.execute("UPDATE automation_v2_steps SET output_sha='broken' WHERE task_id=? AND step_id='S02'", (t['id'],))
    view = snapshot(co, t['id'])
    assert view['errors']
    html = render_report(view)
    assert '来源冲突' in html and 'class="co-report-metrics"' not in html


def test_reading_report_does_not_change_runs_or_approval(co):
    t, view = finished(co)
    before = digest(co.report(t['id']))
    with co.ws.connection() as db:
        counts = [db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('analysis_runs','exploration_runs','automation_v2_approvals')]
    render_report(view); render_report(snapshot(co, t['id']))
    with co.ws.connection() as db:
        assert counts == [db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('analysis_runs','exploration_runs','automation_v2_approvals')]
    assert digest(co.report(t['id'])) == before


def test_historical_read_remains_separate_from_new_code_authority(co,monkeypatch):
    t, _ = finished(co)
    import causalops.application.automation_coordinator as module
    monkeypatch.setattr(module,'execution_source_sha',lambda:'different-source-version')
    view=snapshot(co,t['id'])
    assert view['binding_error'] and not view['errors'] and view['report']
    html=render_report(view)
    assert '50.00%' in html and '当前执行授权不可用' in html
    with pytest.raises(ValueError):approve(co,t)


def test_report_escapes_user_text(co):
    _, view = finished(co, objective='比较两个组的完成比例 <script>alert(1)</script>')
    html = render_report(view)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html


def test_catalog_and_selection_never_fallback_to_other_task(co):
    t = create(co)
    records = study_catalog(co)
    assert records[0]['id'] == t['id']
    assert '完成比例' in records[0]['label'] and '完整观察期' in records[0]['label']
    with pytest.raises(ValueError): resolve_study(co, 'not-in-this-workspace')
    assert resolve_study(co, '') is None


def test_selector_identity_is_stable_while_task_status_changes(co):
    t=create(co)
    before=study_catalog(co)[0]['selector_label']
    approve(co,t);co.run(t['id'])
    assert study_catalog(co)[0]['selector_label']==before


def test_stale_label_cannot_replace_real_task_id(co,monkeypatch):
    from streamlit.testing.v1 import AppTest
    t=create(co);monkeypatch.setenv('CAUSALOPS_HOME',str(co.ws.root))
    app=AppTest.from_string("import streamlit as st\nfrom causalops.ui.workbench import select_study\nst.session_state['test_pick']='an old formatted label'\nst.button('选择',on_click=select_study,args=('test_pick',))")
    app.query_params['automation']=t['id'];app.run();app.button[0].click().run()
    assert not app.exception
    assert app.query_params['automation']==t['id']


def test_home_and_result_navigation_use_existing_real_task(co, monkeypatch):
    from streamlit.testing.v1 import AppTest
    t, _ = finished(co)
    monkeypatch.setenv('CAUSALOPS_HOME', str(co.ws.root))
    app = AppTest.from_file(Path(__file__).parents[1]/'src/causalops/ui/workbench.py', default_timeout=40)
    app.query_params.update(route='legacy_home',automation=t['id'])
    app.run()
    assert not app.exception
    for dest in ('configure','review','execution','results','evidence','decisions','assistant','analysis','settings','history','guide'):
        assert app.button(key='nav_'+dest)
    app.button(key='nav_results').click().run()
    assert not app.exception and app.query_params['automation'] == t['id']
    assert any(b.label == '导出整体研究报告' for b in app.get('download_button'))


def test_diagnostic_navigation_cannot_mix_another_subject(co,monkeypatch):
    from streamlit.testing.v1 import AppTest
    t=create(co);monkeypatch.setenv('CAUSALOPS_HOME',str(co.ws.root))
    app=AppTest.from_file(Path(__file__).parents[1]/'src/causalops/ui/workbench.py',default_timeout=40)
    app.query_params.update(route='evidence',automation=t['id'],diagnostic_mode='post_run',diagnostic_task='other-task')
    app.run()
    assert not app.exception
    assert any('当前研究与诊断来源选择不一致' in e.value for e in app.error)
