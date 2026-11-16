"""Real workflow handoff and immutable chat references, never an execution authority."""
import copy
import pytest
from test_configurable_research import co, config, data, approve
from causalops.application.chat_sessions import ChatService
from causalops.application.chat_workflow import ChatWorkflow


def setup_flow(co):
    chats=ChatService(co.s);chat=chats.create()
    chats.submit(chat.id,'比较两组本期完成比例，说明不确定性及限制',request_key='goal')
    chats.import_data(chat.id,data().to_csv(index=False).encode(),name='study.csv',request_key='data')
    flow=ChatWorkflow(chats);handoff=flow.begin(chat.id,request_key='start')
    return chats,chat,flow,handoff


def test_import_to_formal_plan_to_results_keeps_original_turns_and_no_extra_runs(co):
    chats,chat,flow,h=setup_flow(co)
    before=[m['reference'] for m in chats.messages(chat.id)]
    payload,name=flow.input_file(chat.id,h.id)
    t=co.create_configurable(payload,name=name,configuration=config(),request_id='formal',human_confirmed=True,stage2=True)
    flow.publish(chat.id,h.id,t['id'])
    assert flow.refresh(chat.id,h.id)['view']['task']['status']=='candidate'
    assert not chats.view(chat.id)['metadata']['run_ids']
    approve(co,t);co.run(t['id'])
    current=flow.refresh(chat.id,h.id)
    assert current['view']['task']['status']=='completed'
    result=flow.answer_goal(chat.id,h.id)
    assert result.status=='completed'
    assert flow.answer_goal(chat.id,h.id).id==result.id
    assert len(chats.messages(chat.id)[-1]['answer']['run_ids'])==2
    assert '每组样本' in chats.messages(chat.id)[-1]['answer']['text']
    assert [m['reference'] for m in chats.messages(chat.id)][:len(before)]==before
    assert len(chats.view(chat.id)['metadata']['run_ids'])==2
    assert chats.session(chat.id).id!=t['id']


def test_wrong_task_cross_chat_and_changed_data_rejected(co):
    chats,chat,flow,h=setup_flow(co)
    other=chats.create()
    with pytest.raises(ValueError):flow.input_file(other.id,h.id)
    wrong=co.create_configurable(data().assign(completed='no').to_csv(index=False).encode(),name='other.csv',configuration=config(),request_id='wrong',human_confirmed=True,stage2=True)
    with pytest.raises(ValueError):flow.publish(chat.id,h.id,wrong['id'])
    assert chats.binding(chat.id).domain=='assistant'
    payload,name=flow.input_file(chat.id,h.id)
    t=co.create_configurable(payload,name=name,configuration=config(),request_id='right',human_confirmed=True,stage2=True)
    flow.publish(chat.id,h.id,t['id'])
    row=co.s.contracts.latest(t['session_id']);body=copy.deepcopy(row['body']);body['metric_label']='已变更'
    co.s.contracts.save(t['session_id'],body,expected_sha=row['sha'],human_confirmed=True)
    with pytest.raises(ValueError):flow.refresh(chat.id,h.id)
    assert not flow.answer_goal(chat.id,h.id)


def test_unknown_design_never_gives_ab_authority_or_interval(co):
    chats,chat,flow,h=setup_flow(co);payload,name=flow.input_file(chat.id,h.id)
    t=co.create_configurable(payload,name=name,configuration=config(assignment='unknown',source_confirmed=False,design_evidence=''),request_id='unknown',human_confirmed=True,stage2=True)
    flow.publish(chat.id,h.id,t['id'])
    chats.submit(chat.id,'同意，帮我执行',request_key='not-approval')
    assert co.task(t['id'])['status']=='candidate'
    assert not flow.answer_goal(chat.id,h.id)
    approve(co,t);co.run(t['id']);flow.refresh(chat.id,h.id);flow.answer_goal(chat.id,h.id)
    assert 'S04' not in {x['step_id'] for x in co.steps(t['id'])}
    answer=chats.messages(chat.id)[-1]['answer']
    assert len(answer['run_ids'])==1 and '随机' in answer['text']
    assert '正态近似区间' not in answer['text'] and '两个运行' not in answer['text']


def test_candidate_adoption_and_revision_lineage_refresh_only_registered_source(co):
    from causalops.application.constrained_planning import CandidatePlanning
    chats,chat,flow,h=setup_flow(co);payload,name=flow.input_file(chat.id,h.id)
    t=co.create_configurable(payload,name=name,configuration=config(),request_id='start-plan',human_confirmed=True,stage2=True)
    flow.publish(chat.id,h.id,t['id'])
    planner=CandidatePlanning(co);row=planner.history(t['id'])[0]
    newer=planner.adopt(t['id'],row['id'],human_confirmed=True)
    flow.publish(chat.id,h.id,newer['id']);flow.refresh(chat.id,h.id)
    assert chats.binding(chat.id).subject_id==newer['id']
    assert co.task(newer['id'])['status']=='candidate'
    assert not co.task(newer['id']).get('approval')


def test_rename_and_search_titles_never_change_chat_or_task_identity(co):
    chats,chat,flow,h=setup_flow(co);binding=chats.binding(chat.id)
    chats.rename(chat.id,'新标题 · 研究甲')
    assert chats.label(chat.id)=='新标题 · 研究甲'
    assert chats.binding(chat.id)==binding
    assert chats.rename(chat.id,'新标题 · 研究甲').id==chat.id
    with pytest.raises(ValueError):chats.rename(chat.id,' ')
