"""Deliver numeric questions from the selected immutable evidence bundle."""
import re
from decimal import Decimal

from causalops.application.report_scope import unit_answer


def threshold_question(question, previous):
    """Resolve a pronoun from the previous same-run question, never from another study."""
    if not re.search(r'(?:阈值|基准|参考值|(?:与|比|和)\s*[+-]?\d|超过|高于|低于|大于|小于|等于)',question):
        return question
    if re.search(r'均值|平均|中位|mean|median',question,re.I):return question
    mean=bool(re.search(r'均值|平均|mean',previous,re.I))
    median=bool(re.search(r'中位|median',previous,re.I))
    if mean==median:return question
    return question+'（承接同一报告的'+('均值' if mean else '中位数')+'。）'


def saved_answer(facts, run, dictionary, question, *, bundle=None):
    rid = run['run_id']
    scoped = {key: f for key, f in facts.items() if f['run_id'] == rid}
    outcome = dictionary.get('outcome')
    window = dictionary.get('metric_window') or ''
    label = dictionary.get('metric_label') or outcome or ''
    unit = dictionary.get('metric_unit') or ''
    question=question.replace('−','-')
    # Displayed-page background is not a second target when the user explicitly returns to a named run.
    if rid in question:
        instruction=re.search(r'(?:请仍按|请仅按|请只按|仍以)(?:指定|所指|上述)?(?:旧|历史)?(?:运行|报告)',question)
        if instruction:
            question=question[instruction.start():]
    lower = question.lower()
    def response(text, items):
        return dict(source='本地已保存运行证据', text=text+' 来源：运行 '+rid+'。',
                    facts=[dict(id=k, **v) for k,v in items], citations=[])
    from causalops.application.metric_semantics import semantic_answer
    checked=semantic_answer(scoped,run,dictionary,question,bundle=bundle)
    if checked:return checked
    if re.search(r'每[台家户组].{0,18}(?:平均|均值)',question) and re.search('没有|缺少|未登记',question) and re.search('编号|标识|分组字段',question):
        return response('报告的均值按记录加权。重复观测使记录更多的实体权重更高；还需实体标识，先计算每个实体的均值，再对实体等权平均。',[])
    # Bind a requested statistic to a column in this report's dictionary, including secondary summaries.
    meta={v['field']:v for v in dictionary.get('fields',[]) if v.get('field')}
    mentioned={col for col,entry in meta.items() if
               (len(entry.get('meaning') or '')>=2 and entry['meaning'] in question)
               or re.search(r'(?<![a-zA-Z0-9_])'+re.escape(col)+r'(?![a-zA-Z0-9_])',question,re.I)}
    asks_stat=re.search(r'均值|平均值|平均水平|中位数|median|mean',question,re.I)
    if asks_stat and len(mentioned)>1:
        return response('请确认要读取哪个字段的统计量：'+'、'.join(sorted(mentioned))+'。',[])
    if asks_stat and len(mentioned)==1:
        field=next(iter(mentioned))
        unit=meta[field].get('unit') or (unit if field==outcome else '')
        dictionary={**dictionary,'outcome':field,'metric_unit':unit}
    question=re.sub(r'(?i)(?:运行(?:编号|标识|ID)?\s*[：:#]?\s*)?\b[a-f0-9]{32}\b','',question)
    from causalops.application.comparison import compare
    comparison=compare(scoped,run,dictionary,question)
    if comparison:
        if '百分点' in question and '相对' in question and any(k.endswith(':rate.pp') for k in scoped):
            rates=unit_answer(scoped,run,label,window,control=dictionary.get('control_label') or dictionary.get('control_value'),
                              treated=dictionary.get('treated_label') or dictionary.get('treated_value'))
            if rates:
                comparison['text']+=' '+rates['text']+' 各组事件率分别以本组总人数或观测数为分母。'
                comparison['facts']=list({v['id']:v for v in comparison['facts']+rates['facts']}.values())
        return comparison
    percentile=re.search(r'(?:第\s*(\d{1,3})\s*百分位|(?<![A-Za-z])P(\d{1,3})(?!\d))',question,re.I)
    if percentile and run.get('method')=='descriptive':
        rank=int(percentile[1] or percentile[2])
        statistic={0:'min',25:'q25',50:'median',75:'q75',100:'max'}.get(rank)
        col=next(iter(mentioned),outcome) if len(mentioned)<=1 else None
        items=[(k,v) for k,v in scoped.items() if statistic and v['text']==str(col)+' / '+statistic and v['value'] is not None]
        if len(items)!=1:return response(f'所选报告没有可直接引用的第{rank}百分位数（P{rank}）。其他四分位数或均值不能替代；若需要估算，应另行制定方案。',[])
        stat_unit=meta.get(col,{}).get('unit') or (unit if col==outcome else '')
        return response(f'{col} 的第{rank}百分位数为 {items[0][1]["value"]:.6g}{stat_unit}。',items)
    bounds=[]
    for key,pattern,title in [('min','最小|最短|最低|下界','最小值'),('max','最大|最长|最高|上界','最大值')]:
        if run.get('method')=='descriptive' and re.search(pattern,question) and not re.search('置信|理论|阈值',question):
            col=next(iter(mentioned),outcome) if len(mentioned)<=1 else None
            items=[(k,v) for k,v in scoped.items() if v['text']==str(col)+' / '+key and v['value'] is not None]
            if len(items)!=1:return response('该报告没有唯一对应的样本极值，请确认字段与所需统计量。',[])
            actual_unit=meta.get(col,{}).get('unit') or (unit if col==outcome else '')
            bounds.append((f"{title} {items[0][1]['value']:.6g}{actual_unit}",items[0]))
    if bounds and re.search('不确定|总体均值|总体平均|抽样误差',question):
        return response('样本实际观测范围：'+'，'.join(t for t,_ in bounds)+'。端点描述本批样本的跨度；总体均值的不确定性需用均值的标准误和相应置信区间表示，不能取这两个端点。',[v for _,v in bounds])
    if bounds:return response('所选报告的样本范围：'+'，'.join(t for t,_ in bounds)+'。',[v for _,v in bounds])
    if asks_stat and run.get('method')=='descriptive' and (len(mentioned)==1 and field!=outcome or '中位' in question or 'median' in lower):
        field=next(iter(mentioned),outcome)
        if not field:return response('请指定要读取中位数或均值的字段。',[])
        stat='median' if re.search('中位|median',question,re.I) else 'mean'
        values=[(k,v) for k,v in scoped.items() if v['text']==field+' / '+stat and v['path'].startswith('summary.numeric[')]
        if len(values)!=1 or values[0][1]['value'] is None:
            return response('所选报告未保存 '+field+' 的目标统计量，不能用其他指标的数值替代。',[])
        kind='中位数' if stat=='median' else '均值'
        return response(f"{meta.get(field,{}).get('meaning') or field}（{field}）的{kind}为 {values[0][1]['value']:.6g}{unit}。观察期：{window or '未登记'}。",values)
    if re.search(r'访问率|超标|两组.*比例|转化率|购买率|百分点|相对(?:变化|增长)|概率差|两组.*率|幅度|实际含义|区间|百分|[%％]',question):
        result = unit_answer(scoped,run,label,window,
                             control=dictionary.get('control_label') or dictionary.get('control_value'),
                             treated=dictionary.get('treated_label') or dictionary.get('treated_value'))
        if result:
            result['text'] += ' 来源：运行 '+rid+'。'
            return result
    if re.search(r'同向|反向|正向还是负向|相关报告|相关系数|相关程度|关联方向|相关方向|pearson|spearman|correlation coefficient',lower):
        pairs = {}
        for k,v in scoped.items():
            if v['path'].startswith('summary.correlations['):
                pair, stat = v['text'].rsplit(' / ',1)
                pairs.setdefault(pair,{})[stat]=(k,v)
        named = set(re.findall(r'[a-zA-Z_][a-zA-Z_0-9]*',lower)) - {'pearson','spearman','correlation','coefficient','and','vs','r'}
        matches=[p for p in pairs if all(n in [field.lower() for field in p.split(' 与 ')] for n in named)]
        if len(matches)!=1:
            return response('所选报告未能唯一定位所问变量对。请核对变量名称。',[])
        pair=matches[0]
        methods=[s for s in ('pearson','spearman') if s in lower] or ['pearson']
        used=[]; pieces=[]
        for method in methods:
            item=pairs[pair].get(method)
            if item and isinstance(item[1]['value'],(float,int)):
                used.append(item);value=item[1]['value']; direction='正相关' if value>0 else '负相关' if value<0 else '系数为零'
                pieces.append(f'{method.title()} 相关系数为 {value:.4f}（{direction}）')
        if not pieces:return response(f'{pair} 的所求相关系数在该运行中没有有效数值。',[])
        count=pairs[pair].get('pairwise_n')
        if count:used.append(count);pieces.append('成对有效样本量为 '+str(count[1]['value']))
        return response(pair+'：'+'，'.join(pieces)+'。相关系数无量纲，只描述样本的共同变化方向与程度。它不是带单位的回归斜率，不能据此推算干预一个单位造成的变化或证明因果关系。',used)
    return None



def scoped_result(assistant, sid, run_id, dictionary):
    # A revised descriptive run already has everything required for a first
    # readout. Publish the exact result before any optional model discussion.
    facts,runs=assistant.facts(sid,run_ids=[run_id])
    field=dictionary['outcome']
    chosen={}
    for key,fact in facts.items():
        if fact['run_id']==run_id and fact['text'] in (field+' / mean',field+' / finite_n'):
            chosen[fact['text'].split(' / ')[-1]]={'id':key,**fact}
    mean=chosen.get('mean',{}).get('value')
    count=chosen.get('finite_n',{}).get('value')
    value='没有有效均值' if mean is None else f'均值为 {mean:.6g}'+(dictionary.get('metric_unit') or '')
    text=f"{field}：{value}。"+(f'有效观测 {count} 条。' if count is not None else '')
    if dictionary.get('metric_window'):text+='观察期：'+dictionary['metric_window']+'。'
    text+=f"来源：方案 V{runs[0]['plan_version']}，运行 {run_id}。该结果描述所选样本。"
    return dict(text=text,source='本地已批准运行的指标与范围',facts=list(chosen.values()),run_ids=[run_id],citations=[])
