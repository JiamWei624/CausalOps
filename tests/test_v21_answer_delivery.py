import pytest
from causalops.application import report_scope


def facts(run, entries):
    return {run+':'+key:dict(run_id=run,text=label,path=path,value=value,claim='descriptive') for key,label,path,value in entries}


@pytest.mark.parametrize('limit,word', [('-3','高于'),('-2.25','等于'),('-1.5','低于')])
def test_compare_signed_values_from_selected_record(limit,word):
    data=facts('source',[('n0.mean','margin / mean','summary.numeric[0].mean',-2.25)])
    reply=report_scope.saved_answer(data,dict(run_id='source',method='descriptive'),dict(outcome='margin',metric_unit='元'),f'margin 的均值是否超过 {limit}？')
    assert word in reply['text'] and '-2.25' in reply['text'] and 'source' in reply['text']


def test_pair_value_with_source_and_missing_pair():
    data=facts('abcd',[('c5.pearson','weight 与 height / pearson','summary.correlations[5].pearson',0.63215)])
    args=(data,dict(run_id='abcd',method='correlation'),{})
    assert '0.632' in report_scope.saved_answer(*args,'weight 和 height 的相关系数是多少？')['text']
    assert '0.632' not in report_scope.saved_answer(*args,'weight 与 unknown 的 Pearson 相关系数？')['text']


def test_rate_display_binds_registered_labels():
    data=facts('rate',[('rate.'+k,k,'/evidence/rate_contrast/'+k,v) for k,v in
                       [('control_rate',.14),('treated_rate',.127),('pp',-1.3),('raw',-.013)]])
    reply=report_scope.saved_answer(data,dict(run_id='rate',method='ab_test'),
        dict(metric_label='访问率',metric_window='十天',control_value='A类',treated_value='B类'),'访问率相差多少个百分点？')
    assert all(x in reply['text'] for x in ('A类','B类','14.00%','12.70%','-1.30','十天','rate'))

def test_ratio_explanation_uses_confirmed_components_and_keeps_zero_numerator():
    from causalops.application.research_semantics import registered_ratio_advice
    text=registered_ratio_advice('应怎样汇总各仓库的损耗率？',{'measurement':{
        'numerator':'lost_items','denominator':'handled_items','aggregation':'ratio_of_sums'}})
    assert all(part in text for part in ('lost_items','handled_items','加权','为零','保留'))
    assert not registered_ratio_advice('应怎样汇总损耗率？',{})


def test_explanation_only_never_becomes_ordered_calculation():
    from causalops.application.plan_scope import ordered_methods
    assert not ordered_methods('只解释先看分布，再用 OLS 的意义，不要计算')
    assert not ordered_methods('请不要执行。先看分布，再使用OLS解释统计学概念。')

def test_followup_keeps_the_previously_requested_statistic_only():
    from causalops.application.saved_answers import threshold_question
    literal='请说它比 -4 高还是低，并给出出处'
    assert '中位数' in threshold_question(literal,'只看转化耗时的中位数。')
    assert threshold_question(literal,'比较均值与中位数。')==literal


def test_change_uses_registered_field_meaning_with_no_identifier_in_question():
    from causalops.application.plan_scope import requested_scope
    import pandas as pd
    data=pd.DataFrame({'units':[1,2], 'buyers':[8,9]})
    contract={'outcome':'units','fields':[{'field':'buyers','meaning':'当日采购人数','unit':'人'}]}
    assert requested_scope('从件数换成每日采购人数，请制定新方案。',contract,data)['outcome']=='buyers'

def test_threshold_percent_uses_same_scale_as_probability():
    data=facts('rate2',[('n0.mean','bought / mean','summary.numeric[0].mean',0.4)])
    res=report_scope.saved_answer(data,dict(run_id='rate2',method='descriptive'),dict(outcome='bought',metric_unit='概率',metric_kind='binary'),'平均值大于30%吗？')
    assert '高于' in res['text'] and '30%' in res['text']
