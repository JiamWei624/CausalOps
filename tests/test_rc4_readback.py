from test_v21_flow_boundaries import study,completed_orders,revise_visitors,review
import pytest


def test_median_read_vs_new_estimate(study):
    service,sid,frame=study
    old,rid=completed_orders(service,sid)
    question='只引用所选记录中的中位数，不必用新计划，不要用均值替代。'
    read=service.start(sid,question,run_ids=[rid])
    assert read['status']=='completed' and not read['plan_id']
    answer=service.output(read['id'],'answer')
    assert any(f['text']=='orders / median' for f in answer['facts'])
    assert str(frame.orders.median()).rstrip('0').rstrip('.') in answer['text']
    assert answer['run_ids']==[rid]
    new=service.start(sid,'请制定新的订单分布计算方案。',mode='plan')
    assert new['status']=='awaiting_review'
    assert len(service.a.completed_runs(sid))==1


def test_headcount_is_not_row_count(study):
    service,sid,_=study
    old,rid=completed_orders(service,sid)
    f=service.start(sid,'看看当前报告能不能给出人均每日订单，分母能用行数代替吗？',run_ids=[rid])
    assert not f['plan_id']
    a=service.output(f['id'],'answer')
    assert '人数' in a['text'] and '分母' in a['text'] and '行数' in a['text']
    assert not a['facts']


@pytest.mark.parametrize('question',['先给我看新版。','新方案与旧方案有什么区别？','为什么需要重新批准？'])
def test_review_question_has_durable_answer_and_cannot_approve(study,question):
    s,sid,_=study
    old,rid=completed_orders(s,sid)
    pending=revise_visitors(s,sid,old)
    turn=s.start(sid,question,parent_flow_id=pending['id'])
    ans=s.output(turn['id'],'answer')
    assert turn['status']=='completed' and turn['plan_id'] is None
    assert ans['review_owner']==pending['id'] and 'visitors' in ans['text']
    assert turn['request']['question']==question
    assert s.flow(pending['id'])['status']=='awaiting_review'
    assert len(s.a.plans(sid))==2 and len(s.a.completed_runs(sid))==1


@pytest.mark.parametrize('aggregation,description',[('ratio_of_sums','合计'),('mean_of_ratios','等权')])
def test_registered_ratio_and_zero_denominator(aggregation,description):
    from causalops.application.research_semantics import denominator_note
    note=denominator_note('如何汇总每名员工每天的工单？',dict(analysis_unit='团队日',metric_window='五月',
        measurement=dict(numerator='resolved',denominator='staff_count',aggregation=aggregation)))
    assert all(word in note for word in ('resolved','staff_count','五月',description,'分母为零','未定义'))


def test_negated_new_plan_is_still_read_only(study):
    s,sid,_=study
    old,rid=completed_orders(s,sid)
    flow=s.start(sid,'请只看所选报告最近四天的均值，不用新计划。',run_ids=[rid])
    assert flow['status']=='needs_clarification' and not flow['plan_id']
    assert len(s.a.plans(sid))==1 and len(s.a.completed_runs(sid))==1


def test_saved_extrema_or_explicit_new_scope(study):
    s,sid,frame=study
    old,rid=completed_orders(s,sid)
    f=s.start(sid,'看看原报告中最低和最高记录，不用再建模。',run_ids=[rid])
    answer=s.output(f['id'],'answer')
    assert not f['plan_id'] and answer['run_ids']==[rid]
    assert {fact['value'] for fact in answer['facts']}=={frame.orders.min(),frame.orders.max()}


def test_unknown_exposure_and_unequal_weights():
    from causalops.application.research_semantics import denominator_note
    note=denominator_note('每千机组小时的故障率能否直接从记录数得到？',{})
    assert '总暴露量' in note and '零' in note
    note=denominator_note('不同日期成品率的等权平均能代表整月吗？',{})
    assert '分子' in note and '分母' in note and '权重' in note


def test_new_window_review_with_conditional_explanation(study):
    s,sid,_=study
    old,rid=completed_orders(s,sid)
    f=s.start(sid,'我想看最近五个自然日。请保留原报告，说明实际范围和新方案，我核对后再批准。若不足请说明。',parent_flow_id=old['id'])
    assert f['status']=='awaiting_review'
    assert f['request']['analysis_scope']['covered_days']==5
    assert len(s.a.completed_runs(sid))==1
