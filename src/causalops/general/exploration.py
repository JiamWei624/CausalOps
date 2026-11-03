"""Independent descriptive/correlation/regression tasks; no fabricated causal fields."""
from __future__ import annotations
import hashlib,json,uuid,platform
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
import importlib.metadata as md
import numpy as np,pandas as pd
from scipy import stats
import statsmodels.api as sm
from pydantic import BaseModel,ConfigDict,Field
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.execution import _data_fingerprint

LABELS={'descriptive':'描述性统计分析','correlation':'相关分析（探索性）','ols':'线性关联回归（非因果）','logit':'二元Logit关联（非因果）','poisson':'Poisson计数关联（非因果）'}
class ExplorationDesign(BaseModel):
    model_config=ConfigDict(extra='forbid')
    question:str=Field(min_length=8,max_length=1000)
    method:Literal['descriptive','correlation','ols','logit','poisson']='descriptive'
    numeric:list[str]=Field(default_factory=list,max_length=20)
    categorical:list[str]=Field(default_factory=list,max_length=10)
    group:str|None=None
    date:str|None=None
    frequency:Literal['D','M','Q','Y']='M'
    outcome:str|None=None
    predictors:list[str]=Field(default_factory=list,max_length=20)
    covariance:Literal['HC3','HC0','cluster','HAC']='HC3'
    cluster:str|None=None
    maxlags:int=Field(default=1,ge=1,le=30)
    independent_rows_reviewed:bool=False
    allow_complete_case:bool=False
    comparable_exposure_reviewed:bool=False

def clean_json(v):
    if isinstance(v,dict):return {str(k):clean_json(x) for k,x in v.items()}
    if isinstance(v,(list,tuple,np.ndarray)):return [clean_json(x) for x in v]
    if isinstance(v,(np.integer,)):return int(v)
    if isinstance(v,(float,np.floating)):return float(v) if np.isfinite(v) else None
    if isinstance(v,(np.bool_,)):return bool(v)
    if v is pd.NA or v is pd.NaT:return None
    if isinstance(v,(pd.Timestamp,datetime)):return v.isoformat()
    return v

def validate_frame(frame,d):
    selected=d.numeric+d.categorical+d.predictors+[x for x in (d.group,d.date,d.outcome,d.cluster) if x]
    if not selected or set(selected)-set(frame):raise DesignError('请选择当前表中存在的分析字段。')
    for values in (d.numeric,d.categorical,d.predictors):
        if len(set(values))!=len(values):raise DesignError('同一角色字段不能重复。')
    if set(d.numeric)&set(d.categorical):raise DesignError('数值和分类字段不能重复选择。')
    if d.date in d.numeric or d.date in d.predictors:raise DesignError('日期不得自动作为数值特征。')
    f=frame.copy()
    for c in set(d.numeric+([d.outcome] if d.outcome else [])):
        if pd.api.types.is_datetime64_any_dtype(f[c]):raise DesignError('数值字段不能是日期。')
        try:f[c]=pd.to_numeric(f[c],errors='raise')
        except (ValueError,TypeError):raise DesignError('所选数值字段含不可解析的非数值内容。') from None
    if d.group and f[d.group].nunique(dropna=False)>50:raise DesignError('分组超过50类，请先制定合并规则。')
    if any(f[c].nunique(dropna=False)>1000 for c in d.categorical):raise DesignError('分类字段超过1000类，请勿将ID误作分类变量。')
    if d.method=='correlation' and len(d.numeric)<2:raise DesignError('相关分析至少选择两个数值字段。')
    if d.method in ('ols','logit','poisson') and (not d.outcome or not d.predictors or d.outcome in d.predictors):raise DesignError('回归须指定不同的数值结果与自变量。')
    if d.method=='descriptive' and not (d.numeric or d.categorical):raise DesignError('描述统计至少选择一个数值或分类字段。')
    return f

