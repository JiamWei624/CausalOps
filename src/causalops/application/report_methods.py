"""Read-only labels from verified saved method metadata, never statistical inference."""

def saved_methods(report):
    r=report or {};method=r.get('method')
    result=dict(estimator=None,interval=None,interval_executed=None)
    if method=='descriptive' and r.get('descriptive') and not r.get('effect'):
        result['estimator']='分组描述统计'
        if r['descriptive'].get('interval') is None:
            result.update(interval='没有执行推断区间',interval_executed=False)
    elif method=='ab_test' and r.get('effect'):
        result['estimator']='独立组均值差'
        result['interval_executed']=r['effect'].get('ci_pp') is not None
        if result['interval_executed'] and r.get('interval_method')=='independent-group mean difference; normal approximation 1.96':
            result['interval']='1.96正态近似区间'
    return result


def method_limitations(report):
    base='未验证无干扰、外部代表性和全部识别假设。仅支持登记对象、指标和窗口。'
    if not report:return base+'统计方法和区间尚未完成，不将计划中的方法视为已执行。'
    methods=saved_methods(report)
    if methods['interval_executed'] is False:
        return base+'本研究仅执行分组描述统计，没有执行A/B分析，没有执行推断区间。'
    if methods['estimator'] and methods['interval']:
        return base+'效应估计采用'+methods['estimator']+'；区间采用'+methods['interval']+'。小样本或稀少事件时近似可能不充分，不代表精确随机化检验。'
    return base+'方法未提供完整的可识别说明；不推测估计器或区间算法。'
