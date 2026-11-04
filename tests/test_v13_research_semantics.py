import pytest
from causalops.application.research_semantics import issue,calculation_forbidden,consultation
from causalops.application.data_contracts import DataContract


def test_time_role_mapping_requires_confirmed_event_and_column():
    q='把建档日期当作治疗开始日期，估计治疗效果。'
    body={'time':'registered','measurement':{'event_label':'治疗','event_time_meaning':'治疗开始日期'}}
    assert issue(q,body)
    body.update(treatment_time='started',fields=[{'field':'started','meaning':'实际用药日'}])
    assert issue(q,body)
    assert not issue(q.replace('建档日期','实际用药日'),body)


def test_no_implicit_ratio_estimator_or_cluster_assumption():
    q='计算总体转化率'
    assert '分母' in issue(q,{})
    assert '未绑定' in issue(q,{'measurement':dict(numerator='events',denominator='visits',aggregation='ratio_of_sums')})
    assert '分配单位' in issue('计算实验结果',{'analysis_unit':'患者','measurement':{'assignment_unit':'医院'}},[{'method':'ab_test'}])
    assert not issue('描述身高分布',{},[{'method':'descriptive'}])
    assert '分母' in consultation('如何汇总转化率，分母不同怎么办？')


def test_no_calculation_and_draft_only_are_distinct():
    assert calculation_forbidden('请解释组内相关，不要拟合')
    assert not calculation_forbidden('制定研究方案，不要执行')
    assert '未授权' in issue('只讨论识别条件',{},[{'method':'ols'}])
    assert DataContract.model_validate({}).measurement.aggregation=='unknown'
