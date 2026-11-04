"""Temporal eligibility for inputs of a proposed adjustment, not proof of identification."""
from causalops.general.service import DesignError


CAUSAL_METHODS = {"cuped", "psm", "ipw", "aipw", "double_ml", "did", "ab_test", "staggered_did", "iv_2sls", "rd_sharp", "rd_fuzzy"}


def timing_checks(config, definition):
    purpose = definition.get('purpose')
    method = config.get('method')
    if method in ('descriptive', 'correlation'):
        return []
    treatment = config.get('treatment') or definition.get('treatment')
    causal = purpose == 'causal' or method in CAUSAL_METHODS
    fields = list(config.get('covariates', []))
    if causal or purpose == 'predictive':
        fields.extend(x for x in config.get('predictors', []) if x != treatment)
    timings = {f['field']: f.get('timing', 'unknown') for f in definition.get('fields', [])}
    result = []
    for field in sorted(set(fields)):
        timing = timings.get(field, 'unknown')
        if timing in ('future', 'post_treatment'):
            result.append((field, 'block', f'{field} 登记为处理后或未来测量，不能作为本次处理前调整或预测输入。'))
        elif timing == 'unknown':
            result.append((field, 'review', f'{field} 的测量时点未知，请核对生成逻辑并更新字段口径后再进行因果调整。'))
        else:
            result.append((field, 'declared', f'{field} 的处理前或时间不变属性来自数据字典声明。'))
    return result


def require_eligible(config, definition):
    for field, status, message in timing_checks(config, definition):
        if status == 'block' or (status == 'review' and (
            definition.get('purpose') == 'causal' or config.get('method') in CAUSAL_METHODS)):
            raise DesignError(message)