def describe(f,d):
    n=len(f);result={'row_count':n,'column_count':len(f.columns),'exact_duplicate_rows':int(f.duplicated().sum()),'columns':[{'field':c,'dtype':str(f[c].dtype),'missing':int(f[c].isna().sum()),'missing_pct':float(f[c].isna().mean()*100),'distinct_nonmissing':int(f[c].nunique())} for c in f],'numeric':[],'categorical':[],'grouped':[],'trend':[],'histograms':[],'correlations':[]}
    for c in d.numeric:
        v=f[c];finite=v[np.isfinite(v.fillna(np.nan).astype(float))].astype(float);count=len(finite);q=finite.quantile([.25,.5,.75]) if count else pd.Series([np.nan]*3,index=[.25,.5,.75]);iqr=q[.75]-q[.25]
        result['numeric'].append({'field':c,'finite_n':count,'missing_n':int(v.isna().sum()),'infinite_n':int(np.isinf(v.fillna(0).astype(float)).sum()),'mean':finite.mean(),'std_ddof1':finite.std(ddof=1),'min':finite.min(),'q25':q[.25],'median':q[.5],'q75':q[.75],'max':finite.max(),'zero_n':int((finite==0).sum()),'iqr_flag_n':int(((finite<q[.25]-1.5*iqr)|(finite>q[.75]+1.5*iqr)).sum())})
        if count:
            counts,edges=np.histogram(finite,bins=min(20,max(1,int(np.sqrt(count)))));hist={'field':c,'counts':counts.tolist(),'edges':edges.tolist()}
            if finite.nunique()<=20 and bool((finite%1==0).all()):
                freq=finite.value_counts().sort_index();hist.update(value_type='discrete',values=freq.index.tolist(),frequencies=freq.tolist())
            result['histograms'].append(hist)
    for c in d.categorical:
        series=f[c].astype('string');vc=series.value_counts(dropna=False);rows=[]
        for val,k in vc.iloc[:20].items():rows.append({'value':None if pd.isna(val) else str(val),'is_missing':bool(pd.isna(val)),'n':int(k),'pct_of_all_rows':float(k/n*100)})
        result['categorical'].append({'field':c,'denominator':n,'top':rows,'remaining_n':int(vc.iloc[20:].sum()),'complete_frequency_total':int(vc.sum())})
    if d.group:
        for val,g in f.groupby(d.group,dropna=False,sort=False):
            for c in d.numeric:
                v=g[c].replace([np.inf,-np.inf],np.nan);result['grouped'].append({'group_value':None if pd.isna(val) else str(val),'field':c,'rows':len(g),'finite_n':int(v.notna().sum()),'mean':v.mean() if v.notna().any() else None,'median':v.median() if v.notna().any() else None,'std_ddof1':v.std(ddof=1) if v.notna().sum()>1 else None})
    if d.date:
        dates=pd.to_datetime(f[d.date],errors='coerce');valid=dates.notna();result['date_quality']={'field':d.date,'unusable_rows':int((~valid).sum()),'frequency':d.frequency,'rule':'按输入日期直接分期，未补缺期、未补零；数值按有效值均值汇总'}
        period=dates[valid].dt.to_period(d.frequency).astype(str)
        for label,idx in period.groupby(period).groups.items():
            for c in d.numeric:
                v=f.loc[idx,c].replace([np.inf,-np.inf],np.nan);result['trend'].append({'period':label,'field':c,'rows':len(idx),'finite_n':int(v.notna().sum()),'mean':v.mean()})
    if d.method=='correlation':
        for i,a in enumerate(d.numeric):
            for b in d.numeric[i+1:]:
                pair=f[[a,b]].replace([np.inf,-np.inf],np.nan).dropna();ok=len(pair)>=3 and pair[a].nunique()>1 and pair[b].nunique()>1
                result['correlations'].append({'x':a,'y':b,'pairwise_n':len(pair),'pearson':float(stats.pearsonr(pair[a],pair[b]).statistic) if ok else None,'spearman':float(stats.spearmanr(pair[a],pair[b]).statistic) if ok else None,'status':'available' if ok else '样本不足或常量字段，未计算','p_values':'未生成；探索性描述不自动假设行独立或进行多重显著性筛选'})
    return result

