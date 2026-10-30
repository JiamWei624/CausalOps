"""Cross-fitted AIPW ATE using official DoubleMLIRM, not PLR's constant slope."""
from __future__ import annotations
import numpy as np
import pandas as pd
from doubleml import DoubleMLData,DoubleMLIRM
from doubleml.utils import PSProcessorConfig
from sklearn.ensemble import HistGradientBoostingRegressor,HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold
from causalops.schemas import CausalSpec,EstimateResult,DiagnosticResult
from .base import EstimatorOutput

def estimate_aipw_ate(frame:pd.DataFrame,spec:CausalSpec,*,seed=20261031,n_folds=5)->EstimatorOutput:
    required=[spec.treatment,spec.outcome,*spec.covariates]
    if not spec.covariates or set(required)-set(frame):raise ValueError('AIPW需要明确处理前数值协变量。')
    data=frame[required].copy()
    if data.isna().any().any() or not np.isfinite(data.to_numpy(dtype=float)).all():raise ValueError('AIPW输入必须为完整有限数值；先明确缺失处理规则。')
    if set(data[spec.treatment].unique())!={0,1}:raise ValueError('AIPW仅支持二元处理。')
    if spec.entity_id_column and frame[spec.entity_id_column].duplicated().any():raise ValueError('首版AIPW仅支持独立实体一行，不能以行随机分折处理重复实体。')
    if spec.cluster_column and spec.cluster_column!=spec.entity_id_column:raise ValueError('首版AIPW不支持另一层级的聚类推断。')
    minimum=int(data[spec.treatment].value_counts().min());folds=min(n_folds,minimum)
    if folds<2 or len(data)<30:raise ValueError('AIPW样本不足以交叉拟合。')
    x=data[spec.covariates];d=data[spec.treatment].to_numpy();y=data[spec.outcome].to_numpy()
    splits=list(StratifiedKFold(folds,shuffle=True,random_state=seed).split(x,d))
    g=HistGradientBoostingRegressor(max_iter=80,max_depth=4,min_samples_leaf=15,random_state=seed)
    m=HistGradientBoostingClassifier(max_iter=80,max_depth=4,min_samples_leaf=15,random_state=seed)
    model=DoubleMLIRM(DoubleMLData(data,y_col=spec.outcome,d_cols=spec.treatment,x_cols=spec.covariates),ml_g=g,ml_m=m,n_folds=folds,n_rep=1,score='ATE',normalize_ipw=False,ps_processor_config=PSProcessorConfig(clipping_threshold=.01),draw_sample_splitting=False)
    model.set_sample_splitting(splits);model.fit(n_jobs_cv=1,store_predictions=True)
    pred=model.predictions;ps=np.asarray(pred['ml_m']).reshape(-1);g0=np.asarray(pred['ml_g0']).reshape(-1);g1=np.asarray(pred['ml_g1']).reshape(-1)
    # Library predictions use the declared clipped score probabilities.
    used=np.clip(ps,.01,.99);scores=g1-g0+d*(y-g1)/used-(1-d)*(y-g0)/(1-used)
    identity=bool(np.isclose(scores.mean(),model.coef[0],atol=1e-9,rtol=1e-9));overlap=float(np.mean((used>=.05)&(used<=.95)));clipped=float(np.mean((ps<=.01)|(ps>=.99)))
    ci=model.confint(level=.95).iloc[0].to_numpy(dtype=float)
    diagnostics=[DiagnosticResult(name='aipw_score_identity',passed=identity,value=float(abs(scores.mean()-model.coef[0])),threshold='<=1e-9',message='官方IRM结果与交叉拟合AIPW公式复算一致；该检查不是识别验证。'),DiagnosticResult(name='out_of_fold_propensity_overlap_005_095',passed=overlap>=.9,value=overlap,threshold='>=0.90',message='交叉拟合倾向得分共同支撑检查；阈值是工程诊断，不是无混杂证明。'),DiagnosticResult(name='aipw_clipping_share',passed=clipped<=.05,value=clipped,threshold='<=0.05',message='倾向得分在0.01/0.99截断边界的比例；高比例限制因果主张。')]
    if not identity:raise ValueError('AIPW得分与官方输出不一致，停止保存。')
    return EstimatorOutput(estimate=EstimateResult(estimand='Cross-fitted AIPW average treatment effect (IRM-ATE)',estimate=float(model.coef[0]),standard_error=float(model.se[0]),confidence_interval=(float(ci[0]),float(ci[1])),p_value=float(model.pval[0]),sample_size=len(data)),diagnostics=diagnostics,evidence={'library':'DoubleMLIRM','score':'ATE','n_folds':folds,'seed':seed,'propensity_clipping':[.01,.99],'score_recomputed_mean':float(scores.mean()),'overlap_share':overlap,'clipping_boundary_share':clipped,'sample_splitting':'stratified by treatment; independent entities only','sources':['https://docs.doubleml.org/stable/guide/scores.html','https://github.com/DoubleML/doubleml-for-py']},warnings=['AIPW的双重稳健性不意味着识别双保险；仍需无未测混杂、共同支撑、一致性及适当的独立单位假设。','当前效应为原结果单位的ATE；不将调整后的ATE除以原始对照均值来编造相对提升。'])
