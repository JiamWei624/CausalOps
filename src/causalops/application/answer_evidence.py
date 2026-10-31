"""Question-scoped evidence selection with a hard citation budget, not numerical generation."""
from __future__ import annotations
import re

def select_answer_facts(facts,runs,q,budget=8):
    # Distribute the fixed budget across explicitly selected runs, preserving comparison coverage.
    per=max(1,budget//max(1,len(runs)));selected=[]
    sample=bool(re.search('样本|行数|多少条|多少人',q));correlation=bool(re.search('相关|correlation|pearson|spearman',q,re.I))
    for run in runs:
        candidates=[(k,v) for k,v in facts.items() if v['run_id']==run['run_id']]
        def score(item):
            key,f=item;p=f['path'];text=f['text'];s=0
            if p=='summary.row_count' or p=='regression.n' or p=='/estimate/sample_size':s+=90 if sample else 25
            if '/estimate/' in p:s+=60
            if p.endswith('.coefficient') or p.endswith('.exp_coefficient'):s+=65
            if p.endswith('.ci95_low') or p.endswith('.ci95_high'):s+=5
            if p.endswith('.ci95') or p.endswith('.exp_ci95'):s+=55
            if run.get('method') in ('logit','poisson'):
                if p.endswith('.coefficient'):s-=55
                if p.endswith('.ci95') and any(x['path']==p[:-5]+'.exp_ci95' for _,x in candidates):s-=50
            if '.coefficients[0]' in p and text.startswith('const'):s-=200
            if '.correlations' in p:s+=80 if correlation else 30
            if p.endswith('.pairwise_n') and sample:s+=80
            if p.endswith('.mean'):s+=10
            if 'relative_change_pct' in p or 'scaled_per_1000' in p or 'control_mean' in p:s+=50
            # Requested field names outrank background summaries; never rank by significance.
            field=text.split(' / ')[0]
            if len(field)>1 and field.lower() in q.lower():s+=45
            return -s
        candidates=sorted(candidates,key=score)
        selected.extend(candidates[:per])
    return selected[:budget]

def result_rules(a,sid,runs):
    from causalops.application.task_conclusions import source_dictionary
    result=[]
    for run in runs:
        dictionary,ref=source_dictionary(a,sid,run['run_id'])
        result.append({'run_id':run['run_id'],'method':run['method'],'dictionary_ref':ref,'metric':{k:dictionary[k] for k in ('metric_label','metric_unit','metric_kind','metric_window') if dictionary.get(k)},'source_roles':{k:dictionary[k] for k in ('analysis_unit','entity','outcome','treatment','time','treatment_time','predictors','covariates') if dictionary.get(k)},'reading_rules':['按本运行来源计划解释，不能使用新字典改写旧结果','关联不等于干预效果；OR不等于概率比或百分点','没有成本和业务阈值，不报告利润、ROI或直接推广建议','所有正文数字只能引用本轮提供的事实；不重跑、不批准']})
        if run['kind']=='research':
            bundle,_=a.ws.bundle(run['run_id'])
            result[-1]['actual_claim']=bundle.claim_level.value
            result[-1]['saved_diagnostics']=[{'name':d.name,'passed':d.passed,'claim_blocking':d.claim_blocking} for d in bundle.diagnostics]
            result[-1]['reading_rules'].append('saved_diagnostics是已实际执行的检查结果，优先说明失败且限制主张的检查；不得把失败写成尚未检查或已通过。p值数值舍入为零不是概率严格为零。')
    return result

def check_answer_semantics(text,selected,runs):
    """Conservative language checks supplement numeric references; not a proof of truth."""
    from causalops.general.service import DesignError
    plain=re.sub(r'\[\[[^\]]+\]\]','[运行证据]',text)
    neg=r'不能|不可|无法|不等于|不是|并非|不应|不得|未计算|尚未|没有|缺少|不足|不代表|未能|不要|假设|如果'
    rules=[]
    if any(r.get('method')=='logit' for r in runs):rules.append((r'(?:概率|购买率|转化率).{0,25}(?:增加|提高|下降|增长).{0,25}个百分点','本次Logit没有保存概率边际效应，不能把OR写成概率百分点变化。'))
    if any(f['claim'] in ('associational','descriptive') for _,f in selected):rules.append((r'导致|使得|带来.{0,12}(?:增长|提升|改善)|因果效应(?:为|等于)','本次仅有描述或关联证据，不能写成已识别的干预效果。'))
    rules.append((r'(?:利润|ROI|投资回报).{0,20}(?:增加|提高|达到|为\[运行证据\])','本轮没有成本与利润运行证据，不能补写ROI或利润提升。'))
    for pattern,message in rules:
        for match in re.finditer(pattern,plain,re.I):
            context=plain[max(0,match.start()-22):min(len(plain),match.end()+8)]
            if not re.search(neg,context):raise DesignError(message)


def prepare_result_payload(payload):
    """Only current run facts supply numerical results; keep source plan roles, not draft prose."""
    p={**payload};dataset=p.get('dataset',{})
    p['dataset']={'fields':[{'field':f['field'],'dtype':f['dtype'],'numeric':f['numeric']} for f in dataset.get('fields',[])],'meaning':'样本量、分布和估计值只依据本轮fact_catalog；此处仅提供结构。'}
    c={**p.get('research_context',{})};plans=[]
    for v in c.get('source_plans',[]):
        plan=v.get('plan',{});plans.append({**{k:v[k] for k in ('version','sha','state') if k in v},'plan':{'objective':plan.get('objective'),'steps':[{'tool':x['tool'],'config':{k:value for k,value in x['config'].items() if k!='question'}} for x in plan.get('steps',[])]}})
    c.update(source_plans=plans,plan_questions_at_creation=[],unresolved_items=[],recent_scoped_answer_refs=[])
    c['context_rule']='本轮已执行设计与registered_facts优先于候选阶段的问题清单。人工已登记不等于假设被证明；不得反过来声称已登记的字段/事实不存在。数值只引用本轮fact_catalog。'
    p['research_context']=c
    return p
