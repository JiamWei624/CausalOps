"""Pure reviews of explicitly exported run facts, without analysis or new causal claims."""
from __future__ import annotations
import math

def validate_fact_citations(exported,fact_ids):
    if not isinstance(fact_ids,list) or len(fact_ids)>20 or any(not isinstance(x,str) or len(x)>300 for x in fact_ids):raise ValueError('事实引用须为最多二十个完整事实标识。')
    allowed={f['id'] for f in exported.get('facts',[])}
    missing=sorted(set(fact_ids)-allowed)
    return {'run_id':exported['run_id'],'status':'valid' if exported['status']=='found' and not missing and bool(fact_ids) else 'invalid','missing_fact_ids':missing,'checked_count':len(fact_ids),'claim':'只检查引用归属，不检查自由文本结论是否正确；不验证识别假设。'}

def review_exported_evidence(exported):
    if exported.get('status')!='found':return {'run_id':exported['run_id'],'status':'not_exported','checks':[],'execution_performed':False,'assumptions_verified':False}
    facts=exported['facts'];rid=exported['run_id'];checks=[{'name':'facts_present','passed':bool(facts),'fact_ids':[],'note':'须有已导出的事实，不把空清单视为审阅通过。'}]
    wrong=[f['id'] for f in facts if f.get('run_id')!=rid]
    checks.append({'name':'run_scope','passed':not wrong,'fact_ids':wrong,'note':'核对事实是否属于所请求的运行。'})
    nonfinite=[];invalid_p=[];negative_se=[];reversed_ci=[]
    for f in facts:
        v=f['value'];path=f.get('path','').lower();values=v if isinstance(v,list) else [v]
        if any(isinstance(x,(int,float)) and not math.isfinite(x) for x in values):nonfinite.append(f['id'])
        if isinstance(v,(int,float)) and ('p_value' in path or 'pvalue' in path) and not 0<=v<=1:invalid_p.append(f['id'])
        if isinstance(v,(int,float)) and any(k in path for k in ('std_error','standard_error')) and v<0:negative_se.append(f['id'])
        if isinstance(v,list) and 'ci95' in path and len(v)==2 and all(isinstance(x,(int,float)) for x in v) and v[0]>v[1]:reversed_ci.append(f['id'])
    for name,ids,note in [('finite_values',nonfinite,'检查已导出的数值是否有限。'),('p_value_range',invalid_p,'检查已识别P值字段是否位于合法范围。'),('standard_error_nonnegative',negative_se,'检查已识别标准误字段是否非负。'),('interval_order',reversed_ci,'检查已识别区间字段的上下限顺序。')]:checks.append({'name':name,'passed':not ids,'fact_ids':ids,'note':note})
    claims=sorted({f.get('claim','unknown') for f in facts})
    return {'run_id':rid,'status':'reviewed','checks':checks,'fact_count':len(facts),'registered_claim_levels':claims,'all_machine_checks_passed':all(c['passed'] for c in checks),'execution_performed':False,'approval_performed':False,'assumptions_verified':False,'conclusion':'以上仅为已导出证据的一致性检查。通过不意味着模型选择正确、估计可作因果解释或自由文本结论已被验证。','limitations':['未重算统计量；未核验原始行或源数据。','未验证无混杂、排除限制、平行趋势等识别假设。','不能仅凭显著性或区间确定业务行动。']}
