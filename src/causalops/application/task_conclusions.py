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
    facts,refs=a.facts(sid,run_ids=[rid]);ref=refs[0];dictionary,contract_ref=source_dictionary(a,sid,rid);evidence=[]
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
        elif b['method']=='correlation' and summary['correlations']:
            row=summary['correlations'][0];cite('summary.correlations[0].pearson');cite('summary.correlations[0].pairwise_n')
            sections['magnitude']=row['x']+'与'+row['y']+'的成对有效样本为'+str(row['pairwise_n'])+'，Pearson相关系数为'+(fmt(row['pearson']) if row['pearson'] is not None else '未计算')+'。';sections['meaning']='相关描述共同变化，不能确认方向、排除共同原因或解释为干预收益。'
    body={'version':'task_conclusion_v1','run_id':rid,'data_fingerprint':ref['contract']['data_fingerprint'] if ref.get('contract') else a.tools.envelope(a.session(sid)['upload_id'],ref).data_fingerprint,'contract_ref':contract_ref,'claim':claim,'sections':sections,'evidence':evidence,'source':'saved_run_deterministic_interpretation','no_reestimate':True}
    body['sha256']=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest();return body

def attach_task_conclusion(report,value):
    parts=['<section data-causalops-task-conclusion="1"><h2>研究问题的结论与下一步</h2><p>以下解释对应保存运行，未新增估计。运行编号：'+escape(value['run_id'])+'</p>']
    for k,v in value['sections'].items():parts.append('<h3>'+TITLES[k]+'</h3><p>'+escape(v)+'</p>')
    parts.append('<details><summary>核对本节引用的运行证据</summary><pre>'+escape(json.dumps(value['evidence'],ensure_ascii=False,indent=2))+'</pre></details></section>')
    marker='</body>' if '</body>' in report else '</html>'
    return report.replace(marker,''.join(parts)+marker)
