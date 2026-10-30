"""Clustered linear adjustment with categorical fixed effects, association only."""
from __future__ import annotations

import numpy as np
import pandas as pd
from linearmodels.iv.absorbing import AbsorbingLS
from scipy.stats import t as student_t

from causalops.schemas import CausalSpec, DiagnosticResult, EstimateResult
from .base import EstimatorOutput


def estimate_clustered_regression(frame: pd.DataFrame, spec: CausalSpec) -> EstimatorOutput:
    if not spec.cluster_column:
        raise ValueError("关联回归必须明确聚类字段。")
    required = list(dict.fromkeys([spec.treatment, spec.outcome, spec.cluster_column, *spec.covariates]))
    missing = sorted(set(required)-set(frame.columns))
    if missing: raise ValueError(f"回归缺少字段：{missing}")
    # Selection of controls must be explicit; avoid silently accepting obvious outcomes/future summaries.
    forbidden = [c for c in spec.covariates if '_incl' in c or c.startswith(('next_', 'within_', 'cox_'))
                 or c in {'user_total_mentions', 'reply_delay_sec', 'reply_cat', 'comment_id'}]
    if forbidden: raise ValueError(f"控制变量包含明显处理后/未来信息：{forbidden}")
    data = frame[required].copy()
    categorical = [c for c in spec.covariates if not pd.api.types.is_numeric_dtype(data[c])]
    numeric = [spec.treatment, spec.outcome, *[c for c in spec.covariates if c not in categorical]]
    for c in numeric:
        data[c] = pd.to_numeric(data[c], errors='raise').replace([np.inf,-np.inf],np.nan)
    data = data.dropna().reset_index(drop=True)
    if len(data)<10 or data[spec.treatment].nunique()<2:
        raise ValueError("有效样本或处理变量变化不足。")
    cluster_codes, cluster_labels = pd.factorize(data[spec.cluster_column],sort=True)
    g = len(cluster_labels)
    if g<2: raise ValueError("聚类推断至少需要两个独立聚类。")
    numeric_controls = [c for c in spec.covariates if c not in categorical and data[c].nunique()>1]
    removed_constant = [c for c in spec.covariates if c not in categorical and c not in numeric_controls]
    exog = data[[spec.treatment,*numeric_controls]].astype(float)
    exog.insert(0,'const',1.0)
    absorb = data[categorical].astype('category') if categorical else None
    fitted = AbsorbingLS(data[spec.outcome].astype(float),exog,absorb=absorb,drop_absorbed=True).fit(
        cov_type='clustered',clusters=cluster_codes,debiased=True,use_cache=False)
    if spec.treatment not in fitted.params:
        raise ValueError("处理变量被固定效应吸收，无法估计关联系数。")
    beta,se=float(fitted.params[spec.treatment]),float(fitted.std_errors[spec.treatment])
    if not np.isfinite(beta) or not np.isfinite(se) or se<=0:
        raise ValueError("主系数或聚类标准误无效。")
    critical=float(student_t.ppf(.975,g-1))
    p=float(2*student_t.sf(abs(beta/se),g-1))
    binary=set(data[spec.outcome].unique()).issubset({0,1})
    predictions=np.asarray(fitted.fitted_values).ravel()
    ugc=spec.domain.value=='ugc'
    diagnostics=[
        DiagnosticResult(name='clustered_regression_groups',passed=g>=30,value=g,threshold='>=30',
                         message='已按指定实体聚类；聚类数量阈值只是常用诊断规则，不验证独立性或因果识别。',claim_blocking=False),
        DiagnosticResult(name='regression_finite_inference',passed=True,value=True,
                         message='主分析系数、聚类标准误和区间均为有限值。',claim_blocking=False),
        DiagnosticResult(name='unverified_identification',passed=False,value=False,
                         message=('观察性回复并非随机分配；本次只报告条件相关关系，未验证无未观察混杂、无干扰或处理时序。' if ugc else '观察性处理并非随机分配；本次仅报告条件相关，未验证无未观察混杂、无干扰或时间顺序。')),
    ]
    warnings=[
        '本次执行由用户授权为探索性关联分析，不代表识别假设已获确认或因果研究设计已批准。',
        '回复是否到达和回复到达时间可能与用户行为共同决定；发帖后才发生的回复存在时间顺序和反向选择风险。',
        '标准误按用户聚类，允许同一用户多条事件相关；聚类稳健推断不消除选择偏差或测量误差。',
    ]
    if not ugc:
        warnings[1]='观察性处理的选择机制、测量时点和未观察混杂仍需研究设计支持；回归调整不自动识别因果效应。'
        warnings[2]='标准误按指定分析实体聚类；聚类稳健推断不消除选择偏差或测量误差。'
    if binary:
        warnings.append('二元结果采用线性概率模型：系数乘以100可转换为百分点差异，不能直接称为相对百分比提升。')
    if removed_constant: warnings.append('以下常量控制变量未进入回归：'+','.join(removed_constant))
    raw=data.groupby(spec.treatment,dropna=False)[spec.outcome].agg(['count','mean']).reset_index()
    monthly=[]
    if spec.time_column in data:
        monthly=data.groupby([spec.time_column,spec.treatment],observed=True)[spec.outcome].agg(['count','mean']).reset_index().rename(
            columns={spec.time_column:'period',spec.treatment:'treatment','count':'n','mean':'outcome_mean'}).to_dict('records')
    coefficient_table=[]
    for name,value in fitted.params.items():
        s=float(fitted.std_errors[name]); coefficient_table.append({'term':name,'estimate':float(value),'standard_error':s,
            'ci_lower':float(value)-critical*s,'ci_upper':float(value)+critical*s})
    evidence={
        'estimator_version':'absorbing_lpm_clustered_v1','cluster_count':g,'cluster_column':spec.cluster_column,
        'input_rows':len(frame),'complete_case_rows':len(data),'dropped_rows':len(frame)-len(data),
        'outcome_binary':binary,'coefficient_unit':'probability_difference' if binary else 'outcome_units',
        'percentage_point_difference':beta*100 if binary else None,
        'fixed_effect_columns':categorical,'numeric_control_columns':numeric_controls,
        'removed_constant_controls':removed_constant,'inference_df':g-1,'confidence_level':.95,
        'r_squared':float(fitted.rsquared),'coefficient_table':coefficient_table,
        'raw_group_summary':raw.rename(columns={spec.treatment:'treatment','count':'n','mean':'outcome_mean'}).to_dict('records'),
        'monthly_group_summary':monthly,
        'fitted_outside_probability_range_share':float(np.mean((predictions<0)|(predictions>1))) if binary else None,
        'method_reference_urls':[
            'https://bashtage.github.io/linearmodels/iv/absorbing/linearmodels.iv.absorbing.AbsorbingLS.html',
            'https://bashtage.github.io/linearmodels/iv/absorbing/linearmodels.iv.absorbing.AbsorbingLS.fit.html',
            'https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLSResults.get_robustcov_results.html'],
    }
    return EstimatorOutput(estimate=EstimateResult(estimand='Cluster-adjusted conditional linear association',
        estimate=beta,standard_error=se,confidence_interval=(beta-critical*se,beta+critical*se),p_value=p,sample_size=len(data)),
        diagnostics=diagnostics,evidence=evidence,warnings=warnings)
