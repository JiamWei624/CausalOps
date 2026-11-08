"""P3 stage2: generic diagnostics over real registered runs, counterexamples first."""
import json
import pytest
from test_configurable_research import co,create,approve,config,data
from causalops.application.diagnostics.reports import DiagnosticReportService
from causalops.application.diagnostics.workbench import DiagnosticWorkbench
from causalops.application.diagnostics.decisions import ResearchDecisionService
from causalops.assistant.service import digest
from causalops.general.service import DesignError

def report(co,t):return DiagnosticReportService(co.s).post_run(t['id'],session_id=t['session_id'])
def states(r):return {x.rule.id:x.status for x in r.quality.findings}
def guards(co):
    with co.ws.connection() as db:return {name:digest([list(x) for x in db.execute('SELECT * FROM '+name)]) for name in ['analysis_runs','exploration_runs','automation_v2_tasks','automation_v2_approvals','automation_v2_steps']}

def test_generic_six_rules_two_real_runs_and_readonly_report(co):
    t=create(co);approve(co,t);co.run(t['id']);before=guards(co)
    r=report(co,t)
    assert set(states(r).values())=={'verified'},states(r)
    assert '公开包' not in next(f for f in r.quality.findings if f.rule.id=='PD-02').impact.explanation
    assert r.results.status=='available' and len(r.results.runs)==2
    assert r.results.effect['pp']==pytest.approx(100/6)
    assert r.results.scope['analysis_unit']=='独立参与者'
    assert '客户' not in (r.context.scope.denominator or '')
    assert guards(co)==before and report(co,t)==r
    assert len(r.quality.unimplemented_rules)==8 and not r.suggestions
    assert 'two-arm' in r.rule_pack and r.rule_pack_version=='2'


def test_unknown_design_one_saved_run_and_real_description(co):
    t=create(co,assignment='unknown',design_evidence='',source_confirmed=False);approve(co,t);co.run(t['id']);before=guards(co)
    r=report(co,t);s=states(r)
    assert s['PD-01']=='verified' and s['PD-02']=='unknown'
    assert s['PD-07']=='not_checked' and s['PD-14']=='not_checked'
    assert len(r.results.runs)==1 and r.results.effect is None
    assert r.results.descriptive['source_run_id']==co.evidence(t['id'],'S02')['body']['run_id']
    assert r.results.descriptive['difference_pp']==pytest.approx(100/6)
    assert guards(co)==before
    m=ResearchDecisionService(DiagnosticWorkbench(co.s));sg=next(s for s in r.suggestions if s.rule_id=='PD-02')
    d=m.save('post_run',t['id'],r.report_id,'deferred','补充设计依据前仅解释描述性差异',suggestion_id=sg.suggestion_id,human_confirmed=True)
    assert not d.execution_authorized and len(d.context.run_refs)==1
    assert m.history('post_run',t['id'])[0].decision==d
    assert guards(co)==before


@pytest.mark.parametrize('fault',['hash','metric','window','foreign'])
def test_generic_evidence_conflict_restricts_joint_results(co,fault):
    t=create(co);approve(co,t);co.run(t['id'])
    with co.ws.connection() as db:
        if fault=='hash':db.execute("UPDATE automation_v2_steps SET output_sha='corrupt' WHERE task_id=? AND step_id='S02'",(t['id'],))
        else:
            e=co.evidence(t['id'],'S05')
            if fault=='metric':e['body']['scope']['outcome']='wrong_field'
            elif fault=='window':e['body']['scope']['window']='unapproved_window'
            else:e['body']['source_runs']=['0'*32,'1'*32]
            db.execute("UPDATE automation_v2_steps SET output=?,output_sha=? WHERE task_id=? AND step_id='S05'",(json.dumps(e),digest(e),t['id']))
    r=report(co,t)
    assert 'issue' in states(r).values() and r.results.status=='restricted'
    assert r.results.effect is None and r.results.descriptive is None


def test_different_tasks_cannot_share_decisions(co):
    from causalops.application.configurable_research import create as compile_task
    a=create(co,assignment='unknown',source_confirmed=False,design_evidence='');approve(co,a);co.run(a['id'])
    b=compile_task(co,data().to_csv(index=False).encode(),name='same.csv',configuration=config(assignment='unknown',source_confirmed=False,design_evidence=''),request_id='other-task',human_confirmed=True)
    approve(co,b);co.run(b['id']);r=report(co,a);m=ResearchDecisionService(DiagnosticWorkbench(co.s));sg=next(x for x in r.suggestions if x.rule_id=='PD-02')
    with pytest.raises(DesignError):m.save('post_run',b['id'],r.report_id,'deferred','不得跨任务',suggestion_id=sg.suggestion_id,human_confirmed=True)

def test_generic_report_preserves_original_approximation_limitation(co):
    t=create(co);approve(co,t);co.run(t['id']);r=report(co,t)
    assert any('正态近似' in s for s in r.results.limitations)