def linear_association(f,d):
    fields=list(dict.fromkeys([d.outcome,*d.predictors,*([d.cluster] if d.covariance=='cluster' and d.cluster else []),*([d.date] if d.covariance=='HAC' and d.date else [])]));part=f[fields].copy()
    if d.covariance in ('HC3','HC0') and not d.independent_rows_reviewed:raise DesignError('HC3不能修复重复实体/时间相关，请确认行独立或选择适当聚类/HAC。')
    if d.covariance=='cluster' and not d.cluster:raise DesignError('聚类协方差需要聚类字段。')
    if d.covariance=='HAC' and not d.date:raise DesignError('HAC需要可排序、唯一的时间字段及明确滞后阶数。')
    for c in [d.outcome,*d.predictors]:
        if pd.api.types.is_numeric_dtype(part[c]) and np.isinf(part[c].dropna().astype(float)).any():raise DesignError('回归分析字段含无穷值。')
    valid=part.notna().all(axis=1);excluded=int((~valid).sum())
    if excluded and not d.allow_complete_case:raise DesignError('回归必要字段有缺失；请明确完整案例规则。')
    part=part.loc[valid].copy()
    if d.covariance=='HAC':
        t=pd.to_datetime(part[d.date],errors='coerce')
        if t.isna().any() or t.duplicated().any():raise DesignError('HAC时间字段必须可解析且每期一行。')
        part=part.assign(__sort_time=t).sort_values('__sort_time')
        if len(part)<=d.maxlags+5:raise DesignError('HAC样本不足以使用当前滞后阶数。')
    x=part[d.predictors].copy();categorical=[c for c in x if not pd.api.types.is_numeric_dtype(x[c])]
    if any(x[c].nunique()>30 or x[c].nunique()<2 for c in categorical):raise DesignError('分类自变量须有2至30个有效水平。')
    x=pd.get_dummies(x,columns=categorical,drop_first=True,dtype=float).astype(float);x=sm.add_constant(x,has_constant='add')
    if not np.isfinite(x.to_numpy()).all() or np.linalg.matrix_rank(x)!=x.shape[1]:raise DesignError('设计矩阵含非有限值或不满秩，不能静默使用伪逆掩盖共线性。')
    if len(part)<max(12,x.shape[1]+5):raise DesignError('样本不足以支持当前回归维度。')
    kwargs={'cov_type':d.covariance}
    if d.covariance=='cluster':
        groups=part[d.cluster]
        if groups.nunique()<20:raise DesignError('首版聚类回归要求至少20个聚类；少聚类需另外设计推断。')
        kwargs['cov_kwds']={'groups':groups,'use_correction':True}
    elif d.covariance=='HAC':kwargs['cov_kwds']={'maxlags':d.maxlags,'use_correction':True}
    model=sm.OLS(part[d.outcome].astype(float),x).fit(**kwargs)
    if not np.isfinite(model.bse).all() or (model.bse<=0).any() or np.var(model.resid)<=1e-20:raise DesignError('标准误或残差变异不足，未输出看似确定的显著结果。')
    ci=model.conf_int();return {'n':int(model.nobs),'excluded_complete_case_rows':excluded,'covariance':d.covariance,'maxlags':d.maxlags if d.covariance=='HAC' else None,'r_squared_in_sample':float(model.rsquared),'coefficients':[{'term':str(term),'coefficient':float(model.params[term]),'standard_error':float(model.bse[term]),'ci95_low':float(ci.loc[term,0]),'ci95_high':float(ci.loc[term,1]),'p_value':float(model.pvalues[term])} for term in x.columns],'condition_number':float(model.condition_number),'categorical_encoding':'reference-cell one-hot; sorted library levels','note':'条件线性关联；R²为样本内拟合度，不是样本外预测性能，显著性不是因果或业务提升。'}

