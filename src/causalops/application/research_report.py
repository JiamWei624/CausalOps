"""Research appendix generated exclusively from saved run and its bound contract."""
from html import escape
import json
from causalops.application.research_quality import research_brief,method_contract

def run_quality(a,sid,rid):
    from causalops.application.task_conclusions import source_dictionary
    dictionary,contract=source_dictionary(a,sid,rid)
    ref=next(v for v in a.completed_runs(sid) if v['run_id']==rid)
    plan=a.get_plan(ref['plan_id']) if ref.get('plan_id') else None
    question=plan['plan']['objective'] if plan else ''
    brief=research_brief(dictionary,question=question)
    method=method_contract(ref['method'])
    configurations=[v['config'] for v in (plan['plan']['steps'] if plan else []) if v['config']['method']==ref['method']]
    sample={};warnings=[];diagnostics=[]
    if ref['kind']=='exploration':
        b=a.ex.load(rid);sample={'导入记录':b['summary']['row_count']}
        if b.get('regression'):sample['回归纳入记录']=b['regression']['n']
        else:sample['统计口径']='各字段/变量对有效样本分别统计，详见结果明细；没有统一的完整案例样本数。'
        warnings=b.get('warnings',[])
    elif ref['kind']=='research':
        b,_=a.ws.bundle(rid);sample={'最终估计样本':b.estimate.sample_size} if b.estimate else {}
        diagnostics=[v.model_dump(mode='json') for v in b.diagnostics];warnings=b.warnings
    else:
        b=a.advanced.load(rid);sample={label:b[key] for label,key in [('输入记录','input_rows'),('最终估计记录','analysis_rows'),('排除记录','excluded_rows'),('阈值两侧有效样本','effective_n')] if key in b}
        warnings=b.get('warnings',[]);diagnostics=b.get('diagnostics',[])
    issues=[d.get('message') or d.get('note') or d.get('name','诊断待确认') for d in diagnostics if d.get('passed') is False or d.get('status') in ('failed','blocked','needs_review')]
    return {'version':'research_appendix_v1','run_id':rid,'contract_ref':contract,'brief':brief,'method':method,'sample_flow':sample,'saved_configurations':configurations,'warnings':warnings,'failed_diagnostics':issues,'source':'saved_run_and_bound_contract','reestimate':False,'next_steps':result_next_steps(ref['method'],issues,brief)}

def append_quality(report,value):
    b=value['brief'];m=value['method']
    parts=['<section data-research-quality="1"><h2>研究范围、计算依据与待解决问题</h2>']
    for label,key in [('研究问题','question'),('适用对象','population'),('纳入与排除说明','inclusion'),('比较对象','comparison'),('观察期间','window'),('数据来源','source'),('决策用途','decision')]:parts.append('<p><b>'+label+'：</b>'+escape(str(b[key]))+'</p>')
    parts.append('<h3>实际计算及样本范围</h3><p>'+escape(m['label']+'；'+m['estimand']+'；'+m['population'])+'</p>')
    for k,v in value['sample_flow'].items():parts.append('<p>'+escape(k)+'：'+escape(str(v))+'</p>')
    parts.append('<h3>尚缺少什么</h3><p>'+escape(b['limitations'])+'</p><p>'+escape(m['limits'])+'</p>')
    for item in value['warnings']+value['failed_diagnostics']:parts.append('<p>'+escape(str(item))+'</p>')
    parts.append('<h3>建议的下一步</h3>')
    for item in value['next_steps']:parts.append('<p>'+escape(item)+'</p>')
    parts.append('<details><summary>保存的计算设置（不是重新推断的参数）</summary><pre>'+escape(json.dumps(value.get('saved_configurations',[]),ensure_ascii=False,indent=2))+'</pre></details>')
    parts.append('<details><summary>方法来源与版本</summary>')
    for src in m['sources']:parts.append('<p><a href="'+escape(src['url'],quote=True)+'">'+escape(src['title'])+'</a> · '+escape(src['access_scope'])+'</p>')
    parts.append('<p>运行：'+escape(value['run_id'])+'；口径版本：'+escape(str((value['contract_ref'] or {}).get('version','未绑定')))+'；知识库：'+escape(m['knowledge_sha256'])+'</p></details></section>')
    return report.replace('</body>',''.join(parts)+'</body>') if '</body>' in report else report+''.join(parts)


def result_next_steps(method,failed,brief):
    """Run-specific advice; never choose a model by significance or authorize reruns."""
    steps=[]
    if failed:
        steps.append('先处理本次未通过的诊断：'+'；'.join(str(x) for x in failed[:2])+'。核对设计、数据口径及该方法的适用条件；不要通过反复换方法追求显著。')
    if method=='psm':
        steps.append('报告匹配保留与排除的处理样本，并比较匹配前后平衡；当前条件配对标准误未计入全部匹配不确定性，确认性结论需要额外推断方案。')
    elif method in ('did','staggered_did'):
        steps.append('结合处理前趋势、对照定义与处理时点解释结果。未拒绝前趋势不能证明平行趋势；调整窗口或估计器应建立新计划。')
    elif method in ('descriptive','correlation','ols','logit','poisson','regression_adjustment'):
        steps.append('将结果限定为当前样本的分布或关联；若要研究干预效果，先补充分配机制、比较对象和时间依据，再制定新设计。')
    else:
        steps.append('核对实际估计对象、样本范围与方法诊断；敏感性分析需形成单独待审计划，不覆盖本次记录。')
    steps.append('对照已登记的决策用途和业务阈值判断实际意义；没有成本、收益或推广依据时，不推算整体业务收益。')
    return steps[:3]
