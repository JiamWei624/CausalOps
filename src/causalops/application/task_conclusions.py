"""Run-bound, deterministic explanation of magnitude and limits; no model computes values."""
from __future__ import annotations
from html import escape
import hashlib,json
from causalops.general.service import DesignError

TITLES={'baseline':'参考水平与分析范围','magnitude':'差异幅度与不确定性','meaning':'实际含义与解释边界','action':'建议采取的下一步'}

def source_dictionary(a,sid,rid):
    ref=next((r for r in a.completed_runs(sid) if r['run_id']==rid),None)
    if not ref:raise DesignError('结论不能引用其他任务运行。')
    with a.ws.connection() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_flows'").fetchone():return {},None
        row=c.execute('SELECT id FROM workflow_flows WHERE session_id=? AND plan_id=? ORDER BY rowid DESC LIMIT 1',(sid,ref['plan_id'])).fetchone()
    if not row:return {},None
    from causalops.application.research_service import ResearchService
    service=ResearchService(a);flow=service.flow(row[0]);contract=service.contracts.bound(flow)
    return (contract['body'],flow['request'].get('contract_ref')) if contract else ({},None)

def build_task_conclusion(a,sid,rid):
    facts,refs=a.facts(sid,run_ids=[rid]);ref=refs[0];dictionary,contract_ref=source_dictionary(a,sid,rid);evidence=[];focus=None
    def cite(path):
        for key,fact in facts.items():
            if fact['path']==path:
                if key not in {x['id'] for x in evidence}:evidence.append({'id':key,**fact})
                return
    fmt=lambda v:format(v,'.4g')
    if ref['kind']!='exploration':
        if ref['kind']=='research':
            from causalops.results.interpretation import interpret_run
            b,_=a.ws.bundle(rid);x=interpret_run(b);t=x['texts']
            sections={'baseline':t['baseline'],'magnitude':t['magnitude']+' '+t['relative'],'meaning':t['scale']+' '+t['meaning']+' '+t['boundary'],'action':t['action']+' '+t['cost']}
            for key,fact in list(facts.items())[:8]:evidence.append({'id':key,**fact})
            claim=b.claim_level.value
        else:
            b=a.advanced.load(rid);claim=b['claim'];sections={'baseline':'本次扩展研究的参考范围仅为保存的分析样本。','magnitude':'估计差异为'+fmt(b['estimate'])+'；置信区间为'+str(b['ci95'])+'。','meaning':'解释范围为'+claim+'；工具、阈值或处理时点的设计要求不能由显著性替代。','action':'先核对本方法诊断与局部适用范围，再讨论外推和成本。'}
            for key,fact in list(facts.items())[:8]:evidence.append({'id':key,**fact})
    else:
        b=a.ex.load(rid);claim=b['claim_level'];reg=b['regression'];summary=b['summary'];cite('summary.row_count');fieldinfo={f['field']:f for f in dictionary.get('fields',[])};n=summary['row_count']
        sections={'baseline':'当前表共'+format(n,',')+'行；不自动把原始均值当作干预前基线。','magnitude':'本次仅报告已保存的分布与有效值统计，不估计干预效应。','meaning':'结果描述当前样本；不能据此证明产品、营销或政策带来了增长。','action':'先核对缺失、重复的业务含义、指标单位和观察窗口，再确定是否需要新的分析。'}
        if reg:
            predictors=b['design']['predictors'];index=next((i for i,v in enumerate(reg['coefficients']) if v['term'] in predictors and v['term']!='const'),None)
            if index is not None:
                cite('regression.n')
                row=reg['coefficients'][index];term=row['term'];outcome=b['design']['outcome'];xinfo=fieldinfo.get(term,{});yinfo=fieldinfo.get(outcome,{});unit=xinfo.get('unit') or '原始输入单位';outunit=yinfo.get('unit') or '结果原始单位'
                sections['baseline']='当前关联模型纳入'+format(reg['n'],',')+'行，结果为'+outcome+'；观察窗口和变量单位以该运行创建时的登记为准。'
                for key in ('coefficient','ci95_low','ci95_high'):cite('regression.coefficients['+str(index)+'].'+key)
                lo,hi=row['ci95_low'],row['ci95_high'];beta=row['coefficient']
                if b['method']=='ols':
                    sections['magnitude']='保持其余已列自变量不变时，'+term+'每增加1'+unit+'，'+outcome+'的条件均值相差'+fmt(beta)+outunit+'；95%置信区间为['+fmt(lo)+', '+fmt(hi)+']'+outunit+'。'
                    sections['meaning']='这是条件线性关联，不是改变'+term+'后能够保证获得的收益。区间'+('包含零，当前证据不足以确定差异方向。' if lo<=0<=hi else '未包含零，但仍不能把统计显著解释为重要业务收益。')
                else:
                    ratio=row.get('exp_coefficient');cite('regression.coefficients['+str(index)+'].exp_coefficient')
                    sections['magnitude']=term+'每增加1'+unit+'时，'+('购买等二元结果的条件优势比OR为' if b['method']=='logit' else '等暴露条件下的计数均值比为')+(fmt(ratio) if ratio is not None else '无法安全报告')+'；对应系数的95%置信区间为['+fmt(lo)+', '+fmt(hi)+']。'
                    sections['meaning']='优势比不是概率比，也不是增加多少个百分点。没有保存的概率边际效应，不能补写转化率提升。' if b['method']=='logit' else '这是条件计数关联，要求暴露口径可比；不代表投放或产品干预造成的增长。'
                sections['action']='先结合变量量纲、测量时点、单位独立性及业务可行动性检查解释；若要回答干预收益，应另行设计可识别的实验或准实验，不能直接推广此系数。'
        elif b['method']=='descriptive':
            cite('summary.column_count');cite('summary.exact_duplicate_rows')
            sections['baseline']='本次分析包含'+format(n,',')+'条记录、'+str(summary['column_count'])+'个字段；完全重复记录'+str(summary['exact_duplicate_rows'])+'条，未自动删除。'
            lines=[];target=dictionary.get('outcome');label=dictionary.get('metric_label') or target;unit=dictionary.get('metric_unit') or ''
            rows=list(enumerate(summary['numeric']))
            target_rows=[(i,v) for i,v in rows if v['field']==target]
            focus={'field':target,'label':label,'unit':unit,'available':False,'source':'source_run_contract','contract_ref':contract_ref} if target else None
            ordered=(target_rows+[(i,v) for i,v in rows if v['field']!=target]) if not target or target_rows else []
            for i,row in ordered[:1 if target_rows else 3]:
                if row['finite_n'] and row['mean'] is not None and row['median'] is not None:
                    for key in ('finite_n','mean','median','missing_n'):cite('summary.numeric['+str(i)+'].'+key)
                    if target_rows:
                        for key in ('min','max','q25','q75','infinite_n'):cite('summary.numeric['+str(i)+'].'+key)
                        lines.append(str(label)+'（'+str(target)+'）：有效观测'+str(row['finite_n'])+'条，均值'+fmt(row['mean'])+unit+'，中位数'+fmt(row['median'])+unit+'，观测范围'+fmt(row['min'])+'至'+fmt(row['max'])+unit+'；缺失'+str(row['missing_n'])+'条，无穷值'+str(row['infinite_n'])+'条')
                        if row['min']>=0 and row['max']<=1 and row['zero_n']+round(row['mean']*row['finite_n'])==row['finite_n'] and any(h['field']==target and h.get('value_type')=='discrete' and set(h.get('values',[]))<= {0.,1.} for h in summary['histograms']):
                            lines[-1]=str(label)+'（'+str(target)+'）：取值为1的记录占'+str(row['finite_n'])+'条有限有效记录的'+fmt(row['mean']*100)+'%；缺失'+str(row['missing_n'])+'条，无穷值'+str(row['infinite_n'])+'条。该比例不表示相对基线提升，1的业务含义以字段说明为准'
                        focus['available']=True
                    else:lines.append(row['field']+'：有效观测'+str(row['finite_n'])+'条，均值'+fmt(row['mean'])+'，中位数'+fmt(row['median'])+'，缺失'+str(row['missing_n'])+'条')
                elif target_rows:
                    for key in ('finite_n','missing_n','infinite_n'):cite('summary.numeric['+str(i)+'].'+key)
                    lines.append(str(label)+'没有有限有效值，不能报告其均值或中位数；缺失'+str(row['missing_n'])+'条，无穷值'+str(row['infinite_n'])+'条')
            if target and not target_rows:
                # Do not substitute another metric when the frozen target was not computed.
                lines=[]
                category=next(((i,v) for i,v in enumerate(summary['categorical']) if v['field']==target),None)
                if category:
                    i,row=category;valid=[(j,v) for j,v in enumerate(row['top']) if not v['is_missing']]
                    if valid:
                        j,value=valid[0];category_label=str(value['value'])[:60];missing=next((v['missing'] for v in summary['columns'] if v['field']==target),0);lines=[str(label)+'为分类字段；类别“'+category_label+'”有'+str(value['n'])+'条，占全部'+str(row['denominator'])+'条记录的'+fmt(value['pct_of_all_rows'])+'%；该字段缺失'+str(missing)+'条。未把类别编码当作连续指标计算均值。'];focus['available']=True
                        path='summary.categorical['+str(i)+'].top['+str(j)+'].pct_of_all_rows'
                        # Categorical labels may identify people: cite only the stored aggregate share.
                        cite(path)
                if not lines:lines=['本次保存结果未形成目标指标 '+str(target)+' 的有效汇总。请检查所选字段与计划；不能用其他字段的均值代替其结果。']
            if not lines:
                for i,row in enumerate(summary['categorical'][:3]):
                    if row['top']:
                        lines.append(row['field']+'最高频类别占全部记录的'+fmt(row['top'][0]['pct_of_all_rows'])+'%')
            sections['magnitude']='；'.join(lines)+('。优先解释创建本次运行时已确认的目标指标，其他统计见明细。' if target else '。未指定目标指标，以上按原字段顺序展示，完整统计见明细。') if lines else '所选字段未形成有效的汇总，未补写均值或中位数。'
            sections['meaning']=('本次回答“'+str(label)+'在当前样本中是什么水平、如何分布”。' if target else '')+'结果仅描述当前样本。均值不代表每条记录的取值，最小值和最大值不是置信区间；指标解释依赖其测量尺度。当前没有估计干预效果，不能据此解释为改动某项措施后必然提升。'
            sections['action']=('围绕 '+str(label)+' 检查缺失、重复记录与量纲；如需研究相关因素，应先明确比较字段、观察单位与测量口径，再制定新的关联分析计划。' if target else '先确认关心的指标及分析单位，再根据具体目标开展比较或关联分析。')
        elif b['method']=='correlation' and summary['correlations']:
            target=dictionary.get('outcome');eligible=[(i,v) for i,v in enumerate(summary['correlations']) if not target or target in (v['x'],v['y'])]
            if eligible:
                idx,row=eligible[0];cite('summary.correlations['+str(idx)+'].pearson');cite('summary.correlations['+str(idx)+'].spearman');cite('summary.correlations['+str(idx)+'].pairwise_n')
                sections['magnitude']=row['x']+'与'+row['y']+'的成对有效样本为'+str(row['pairwise_n'])+'，Pearson相关系数为'+(fmt(row['pearson']) if row['pearson'] is not None else '未计算')+'，Spearman系数为'+(fmt(row['spearman']) if row['spearman'] is not None else '未计算')+'。优先报告保存顺序中首个涉及目标的变量对，不按显著性挑选。'
            else:sections['magnitude']='本次相关矩阵未包含已登记的目标指标，不能将其他变量对替代目标结果。'
            sections['meaning']='系数描述变量共同变化，不表示改动某变量后能提高多少结果。相关矩阵中的各变量对可能使用不同有效样本。'
            sections['action']='结合字段含义、异常值、时间顺序和散点分布核查；若要研究干预收益，需要新的研究设计。'
            focus={'field':target,'label':dictionary.get('metric_label') or target,'unit':dictionary.get('metric_unit') or '', 'available':bool(eligible),'source':'source_run_contract','contract_ref':contract_ref} if target else None
    body={'version':'task_conclusion_v3','run_id':rid,'data_fingerprint':ref['contract']['data_fingerprint'] if ref.get('contract') else a.tools.envelope(a.session(sid)['upload_id'],ref).data_fingerprint,'contract_ref':contract_ref,'claim':claim,'sections':sections,'evidence':evidence,'source':'saved_run_deterministic_interpretation','no_reestimate':True,'focus':focus}
    if ref['kind']=='exploration' and b['method']=='descriptive':body['titles']={'baseline':'样本范围与数据质量','magnitude':'主要统计结果','meaning':'结果解释','action':'后续分析建议'}
    body['sha256']=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest();return body

def attach_task_conclusion(report,value):
    parts=['<section data-causalops-task-conclusion="1"><h2>研究问题的结论与下一步</h2><p>以下解释对应保存运行，未新增估计。运行编号：'+escape(value['run_id'])+'</p>']
    for k,v in value['sections'].items():parts.append('<h3>'+escape(value.get('titles',TITLES)[k])+'</h3><p>'+escape(v)+'</p>')
    parts.append('<details><summary>核对本节引用的运行证据</summary><pre>'+escape(json.dumps(value['evidence'],ensure_ascii=False,indent=2))+'</pre></details></section>')
    if '</h1>' in report:return report.replace('</h1>','</h1>'+''.join(parts),1)
    marker='</body>' if '</body>' in report else '</html>'
    return report.replace(marker,''.join(parts)+marker)
