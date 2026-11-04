import pytest
from causalops.application.saved_answers import saved_answer


def answer(question, *, measurement=None, unit='元', denominator=True, n=4, d=2, row_unit='门店日'):
    fields=[dict(field='sales',meaning='销售额',unit=unit),dict(field='volume',meaning='交易笔数',unit='笔')]
    contract=dict(outcome='sales',fields=fields,metric_label='销售额',metric_unit=unit,
                  analysis_unit=row_unit,metric_window='本周',measurement=measurement or {})
    facts={'rows':dict(run_id='r',text='纳入表行数',path='summary.row_count',value=4)}
    for i,(field,stats) in enumerate([('sales',dict(mean=90,finite_n=4,min=10,max=150,median=2)),
                                      ('volume',dict(mean=d,finite_n=n,min=0))]):
        if i and not denominator:continue
        for stat,value in stats.items():
            facts[field+stat]=dict(run_id='r',text=f'{field} / {stat}',path=f'summary.numeric[{i}].{stat}',value=value)
    return saved_answer(facts,dict(run_id='r',method='descriptive'),contract,question)


DECL=dict(numerator='sales',denominator='volume',aggregation='ratio_of_sums')


def test_no_transaction_denominator():
    a=answer('请看旧报告，每笔交易平均金额能从日销售额直接得出吗？',denominator=False)
    assert a and '交易笔数' in a['text'] and not a['facts']


def test_matched_sums_are_not_an_average_of_daily_ratios():
    a=answer('每笔交易的平均销售额是多少？',measurement=DECL)
    assert a and '45' in a['text'] and '元' in a['text'] and 'volume' in a['text']
    assert all(f['run_id']=='r' for f in a['facts']) and len(a['facts'])>=4


@pytest.mark.parametrize('n,d',[(3,2),(4,0)])
def test_incomplete_or_zero_denominator(n,d):
    a=answer('每笔交易的平均销售额是多少？',measurement=DECL,n=n,d=d)
    assert a and ('零' in a['text'] or '缺失' in a['text']) and '45元' not in a['text']


def test_no_cross_grain_reuse():
    a=answer('每台设备的平均销售额是多少？',measurement=DECL)
    assert a and '45元' not in a['text'] and '台' in a['text']


def test_ci_and_range_have_distinct_targets():
    a=answer('样本最大最小值能否当作总体均值的置信区间？')
    assert a and '样本' in a['text'] and '重复抽样' in a['text'] and '总体' in a['text']


def test_unit_bound_to_operand():
    a=answer('中位数不超过2微米）吗？',unit='微米')
    assert '满足' in a['text'] and '等于' in a['text']
    b=answer('已知中位数为2微米，是否等于2毫米？',unit='微米')
    assert '不能' in b['text'] or '不满足' in b['text']


@pytest.mark.parametrize('q,term',[('每名顾客的平均销售额，缺什么？','人数'),('每台机器的平均销售额是多少？','设备数'),
                                   ('平均每天的销售额是多少？','日期数')])
def test_request_grain_when_denominator_unspecified(q,term):
    assert term in answer(q)['text']


def test_mean_of_ratios_not_inferred_from_marginal_means():
    r=answer('每笔交易的平均销售额是多少？',measurement={**DECL,'aggregation':'mean_of_ratios'})
    assert '等权' in r['text'] and not r['facts']


def test_total_is_not_the_mean():
    result=answer('报告的销售额总量是多少？')
    assert '360' in result['text'] and len(result['facts'])==3
