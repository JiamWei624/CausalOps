"""Actual registered-tool evidence, requested answer fields and read-only artifacts."""
import pytest
from test_configurable_research import config,data
from causalops.general.service import GeneralWorkspace
from causalops.assistant.service import AssistantWorkspace,digest
from causalops.application.research_service import ResearchService
from causalops.application.automation_results import snapshot
from causalops.application.automation_answer import answer

@pytest.fixture(scope='module')
def studies(tmp_path_factory):
    co=ResearchService(AssistantWorkspace(GeneralWorkspace(tmp_path_factory.mktemp('answer')))).automation_v2()
    result=[]
    for key,changes in [('effect',{}),('description',dict(assignment='unknown',design_evidence='',source_confirmed=False))]:
        t=co.create_configurable(data().to_csv(index=False).encode(),name='controlled.csv',configuration=config(**changes),request_id=key,human_confirmed=True,stage2=True)
        co.approve(t['id'],expected_plan_sha=t['plan_sha'],human_confirmed=True);assert co.run(t['id'])['status']=='completed'
        result.append(t)
    return co,*result

@pytest.mark.parametrize('question,required',[
    ('两组比例是多少？',{'groups'}),
    ('请说明样本量、差异和置信区间',{'samples','difference','interval'}),
    ('这个结果有哪些研究限制？',{'limitations'}),
    ('请一次回答两组比例、样本量、差异、置信区间和研究限制',{'groups','samples','difference','interval','limitations'}),
])
def test_requested_fields_from_same_saved_report(studies,question,required):
    co,t,_=studies;view=snapshot(co,t['id']);before=digest(view)
    r=answer(co.a,t['session_id'],view,question)
    assert required<=set(r['coverage'])
    assert all(r['coverage'][k]=='available' for k in required)
    assert r['run_ids']==view['report']['source_runs'] and digest(snapshot(co,t['id']))==before
    if 'samples' in required:assert '12' in r['text'] and '24' in r['text']
    if 'difference' in required:assert '百分点' in r['text']

@pytest.mark.parametrize('question',['这份研究的长期利润和ROI是多少？','结果字段 `retained` 的区间是多少？','请给出字段 "unknown_measure" 的均值'])
def test_uncomputed_metric_is_not_answered_with_current_metric(studies,question):
    co,t,_=studies;r=answer(co.a,t['session_id'],snapshot(co,t['id']),question)
    assert '不支持' in r['text'] or '未计算' in r['text']
    assert '66.67%' not in r['text'] and not r['facts']
    assert r['coverage']['requested_metric']=='unsupported'

def test_mixed_request_delivers_supported_fields_and_states_missing_metric(studies):
    co,t,_=studies
    r=answer(co.a,t['session_id'],snapshot(co,t['id']),'当前完成比例和样本量是多少？长期利润也计算了吗？')
    assert r['coverage']['groups']=='available' and r['coverage']['samples']=='available'
    assert r['coverage']['requested_metric']=='unsupported' and '未计算' in r['text']

def test_description_explicitly_has_no_inferential_interval(studies):
    co,_,t=studies;r=answer(co.a,t['session_id'],snapshot(co,t['id']),'两组比例、样本量、差异、置信区间和研究限制')
    assert r['coverage']['interval']=='not_executed' and '随机分配依据未知' in r['text']
    assert len(r['run_ids'])==1 and '原工具95%' not in r['text']

def test_diagnostic_and_decision_summary_is_actual_readonly_and_task_bound(studies):
    from causalops.application.chat_sessions import ChatService
    from causalops.application.chat_artifacts import artifacts
    from causalops.application.diagnostics.workbench import DiagnosticWorkbench
    from causalops.application.diagnostics.decisions import ResearchDecisionService
    co,t,other=studies;chats=ChatService(co.s);chat=chats.create();chats.bind(chat.id,'automation_v2',t['id'])
    w=DiagnosticWorkbench(co.s);before=digest(co.steps(t['id']))
    assert artifacts(chats,chat.id)['diagnostic'] is None
    report=w.create('post_run',t['id']);m=ResearchDecisionService(w)
    m.save('post_run',t['id'],report.report_id,'note','仅支持登记窗口的二元结果，不外推长期利润。',human_confirmed=True)
    state=artifacts(chats,chat.id,report_id=report.report_id)
    assert state['diagnostic']['id']==report.report_id and state['diagnostic']['source_current']
    assert state['decisions']['count']==1 and not state['decisions']['execution_authorized']
    assert digest(co.steps(t['id']))==before
    foreign=w.create('post_run',other['id'])
    with pytest.raises(ValueError):artifacts(chats,chat.id,report_id=foreign.report_id)


def test_long_history_verification_does_not_reuse_stale_events_across_reads(studies):
    import json
    from causalops.application.chat_sessions import ChatService
    co,t,_=studies;chats=ChatService(co.s);chat=chats.create();chats.bind(chat.id,'automation_v2',t['id'])
    before=digest(co.steps(t['id']))
    for i in range(8):chats.submit(chat.id,'请说明两组比例、样本量和差异',request_key='long-'+str(i))
    assert all(x['available'] for x in chats.messages(chat.id))
    with co.ws.connection() as db:
        ref=json.loads(db.execute('SELECT reply FROM chat_turns WHERE chat_id=? ORDER BY ordinal LIMIT 1',(chat.id,)).fetchone()[0])
        db.execute('UPDATE assistant_events SET body=? WHERE id=?',(json.dumps({'text':'不受支持的新数字','run_ids':[]}),ref['event_id']))
    restored=chats.messages(chat.id)
    assert not restored[0]['available'] and all(x['available'] for x in restored[1:])
    assert digest(co.steps(t['id']))==before
