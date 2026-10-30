"""Restricted research extensions backed by pinned upstream estimators."""
from __future__ import annotations
import hashlib,json,uuid,warnings
from pathlib import Path
from datetime import datetime,timezone
from importlib.metadata import version
from typing import Literal
import numpy as np
import pandas as pd
from pydantic import BaseModel,ConfigDict,Field
from scipy.stats import norm
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.general.exploration import clean_json

LABELS={'iv_2sls':'工具变量 2SLS','rd_sharp':'清晰断点回归 RDD','staggered_did':'交错 DID：ATT(g,t)'}
FACT_FIELDS={'allow_complete_case','independent_units_reviewed','design_evidence','instrument_exogeneity_reviewed','exclusion_reviewed','monotonicity_reviewed','continuity_reviewed','no_manipulation_reviewed','threshold_rule_reviewed','parallel_reviewed','no_anticipation_reviewed','no_interference_reviewed','covariates_pre_reviewed'}
class AdvancedDesign(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    method:Literal['iv_2sls','rd_sharp','staggered_did']
    question:str=Field(min_length=8,max_length=1000)
    outcome:str
    treatment:str|None=None
    instruments:list[str]=Field(default_factory=list,max_length=8)
    covariates:list[str]=Field(default_factory=list,max_length=12)
    entity:str|None=None
    cluster:str|None=None
    time:str|None=None
    cohort:str|None=None
    running:str|None=None
    cutoff:float=0.0
    control_group:Literal['never_treated','not_yet_treated']='never_treated'
    unit:str=Field(default='结果指标原单位',max_length=100)
    allow_complete_case:bool=False
    independent_units_reviewed:bool=False
    design_evidence:str=Field(default='',max_length=3000)
    instrument_exogeneity_reviewed:bool=False
    exclusion_reviewed:bool=False
    monotonicity_reviewed:bool=False
    continuity_reviewed:bool=False
    no_manipulation_reviewed:bool=False
    threshold_rule_reviewed:bool=False
    parallel_reviewed:bool=False
    no_anticipation_reviewed:bool=False
    no_interference_reviewed:bool=False
    covariates_pre_reviewed:bool=False

def roles(d):
    return list(dict.fromkeys([x for x in [d.outcome,d.treatment,d.entity,d.cluster,d.time,d.cohort,d.running] if x]+d.instruments+d.covariates))
def sha(value):return hashlib.sha256(json.dumps(clean_json(value),ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
def require(d,*fields):
    missing=[k for k in fields if not getattr(d,k)]
    if missing:raise DesignError('本步骤仍需人工依据：'+', '.join(missing))
    if len(d.design_evidence.strip())<12:raise DesignError('请填写至少12字的具体研究设计依据；不能只勾选或让模型代确认。')
def numeric(f,cols):
    for c in cols:
        try:f[c]=pd.to_numeric(f[c],errors='raise')
        except (ValueError,TypeError):raise DesignError('字段须为数值：'+c) from None
        if not np.isfinite(f[c].dropna().astype(float)).all():raise DesignError('数值字段含无穷：'+c)
def estimate(frame,d):
    named=[x for x in [d.outcome,d.treatment,d.entity,d.time,d.cohort,d.running] if x]
    if len(set(named))!=len(named):raise DesignError('不同角色不能使用同一字段（聚类与实体可相同）。')
    if set(d.instruments)&{d.entity,d.cluster}:raise DesignError('标识不能作为工具变量。')
    required=roles(d)
    if set(required)-set(frame):raise DesignError('字段不存在：'+str(sorted(set(required)-set(frame))))
    predictors=[d.treatment,*d.instruments,*d.covariates] if d.method=='iv_2sls' else [d.running,*d.covariates] if d.method=='rd_sharp' else [d.cohort,d.time,*d.covariates]
    predictors=[x for x in predictors if x]
    if len(set(predictors))!=len(predictors) or d.outcome in predictors:raise DesignError('结果、自变量与工具角色冲突或重复。')
    if set(d.covariates)&{d.entity,d.cluster}:raise DesignError('标识不能作为协变量。')
    if d.covariates and not d.covariates_pre_reviewed:raise DesignError('协变量的处理前时序尚未确认。')
    f=frame[required].copy();before=len(f)
    numeric(f,[c for c in required if c not in {d.entity,d.cluster}])
    # A cohort null is the explicit never-treated encoding, not a missing case.
    complete=f[[c for c in required if not (d.method=='staggered_did' and c==d.cohort)]].notna().all(axis=1)
    dropped=int((~complete).sum())
    if dropped and not d.allow_complete_case:raise DesignError(f'缺失会排除{dropped}行，请先登记完整案例规则。')
    if dropped and d.method=='staggered_did':raise DesignError('面板缺行或字段缺失时不自动删行；请先处理并解释缺失机制。')
    f=f.loc[complete].reset_index(drop=True)
    if len(f)<60 or f[d.outcome].nunique()<2:raise DesignError('本扩展至少60行且结果须有变异。')
    if d.entity and d.method!='staggered_did' and f[d.entity].duplicated().any() and not d.cluster:raise DesignError('重复实体需明确聚类字段，不能按独立行推断。')
    out={'method':d.method,'input_rows':before,'analysis_rows':len(f),'excluded_rows':dropped,'warnings':[],'diagnostics':[],'unit':d.unit,'assumptions_are_human_declarations':True,'claim':'reduced_form','automatic_assumption_verification':False}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        if d.method=='iv_2sls':
            require(d,'instrument_exogeneity_reviewed','exclusion_reviewed','no_interference_reviewed')
            if not d.treatment or not d.instruments:raise DesignError('2SLS须指定一个内生处理和至少一个排除工具。')
            if f[d.treatment].isin([0,1]).all():require(d,'monotonicity_reviewed')
            if not d.cluster:require(d,'independent_units_reviewed')
            from linearmodels.iv import IV2SLS
            x=pd.DataFrame({'const':np.ones(len(f))},index=f.index)
            for c in d.covariates:x[c]=f[c]
            for mat in [x,pd.concat([x,f[[d.treatment]]],axis=1),pd.concat([x,f[d.instruments]],axis=1)]:
                if np.linalg.matrix_rank(mat.to_numpy(float))!=mat.shape[1]:raise DesignError('IV设计矩阵不满秩或工具与控制共线。')
            kwargs={'cov_type':'robust','debiased':True}
            if d.cluster:
                if f[d.cluster].nunique()<30:raise DesignError('当前IV聚类推断要求至少30个独立簇。')
                kwargs={'cov_type':'clustered','clusters':f[d.cluster],'debiased':True}
            r=IV2SLS(f[d.outcome],x,f[[d.treatment]],f[d.instruments]).fit(**kwargs)
            ci=r.conf_int().loc[d.treatment];b=float(r.params[d.treatment]);se=float(r.std_errors[d.treatment]);pv=float(r.pvalues[d.treatment])
            diag=r.first_stage.diagnostics.reset_index().rename(columns={'index':'term'}).to_dict('records')
            # Robust first-stage chi-square is NOT an ordinary F(10) weak-IV certificate.
            first=diag[0];weak=not np.isfinite(first['f.stat']) or first['f.pval']>.05
            out.update(estimate=b,std_error=se,p_value=pv,ci95=[float(ci.iloc[0]),float(ci.iloc[1])],implementation='linearmodels.IV2SLS',package_version=version('linearmodels'),first_stage=diag,estimand='线性IV参数；二元工具/处理在额外单调性下才有局部解释，不自动等于总体ATE')
            out['diagnostics'].append({'name':'工具相关性检验','status':'warning' if weak else 'informative_only','value':first['f.pval'],'note':'仅报告相关性与partial R²；不能据此排除弱工具或证明排除限制。'})
            out['warnings']+=['常规2SLS置信区间不是弱工具稳健区间；未实现AR/CLR，不能仅用第一阶段显著性作因果结论。','工具外生性和排除限制不能由此表证明。']
            out['claim']='associational' if weak else 'iv_under_declared_assumptions'
        elif d.method=='rd_sharp':
            require(d,'continuity_reviewed','no_manipulation_reviewed','threshold_rule_reviewed','no_interference_reviewed')
            if not d.running:raise DesignError('RDD须明确运行变量和事先存在的阈值。')
            if not d.cluster:require(d,'independent_units_reviewed')
            if d.cluster and f[d.cluster].nunique()<30:raise DesignError('当前RD聚类推断要求至少30簇。')
            if d.treatment and not f[d.treatment].eq((f[d.running]>=d.cutoff).astype(int)).all():raise DesignError('处理不完全遵循阈值；这是模糊断点，不能套清晰断点执行器。')
            left=f.loc[f[d.running]<d.cutoff,d.running];right=f.loc[f[d.running]>=d.cutoff,d.running]
            if min(len(left),len(right))<30 or min(left.nunique(),right.nunique())<15:raise DesignError('阈值每侧至少30行、15个不同运行变量取值。')
            from rdrobust import rdrobust
            r=rdrobust(f[d.outcome],f[d.running],c=d.cutoff,p=1,q=2,bwselect='mserd',kernel='tri',masspoints='adjust',covs=f[d.covariates] if d.covariates else None,cluster=f[d.cluster] if d.cluster else None)
            b=float(r.coef.loc['Robust'].iloc[0]);se=float(r.se.loc['Robust'].iloc[0]);pv=float(r.pv.loc['Robust'].iloc[0]);ci=r.ci.loc['Robust'].tolist()
            if min(r.N_h)<20:raise DesignError('自动选带宽内任一侧不足20观测，停止不稳定推断。')
            out.update(estimate=b,std_error=se,p_value=pv,ci95=list(map(float,ci)),implementation='rdrobust.rdrobust robust bias-corrected row',package_version=version('rdrobust'),bandwidth=r.bws.to_dict(),effective_n=list(map(int,r.N_h)),estimand='阈值处的局部跳跃，不外推全体平均效应')
            out['diagnostics']=[{'name':'带宽内样本','status':'informative_only','value':list(map(int,r.N_h)),'note':'使用mserd带宽、局部线性、三角核与稳健偏差校正区间。'}]
            out['warnings']+=['未自动完成运行变量密度/操纵检验和协变量连续性检验；人工声明不是经验检验。','阈值其他政策、排序或堆积可能破坏局部解释；带宽敏感性须另行预定。']
            out['claim']='local_rd_under_declared_assumptions'
            bins=pd.cut(f[d.running],20);plot=f.assign(bin=bins).groupby('bin',observed=True).agg(x=(d.running,'mean'),y=(d.outcome,'mean'),n=(d.outcome,'size'))
            out['plot']=plot.reset_index(drop=True).to_dict('records')
        else:
            require(d,'parallel_reviewed','no_anticipation_reviewed','no_interference_reviewed','independent_units_reviewed')
            if not d.entity or not d.time or not d.cohort:raise DesignError('交错DID须明确实体、整数期序号和首次处理期；从未处理记为空值。')
            if d.cluster and d.cluster!=d.entity:raise DesignError('当前交错DID仅支持实体层聚类，不支持上层聚类。')
            if f.duplicated([d.entity,d.time]).any():raise DesignError('实体×时期不唯一。')
            for c in [d.time,d.cohort]:
                if not f[c].dropna().eq(np.floor(f[c].dropna())).all():raise DesignError('时间与首次处理期必须显式编码为整数期；不自动猜测日期频率。')
            times=sorted(f[d.time].unique());entities=f[d.entity].nunique()
            if len(times)>30 or len(times)<5 or entities>10000:raise DesignError('首版限制5至30期、最多一万个实体。')
            if times!=list(range(int(times[0]),int(times[-1])+1)):raise DesignError('期序必须连续；请先解释频率和缺期。')
            if f.groupby(d.entity)[d.cohort].nunique(dropna=False).max()>1:raise DesignError('同一实体的首次处理期不一致。')
            if not f.groupby(d.entity).size().eq(len(times)).all():raise DesignError('首版交错DID要求平衡面板，不补零或悄悄删单位。')
            groups=f.groupby(d.entity)[d.cohort].first();counts=groups.dropna().value_counts();never=int(groups.isna().sum())
            if len(counts)<2 or counts.min()<20 or never<20:raise DesignError('至少两个处理批次，每批及从未处理组至少20实体。')
            if min(counts.index)<min(times)+2 or max(counts.index)>max(times)-1:raise DesignError('每批至少有两期处理前和两期含处理期的处理后支持。')
            if d.covariates and any(f.groupby(d.entity)[c].nunique().max()>1 for c in d.covariates):raise DesignError('本版仅开放已核对处理前的时间不变协变量；不使用可能受处理影响的时变控制。')
            # Canonical internal names prevent user-provided formula injection.
            names={d.entity:'entity',d.time:'period',d.cohort:'cohort',d.outcome:'outcome',**{c:'x'+str(i) for i,c in enumerate(d.covariates)}}
            data=f.rename(columns=names).set_index(['entity','period']).sort_index()
            from differences import ATTgt
            a=ATTgt(data,cohort_column='cohort',base_period='universal',anticipation=0)
            result=a.fit('outcome'+(' ~ '+' + '.join(names[c] for c in d.covariates) if d.covariates else ''),est_method='reg',control_group=d.control_group,progress_bar=False,n_jobs=1,boot_iterations=0)
            def flat(table):
                t=table.copy();t.columns=[next((v for v in col if v in {'ATT','std_error','lower','upper'}),str(col[-1])) for col in t.columns];return t.reset_index().to_dict('records')
            simple=flat(a.aggregate('simple'))[0];events=flat(a.aggregate('event'));cells=flat(a.results())
            if any('exception' in str(col).lower() for col in a.results().columns):raise DesignError('上游存在失败的批次时间单元，不输出聚合结果。')
            b=float(simple['ATT']);se=float(simple['std_error']);pv=float(2*norm.sf(abs(b/se)))
            # differences 0.3.0 property calls results(sample_name=...), an invalid signature.
            # Use the SAME pinned upstream helper on its native namedtuple influence functions.
            pre={'status':'unavailable','note':'联合检验不可用时不得报告通过。'}
            try:
                from differences.models.attgt.attgt import wald_pre_test
                w=wald_pre_test(result._att_gt['full_sample']['ATTgt_ntl']);pre={'status':'diagnostic_only','note':'未拒绝不证明平行趋势；固定版本官方辅助函数兼容路径。',**w}
            except (ValueError,TypeError,np.linalg.LinAlgError,ZeroDivisionError) as exc:pre['error_type']=type(exc).__name__
            out.update(estimate=b,std_error=se,p_value=pv,ci95=[float(simple['lower']),float(simple['upper'])],implementation='differences.ATTgt outcome-regression; universal base g-1; analytic pointwise intervals',package_version=version('differences'),group_time=cells,event_study=events,pretrend=pre,cohort_counts={str(int(k)):int(v) for k,v in counts.items()},never_treated=never,estimand='按批次规模加权的可识别处理后ATT(g,t)平均，不是TWFE系数')
            out['claim']='staggered_att_under_declared_assumptions' if pre.get('p_value',0)>=.05 else 'associational'
            out['warnings']+=['事件期置信区间为逐点区间，不是同时置信带；未拒绝处理前检验不证明平行趋势。','不同事件期的批次构成可能变化，动态形状不等于同一人群效应轨迹。']
            out['diagnostics']=[{'name':'处理前ATT联合检验','status':pre['status'],'value':pre.get('p_value'),'note':pre['note']}]
        out['upstream_warnings']=list(dict.fromkeys(str(w.message)[:500] for w in caught))
    if not all(np.isfinite([out['estimate'],out['std_error'],*out['ci95']])) or out['std_error']<=0:raise DesignError('估计或不确定性非有限，停止输出。')
    out['conclusion']=f"{LABELS[d.method]}估计差异为{out['estimate']:.4g} {d.unit}，95%区间[{out['ci95'][0]:.4g}, {out['ci95'][1]:.4g}]。这不是自动证实的业务增量；解释范围：{out['estimand']}。"
    return clean_json(out)

class AdvancedWorkspace:
    def __init__(self,workspace=None):
        self.ws=workspace or GeneralWorkspace()
        with self.ws.connection() as c:c.execute('CREATE TABLE IF NOT EXISTS advanced_runs(run_id TEXT PRIMARY KEY,upload_id TEXT NOT NULL,design_json TEXT NOT NULL,result_json TEXT NOT NULL,result_sha TEXT NOT NULL,created TEXT NOT NULL)')
    def run(self,uid,d,*,reviewed=False):
        if not reviewed:raise DesignError('须人工确认具体设计后执行；模型无执行权限。')
        frame=self.ws.load_upload(uid);out=estimate(frame,d);rid=uuid.uuid4().hex
        out.update(run_id=rid,upload_id=uid,design=d.model_dump(),data_fingerprint=sha(frame.to_json()),created=datetime.now(timezone.utc).isoformat())
        with self.ws.connection() as c:c.execute('INSERT INTO advanced_runs VALUES(?,?,?,?,?,?)',(rid,uid,json.dumps(d.model_dump(),ensure_ascii=False),json.dumps(out,ensure_ascii=False),sha(out),out['created']))
        return out
    def load(self,rid):
        with self.ws.connection() as c:r=c.execute('SELECT upload_id,result_json,result_sha FROM advanced_runs WHERE run_id=?',(rid,)).fetchone()
        if not r:raise DesignError('扩展运行不存在。')
        b=json.loads(r[1]);frame=self.ws.load_upload(r[0])
        if sha(b)!=r[2] or b['data_fingerprint']!=sha(frame.to_json()):raise DesignError('扩展证据或数据指纹不一致。')
        return b
