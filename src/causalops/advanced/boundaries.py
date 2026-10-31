"""Predefined sensitivity checks. No assumption is inferred from a diagnostic."""
from __future__ import annotations
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import chi2
from causalops.general.service import DesignError


def ar_null_test(frame, design, exog):
    """Robust AR-style reduced-form test for one endogenous coefficient.

    H0: beta=beta0. Regress Y-beta0*D on [X,Z] and test all excluded
    Z coefficients jointly. HC1 / one-way cluster, asymptotic chi-square.
    This is not linearmodels' similarly named overidentification statistic.
    It is not a confidence-set inversion or CLR test.
    """
    z=frame[design.instruments].to_numpy(float)
    w=np.column_stack([exog.to_numpy(float),z]);k=z.shape[1]
    adjusted=frame[design.outcome].to_numpy(float)-design.ar_null*frame[design.treatment].to_numpy(float)
    kwargs={'cov_type':'HC1'}
    if design.cluster:
        kwargs={'cov_type':'cluster','cov_kwds':{'groups':pd.factorize(frame[design.cluster])[0],'use_correction':True},'use_t':False}
    fitted=sm.OLS(adjusted,w).fit(**kwargs)
    restriction=np.zeros((k,w.shape[1]));restriction[:,-k:]=np.eye(k)
    covariance=restriction@fitted.cov_params()@restriction.T
    if not np.isfinite(covariance).all() or np.linalg.matrix_rank(covariance)<k or np.linalg.eigvalsh(covariance).min()<=0:
        return {'status':'unavailable','null_effect':design.ar_null,'reason':'工具系数联合协方差矩阵不可逆，未报告检验结果。'}
    test=fitted.wald_test(restriction,use_f=False,scalar=True)
    stat=float(test.statistic);pv=float(test.pvalue)
    if not np.isfinite([stat,pv]).all():return {'status':'unavailable','null_effect':design.ar_null,'reason':'检验统计量非有限。'}
    return {'status':'computed','null_effect':design.ar_null,'statistic':stat,'p_value':pv,'degrees_of_freedom':k,'reference':'asymptotic chi-square','covariance':'cluster' if design.cluster else 'HC1','reject_at_5_percent':pv<.05,'implementation':'statsmodels.OLS + robust joint Wald on excluded instruments','interpretation':'仅检验指定效应值；依赖工具有效性及相应渐近条件。不拒绝不表示已证明该效应值，不提供弱工具稳健置信区间。'}


def rd_sensitivity(frame,design,main,kwargs):
    """Prespecified 0.75/1/1.25 h and b; never choose a result by significance."""
    from rdrobust import rdrobust
    h=main.bws.loc['h'].to_numpy(float);bias=main.bws.loc['b'].to_numpy(float)
    rows=[]
    for scale in (.75,1.,1.25):
        row={'bandwidth_scale':scale,'h_left':float(h[0]*scale),'h_right':float(h[1]*scale),'b_left':float(bias[0]*scale),'b_right':float(bias[1]*scale),'status':'computed'}
        try:
            model=main if scale==1 else rdrobust(frame[design.outcome],frame[design.running],**kwargs,h=h*scale,b=bias*scale)
            vals=[float(model.coef.loc['Robust'].iloc[0]),float(model.se.loc['Robust'].iloc[0]),float(model.pv.loc['Robust'].iloc[0]),*map(float,model.ci.loc['Robust'])]
            if min(model.N_h)<20 or not np.isfinite(vals).all() or vals[1]<=0:raise ValueError('insufficient support')
            if design.cluster:
                local=frame[design.running].between(design.cutoff-h[0]*scale,design.cutoff+h[1]*scale)
                if frame.loc[local,design.cluster].nunique()<30:raise ValueError('insufficient local clusters')
            row.update(estimate=vals[0],std_error=vals[1],p_value=vals[2],ci95_low=vals[3],ci95_high=vals[4],n_left=int(model.N_h[0]),n_right=int(model.N_h[1]))
        except (ValueError,np.linalg.LinAlgError,ZeroDivisionError) as exc:
            row.update(status='unavailable',reason='该带宽下支持不足或估计失败。',error_type=type(exc).__name__)
        rows.append(row)
    return rows


def boundary_rows(method):
    common=[{'检查事项':'识别条件','当前状态':'研究者确认','说明':'统计诊断不能证明随机化、工具有效性、连续性或平行趋势。'}]
    details={
        'iv_2sls':[('指定效应值 AR 型检验','已实现','HC1或单向聚类的渐近联合检验；不等同于弱工具稳健区间。'),('AR置信集合与CLR','尚未实现','常规2SLS区间仍依赖强识别，不能替代AR/CLR。')],
        'rd_sharp':[('带宽敏感性','已实现','固定比较主带宽的0.75、1和1.25倍；完整保留失败行。'),('密度与协变量连续性检验','尚未实现','需要另行预定；未检验不能表述为通过。')],
        'rd_fuzzy':[('局部处理概率跳跃','已实现','同一主带宽下报告处理变量跳跃及区间。'),('弱第一阶段稳健区间','尚未实现','处理跳跃精度不足时只保留关联解释。'),('带宽敏感性','已实现','固定比较0.75、1和1.25倍主带宽。'),('密度与协变量连续性检验','尚未实现','不因处理跳跃显著而默认阈值不可操纵。')],
        'staggered_did':[('对照组与处理前诊断','已实现','报告批次ATT、动态效应及联合检验；未拒绝不证明平行趋势。'),('不平衡面板及上层政策聚类','尚未支持','明确停止执行；不自动补零、删单位或改聚类。'),('同时置信带','尚未实现','动态结果仅提供逐点置信区间。')]
    }
    return common+[{'检查事项':a,'当前状态':b,'说明':c} for a,b,c in details[method]]
