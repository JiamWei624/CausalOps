"""Association GLMs backed by statsmodels GLM, with explicit outcome and inference contracts."""
from __future__ import annotations
import warnings
import numpy as np,pandas as pd
import statsmodels.api as sm
from causalops.general.service import DesignError

def generalized_association(frame,d):
    if d.covariance not in ('HC0','cluster'):raise DesignError('GLM首版只开放HC0或至少20组的聚类稳健推断，不把OLS的HC3/HAC原样套入。')
    if d.covariance=='HC0' and not d.independent_rows_reviewed:raise DesignError('请先核对行独立，或指定恰当聚类字段。')
    if d.method=='poisson' and not d.comparable_exposure_reviewed:raise DesignError('计数模型须核对暴露时间可比；变暴露offset尚未开放。')
    required=list(dict.fromkeys([d.outcome,*d.predictors,*([d.cluster] if d.covariance=='cluster' and d.cluster else [])]))
    part=frame[required].copy();valid=part.notna().all(axis=1);excluded=int((~valid).sum())
    if excluded and not d.allow_complete_case:raise DesignError('必要字段存在缺失；请明确完整案例规则。')
    part=part.loc[valid];y=pd.to_numeric(part[d.outcome],errors='raise').astype(float)
    if not np.isfinite(y).all() or y.nunique()<2:raise DesignError('结果必须有限且非退化。')
    if d.method=='logit' and not y.isin([0,1]).all():raise DesignError('Logit结果必须恰为0/1。')
    if d.method=='poisson' and ((y<0).any() or not np.allclose(y,np.floor(y))):raise DesignError('Poisson结果必须为非负整数。')
    x=part[d.predictors].copy();cat=[c for c in x if not pd.api.types.is_numeric_dtype(x[c])]
    if any(x[c].nunique()<2 or x[c].nunique()>30 for c in cat):raise DesignError('分类自变量须有2至30个有效水平。')
    x=sm.add_constant(pd.get_dummies(x,columns=cat,drop_first=True,dtype=float).astype(float),has_constant='add')
    if not np.isfinite(x.to_numpy()).all() or np.linalg.matrix_rank(x)!=x.shape[1]:raise DesignError('GLM设计矩阵必须有限且满秩。')
    if len(y)<max(30,10*x.shape[1]):raise DesignError('GLM首版要求至少30行且每个参数至少10行；该下限不证明功效充足。')
    if d.method=='logit' and y.value_counts().min()<max(5,x.shape[1]):raise DesignError('二元两类样本不足以支持当前参数维度。')
    opts={'cov_type':d.covariance}
    if d.covariance=='cluster':
        if not d.cluster or part[d.cluster].nunique()<20:raise DesignError('聚类GLM至少需要20个有效聚类。')
        opts['cov_kwds']={'groups':part[d.cluster],'use_correction':True}
    family=sm.families.Binomial() if d.method=='logit' else sm.families.Poisson()
    try:
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter('always');fit=sm.GLM(y,x,family=family).fit(maxiter=100,**opts)
        if any('separation' in str(w.message).lower() for w in recorded):raise DesignError('检测到完全/近完全分离，未报告有限可靠的Logit推断。')
    except (np.linalg.LinAlgError,ValueError) as exc:
        raise DesignError('GLM拟合失败；检查分离、共线性与有效样本。') from exc
    if not fit.converged or not np.isfinite(fit.params).all() or not np.isfinite(fit.bse).all() or (fit.bse<=0).any():raise DesignError('模型未收敛或推断非有限，停止报告。')
    if np.abs(fit.params).max()>30:raise DesignError('系数极端，疑似分离/退化；需要重新设计，未输出夸张优势比。')
    ci=fit.conf_int();dispersion=float(fit.pearson_chi2/fit.df_resid)
    note=('二元条件关联；exp系数是优势比OR，不是概率比或提升百分点。' if d.method=='logit' else '计数条件均值关联；exp系数是等暴露条件均值比，非因果收益；稳健标准误不修复均值模型错设。')
    return {'n':int(fit.nobs),'excluded_complete_case_rows':excluded,'covariance':d.covariance,'model_family':d.method,'converged':bool(fit.converged),'pearson_dispersion':dispersion,'overdispersion_flag':bool(d.method=='poisson' and dispersion>1.5),'coefficients':[{'term':str(t),'coefficient':float(fit.params[t]),'standard_error':float(fit.bse[t]),'ci95_low':float(ci.loc[t,0]),'ci95_high':float(ci.loc[t,1]),'p_value':float(fit.pvalues[t]),'exp_coefficient':float(np.exp(fit.params[t]))} for t in x.columns],'note':note,'sources':['https://www.statsmodels.org/stable/examples/notebooks/generated/glm.html']}
