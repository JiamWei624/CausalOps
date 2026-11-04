import pandas as pd
import pytest
from test_v21_flow_boundaries import study, completed_orders, revise_visitors, review
from causalops.application.saved_answers import saved_answer
from causalops.application.plan_scope import requested_scope


@pytest.mark.parametrize("question,unit,expected",[
    ("均值是否至少负2摄氏度？","摄氏度","满足"),
    ("均值是否大于负2摄氏度？","摄氏度","不满足"),
    ("均值不超过负2摄氏度吗？","摄氏度","满足"),
    ("均值比负1摄氏度低还是高？","摄氏度","低于"),
    ("均值是否超过3元？","摄氏度","不能"),
    ("均值是否至少0个百分点？","摄氏度","不能"),
])
def test_comparison_predicate(question,unit,expected):
    facts={'r:n':{'text':'offset / mean','value':-2.,'run_id':'r','path':'summary.numeric[0].mean','claim':'descriptive'}}
    result=saved_answer(facts,{'run_id':'r','method':'descriptive'},{'outcome':'offset','metric_unit':unit},question)
    assert result and expected in result['text']


def test_calendar_gap_is_conditional_on_contract():
    frame=pd.DataFrame({'day':['2026-02-01','2026-02-03'],'sales':[0,5]})
    plain=dict(time='day',outcome='sales')
    for body,phrase in [(plain,'未声明'),({**plain,'calendar_rule':'daily','calendar_start':'2026-02-01','calendar_end':'2026-02-03'},'应观测')]:
        err=requested_scope('只看最近三个自然日',body,frame)['error']
        assert '2026-02-02' in err and phrase in err and '零' in err


def test_last_answer_not_selected_or_latest(study):
    s,sid,_=study
    old,old_id=completed_orders(s,sid)
    change=revise_visitors(s,sid,old)
    review(s,change)
    new_id=s.a.selected_run(sid)
    s.a.select_run(sid,old_id)
    f=s.start(sid,'请解释刚才答复中的指标和结果。',parent_flow_id=change['id'])
    assert s.output(f['id'],'answer')['run_ids']==[new_id]
    f=s.start(sid,'请解释当前页面选中的报告。',parent_flow_id=change['id'])
    assert s.output(f['id'],'answer')['run_ids']==[old_id]


def test_explain_history_then_new_plan(study):
    s,sid,_=study
    old,rid=completed_orders(s,sid)
    f=s.start(sid,'先解释已有订单报告的平均值，再为 orders 与 visitors 制定 OLS 待审方案，暂不执行。',parent_flow_id=old['id'])
    assert f['status']=='awaiting_review'
    assert s.output(f['id'],'prior_answer')['run_ids']==[rid]
    assert [a['config']['method'] for a in s.a.get_plan(f['plan_id'])['plan']['steps']]==['ols']
    assert len(s.a.completed_runs(sid))==1


@pytest.mark.parametrize('predicate,number,expected',[
    ('大于等于','0','满足'),('小于等于','0','满足'),('超过','0','不满足'),
    ('至多','-1','不满足'),('不超过','1','满足'),('至少','0.5','不满足'),
])
def test_zero_boundary(predicate,number,expected):
    data={'r:n':dict(run_id='r',claim='descriptive',path='summary.numeric[0].mean',text='net / mean',value=0)}
    r=saved_answer(data,{'run_id':'r'},dict(outcome='net',metric_unit='元'),f'均值是否{predicate}{number}元？')
    assert '所问条件'+expected+'。' in r['text']


def test_historical_ambiguity_does_not_start_a_plan(study):
    service,sid,_=study
    f,rid=completed_orders(service,sid)
    updated=revise_visitors(service,sid,f)
    review(service,updated)
    before=len(service.a.plans(sid))
    inquiry=service.start(sid,'请解释之前那个报告。',parent_flow_id=updated['id'])
    assert inquiry['status']=='needs_clarification'
    assert service.output(inquiry['id'],'answer')['run_ids']==[]
    assert len(service.a.plans(sid))==before


def test_threshold_on_left_reverses_the_predicate_not_the_statistic():
    data={'r:n':dict(run_id='r',claim='descriptive',path='summary.numeric[0].mean',text='net / mean',value=3)}
    r=saved_answer(data,{'run_id':'r'},dict(outcome='net',metric_unit='元'),'2元是否小于均值？')
    assert '所问条件满足' in r['text'] and '高于' in r['text']

def test_reference_does_not_override_out_of_scope_metric(study):
    service,sid,_=study
    old,rid=completed_orders(service,sid)
    f=service.start(sid,'据此能说明明年的净利润增加多少吗？',run_ids=[rid],parent_flow_id=old['id'])
    assert service.output(f['id'],'route')['route']=='clarify'
    assert not service.output(f['id'],'execution')

def test_read_only_status_replays_completed_revision(study):
    service,sid,_=study
    old,_=completed_orders(service,sid)
    revision=revise_visitors(service,sid,old)
    review(service,revision)
    rid=service.a.selected_run(sid)
    flow=service.start(sid,'请只说明刚才这一轮到哪一步，如果已经完成，请给我具体均值及来源。',parent_flow_id=revision['id'])
    answer=service.output(flow['id'],'answer')
    assert answer.get('source_flow_id')==revision['id']
    assert answer['run_ids']==[rid] and 'visitors' in answer['text'] and rid in answer['text']
    assert not flow['plan_id'] and len(service.a.completed_runs(sid))==2


def test_status_followup_keeps_real_blocker(study):
    service,sid,_=study
    old,_=completed_orders(service,sid)
    blocked=service.start(sid,'请改为截至2030-03-03的最近三天并提交新方案。',parent_flow_id=old['id'])
    assert blocked['status']=='needs_clarification'
    f=service.start(sid,'请只说明刚才这轮的进度。如果尚未运行请告诉我缺哪项条件。',parent_flow_id=blocked['id'])
    a=service.output(f['id'],'answer')
    assert a.get('source_flow_id')==blocked['id']
    assert '2030-03-02' in a['text'] and not a['run_ids'] and not f['plan_id']