def compute(frame,d):
    f=validate_frame(frame,d);summary=describe(f,d)
    bundle={'run_id':uuid.uuid4().hex,'created_at':datetime.now(timezone.utc).isoformat(),'method':d.method,'claim_level':'associational' if d.method in ('correlation','ols','logit','poisson') else 'descriptive','design':d.model_dump(mode='json'),'data_fingerprint':_data_fingerprint(frame),'summary':summary,'regression':(linear_association(f,d) if d.method=='ols' else __import__('causalops.general.glm',fromlist=['generalized_association']).generalized_association(f,d)) if d.method in ('ols','logit','poisson') else None,'runtime':{'python':platform.python_version(),**{x:md.version(x) for x in ['pandas','numpy','scipy','statsmodels']}},'sources':['https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.describe.html','https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html','https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html','https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.html'],'warnings':['数值统计只使用有限有效值，并分别记录缺失和无穷值；IQR标记不删除数据。','分类比例的分母为全表行数，缺失单独记录；分组按有效值汇总，不默认等权总体外推。','描述与相关不能识别因果；未测量实际收益或平台上线提效。']}
    bundle=clean_json(bundle);bundle['conclusions']=conclusions(bundle);return bundle

def conclusions(b):
    s=b['summary'];lines=[f"本表包含{s['row_count']:,}行、{s['column_count']}列；发现{s['exact_duplicate_rows']}行完全重复记录，未自动删除。"]
    if b['method'] == 'correlation' and len(s['correlations']) == 1:
        pair = s['correlations'][0]
        names = f"{pair['x']} 与 {pair['y']}"
        if pair['pearson'] is None or pair['spearman'] is None:
            lines.append(f"{names}：{pair['pairwise_n']} 对有效观测，样本不足或变量为常量，未计算相关系数。")
        else:
            lines.append(f"{names}：成对有效样本 {pair['pairwise_n']}，Pearson 系数 {pair['pearson']:.4g}，Spearman 系数 {pair['spearman']:.4g}。系数描述样本内关联。")
    for row in s['numeric'][:5]:
        if row['finite_n']:lines.append(f"{row['field']}：有效数{row['finite_n']}，均值{row['mean']:.4g}，中位数{row['median']:.4g}，缺失{row['missing_n']}，无穷值{row['infinite_n']}。")
        else:lines.append(f"{row['field']}没有有限有效值，未补写均值或中位数。")
    if b['method']=='correlation':lines.append('相关系数按各变量对的完整有限观测计算，样本数可能不同；未自动筛选显著结果或进行因果解释。')
    if b['regression']:lines.append(f"关联模型纳入{b['regression']['n']}行，协方差使用{b['regression']['covariance']}；系数用于条件关联解释，不代表干预收益。")
    lines.append('建议先核对缺失、字段单位、重复记录含义及观察窗口，再决定分组比较或正式研究设计。');return lines

