import pytest
from test_v21_flow_boundaries import study, completed_orders, review
from causalops.application.run_context import review_preview, split_request
from causalops.application.report_scope import match_requested_report


def test_explicit_range_and_backward_rolling_window(study):
    s,sid,frame=study
    old,old_id=completed_orders(s,sid)
    request='表内最新日期往回算的四个自然日，请为这些天的订单数建立新方案。'
    new=s.start(sid,request,parent_flow_id=old['id'])
    assert new['status']=='awaiting_review'
    assert new['request']['analysis_scope']['covered_days']==4
    binding=s.data_binding(sid)
    question='2026-03-25 至 2026-03-28 的均值是否大于 2 单？'
    assert match_requested_report(s,sid,question,[old_id],binding)['error']
    reply=s.start(sid,question,run_ids=[old_id])
    assert reply['status']=='needs_clarification'
    assert not s.output(reply['id'],'answer')['facts']
    review(s,new)
    new_id=s.a.selected_run(sid)
    assert new_id!=old_id
    assert match_requested_report(s,sid,question,[old_id],binding)['ids']==[new_id]
    assert match_requested_report(s,sid,'指定运行 '+old_id+' '+question,[old_id],binding)['error']
    assert match_requested_report(s,sid,'截至2026-03-28的所选报告',[old_id],binding)['error']
    assert len(s.a.completed_runs(sid))==2


@pytest.mark.parametrize('text', ['查看候选方案和需核对的指标。','先说清新时间范围和需要核对的内容。'])
def test_pending_readback(text):
    assert review_preview(text)
    assert not review_preview(text+'请改为新的指标。')


def test_compound_delivers_readback_before_proposal():
    assert split_request('先从已完成报告给出关联方向；再提出 OLS 方案，暂不执行。')


def test_same_numbers_cannot_substitute_for_a_different_metric(tmp_path):
    import pandas as pd
    from test_v21_flow_boundaries import reopen
    s=reopen(tmp_path)
    frame=pd.DataFrame({'sold':[2,4,6,8], 'returned':[2,4,6,8]})
    sid=s.create_task(payload=frame.to_csv(index=False).encode(),name='totals.csv')
    s.contracts.save(sid,dict(analysis_unit='仓库',outcome='sold',metric_unit='件',metric_label='售出件数',
                             predictors=['returned'],metric_kind='count'),expected_sha=None,human_confirmed=True)
    old=s.start(sid,'请描述 sold 的样本分布。',mode='plan')
    review(s,old)
    rid=s.a.selected_run(sid)
    reply=s.start(sid,'指标为 returned 的均值是多少？',run_ids=[rid])
    answer=s.output(reply['id'],'answer')
    assert reply['status']=='needs_clarification' and not answer['facts']
    assert len(s.a.completed_runs(sid))==1


def test_secondary_measure_with_same_number_uses_its_own_business_label_and_unit():
    from causalops.application.saved_answers import saved_answer
    run={'run_id':'r','method':'descriptive'}
    metadata={'outcome':'mass','metric_unit':'千克','metric_window':'本批样品',
              'fields':[{'field':'mass','meaning':'样品净重','unit':'千克'},
                        {'field':'length','meaning':'样品长度','unit':'厘米'}]}
    facts={'m':dict(text='mass / mean',path='summary.numeric[0].mean',value=15.,run_id='r'),
           'l':dict(text='length / mean',path='summary.numeric[1].mean',value=15.,run_id='r')}
    answer=saved_answer(facts,run,metadata,'仅解释样品长度的均值。')
    assert '15厘米' in answer['text'] and [f['id'] for f in answer['facts']]==['l']
    absent=saved_answer({'m':facts['m']},run,metadata,'仅解释样品长度的均值。')
    assert not absent['facts'] and '不能' in absent['text']