class ExplorationWorkspace:
    def __init__(self,ws:GeneralWorkspace):
        self.ws=ws
        with ws.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS exploration_designs(study_id TEXT,version INTEGER,upload_id TEXT,design_json TEXT,created_at TEXT,PRIMARY KEY(study_id,version))')
            c.execute('CREATE TABLE IF NOT EXISTS exploration_runs(run_id TEXT PRIMARY KEY,study_id TEXT,version INTEGER,path TEXT,sha TEXT,created_at TEXT)')
    def studies(self,method):
        with self.ws.connection() as c:rows=c.execute('SELECT study_id,version,upload_id,design_json FROM exploration_designs ORDER BY rowid DESC').fetchall()
        seen=set();out=[]
        for sid,v,uid,text in rows:
            if sid not in seen:
                seen.add(sid);d=ExplorationDesign.model_validate_json(text)
                if d.method==method:out.append({'study_id':sid,'version':v,'upload_id':uid,'design':d})
        return out
    def save(self,uid,d,study_id=None):
        validate_frame(self.ws.load_upload(uid),d);sid=study_id or uuid.uuid4().hex;text=d.model_dump_json()
        with self.ws.connection() as c:
            row=c.execute('SELECT version,upload_id,design_json FROM exploration_designs WHERE study_id=? ORDER BY version DESC LIMIT 1',(sid,)).fetchone()
            if row and row[1]!=uid:raise DesignError('请为另一个上传文件新建分析。')
            if row and row[2]==text:return sid,row[0]
            v=row[0]+1 if row else 1;c.execute('INSERT INTO exploration_designs VALUES(?,?,?,?,?)',(sid,v,uid,text,datetime.now(timezone.utc).isoformat()))
        return sid,v
    def run(self,sid,version,*,run_id=None):
        if run_id:
            import re
            if not re.fullmatch(r"[a-f0-9]{32}",run_id):raise DesignError("运行标识格式无效。")
            with self.ws.connection() as c:exists=c.execute("SELECT 1 FROM exploration_runs WHERE run_id=?",(run_id,)).fetchone()
            if exists:
                b=self.load(run_id)
                if b["study_id"]!=sid or b["design_version"]!=version:raise DesignError("运行标识与研究版本不一致。")
                return b
        with self.ws.connection() as c:row=c.execute('SELECT upload_id,design_json,version FROM exploration_designs WHERE study_id=? ORDER BY version DESC LIMIT 1',(sid,)).fetchone()
        if not row or row[2]!=version:raise DesignError('分析配置已变化，请核对最新保存版本。')
        b=compute(self.ws.load_upload(row[0]),ExplorationDesign.model_validate_json(row[1]));b.update(study_id=sid,design_version=version,upload_id=row[0],external_model_calls=0)
        if run_id:b['run_id']=run_id
        base=self.ws.root/'exploration-runs'/sid;base.mkdir(parents=True,exist_ok=True);p=base/(b['run_id']+'.json');text=json.dumps(b,ensure_ascii=False,indent=2,allow_nan=False)
        temp=p.with_suffix('.pending');temp.write_text(text,encoding='utf-8');temp.replace(p)
        with self.ws.connection() as c:c.execute('INSERT INTO exploration_runs VALUES(?,?,?,?,?,?)',(b['run_id'],sid,version,str(p.relative_to(self.ws.root)),hashlib.sha256(p.read_bytes()).hexdigest(),b['created_at']))
        return b
    def runs(self,sid):
        with self.ws.connection() as c:return [x[0] for x in c.execute('SELECT run_id FROM exploration_runs WHERE study_id=? ORDER BY rowid DESC',(sid,))]
    def load(self,run_id):
        with self.ws.connection() as c:r=c.execute('SELECT path,sha,study_id,version FROM exploration_runs WHERE run_id=?',(run_id,)).fetchone()
        if not r:raise DesignError('运行不存在。')
        p=(self.ws.root/r[0]).resolve()
        if not p.is_relative_to(self.ws.root/'exploration-runs') or hashlib.sha256(p.read_bytes()).hexdigest()!=r[1]:raise DesignError('运行路径或文件哈希不一致。')
        b=json.loads(p.read_text(encoding='utf-8'))
        if b['run_id']!=run_id or b['study_id']!=r[2] or b['design_version']!=r[3]:raise DesignError('运行和配置版本不一致。')
        with self.ws.connection() as c:design=c.execute('SELECT upload_id,design_json FROM exploration_designs WHERE study_id=? AND version=?',(r[2],r[3])).fetchone()
        if not design or design[0]!=b['upload_id'] or json.loads(design[1])!=b['design']:raise DesignError('保存配置与运行证据不一致。')
        if b['data_fingerprint']!=_data_fingerprint(self.ws.load_upload(b['upload_id'])):raise DesignError('上传数据与运行指纹不一致。')
        return b