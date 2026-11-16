"""Read-only projection of a verified automation report; never an estimator."""
import re
from causalops.assistant.service import digest,check_run_mentions
from causalops.general.service import DesignError

def facts(view):
    r=view.get('report');out={}
    if not r:return out
    rid=r['source_runs'][-1]
    def add(key,label,value):out[rid+':report.'+key]=dict(text=label,value=value,run_id=rid,path='ReportManifest.'+key,claim='saved_report')
    add('sample_size','样本量',r['sample_size'])
    if r.get('effect'):
        f=r['effect']
        for key,label in [('control_rate','对照组比例'),('treated_rate','处理组比例'),('pp','绝对差（百分点）'),('ci_pp','原工具95%区间（百分点）')]:add('effect.'+key,label,f[key])
    elif r.get('descriptive'):
        d=r['descriptive']
        for i,g in enumerate(d['groups']):add('descriptive.groups.'+str(i),g['label']+'比例',g['proportion'])
        add('descriptive.difference_pp','描述性差异（百分点）',d['difference_pp'])
    return out

def requested_fields(question,scope):
    """Bounded result-field vocabulary, not method selection or open research reasoning."""
    patterns={
        'groups':r'比例|访问率|转化率|完成率|概率|两组|组别|\brates?\b',
        'samples':r'样本|人数|记录数|客户数|\bsample(?:_size)?\b',
        'difference':r'差异|差值|绝对差|效应|百分点|\bdifference\b',
        'interval':r'置信|区间|不确定性|\bci\b|\binterval\b',
        'limitations':r'限制|局限|结论|设计|随机|证据|适用|\blimits?\b',
        'relative':r'相对(?:增长|增幅|变化)|\brelative\b',
    }
    fields={k for k,v in patterns.items() if re.search(v,question,re.I)}
    if not fields:fields={'groups','samples','difference','interval','limitations'}
    current={str(scope.get(k,'')) for k in ('metric','outcome')}-{''}
    named=any(x in question for x in current)
    unknown=set()
    quoted=re.findall(r'[`"“]([^`"”]+)[`"”]',question)
    for item in quoted:
        if item not in current and item not in ('样本量','差异','置信区间','比例','研究限制'):
            unknown.add(item)
    for token in re.findall(r'\b[A-Za-z_][A-Za-z_0-9]*\b',question):
        if token.lower() not in {'ci','ab','a','b','run','id','sample','sample_size','rate','rates','difference','interval','relative','limits','limit'} and token not in current:
            unknown.add(token)
    for term in ('长期利润','利润','ROI','收益','收入','成本','销售额','留存率','购买率','访问率','转化率','客单价'):
        if term.lower() in question.lower() and not any(term.lower() in x.lower() for x in current):unknown.add(term)
    if unknown and not named:
        fields-={'groups','difference','interval','relative'}
        if not re.search(patterns['samples'],question,re.I):fields.discard('samples')
    fields.add('limitations')
    return fields,sorted(unknown)


def answer(a,sid,view,question):
    r=view.get('report');p=view['task']['plan'];sc=p['scope']
    if not r:raise DesignError('没有完整保存的报告。')
    check_run_mentions(question,r['source_runs'])
    catalog=facts(view);fields,unknown=requested_fields(question,sc);coverage={};lines=[]
    f=r.get('effect');d=r.get('descriptive');numeric=fields&{'groups','samples','difference','interval','relative'}
    if unknown:
        coverage['requested_metric']='unsupported'
        lines.append('当前报告**未计算**所问的其他指标（'+ '、'.join(unknown)+'），不能用'+sc['metric']+'替代，也不会借用其他研究的数值。新的研究指标需要重新配置与审核。')
    def md(value):return str(value).replace('|',r'\|').replace('\n',' ')
    control=sc.get('control_value','0');treated=sc.get('treated_value','1')
    if f:
        by={str(g['treatment']):g for g in r['group_summary']}
        groups=[(sc['groups'][control],by['0']['n'],f['control_rate']),(sc['groups'][treated],by['1']['n'],f['treated_rate'])]
    elif d:groups=[(g['label'],g['n'],g['proportion']) for g in d['groups']]
    else:raise DesignError('完整报告中缺少可核验的分组结果。')
    if fields&{'groups','samples'}:
        lines.append('| 比较组 | 每组样本 | '+md(sc['metric'])+' |\n| :-- | --: | --: |\n'+'\n'.join(f'| {md(name)} | {n:,} | **{rate:.2%}** |' for name,n,rate in groups))
        coverage.update(groups='available',samples='available')
    if 'difference' in fields:
        diff=f['pp'] if f else d['difference_pp']
        lines.append(('**绝对差**' if f else '**描述性差异**')+f'（{md(groups[1][0])} − {md(groups[0][0])}）：**{diff:.4f} 个百分点**，不是相对增长率。')
        coverage['difference']='available'
    if 'interval' in fields:
        if f and f.get('ci_pp') is not None:
            low,high=f['ci_pp'];lines.append(f'**原工具95%区间**：**[{low:.4f}, {high:.4f}] 个百分点**（正态近似）。');coverage['interval']='available'
        else:lines.append('**区间未执行**：本研究只有描述统计，没有A/B因果效应或推断区间。');coverage['interval']='not_executed'
    if 'relative' in fields:
        if f and f.get('relative_pct') is not None:lines.append(f"已保存的相对变化为 **{f['relative_pct']:.4f}%**，与百分点差的分母和单位不同。");coverage['relative']='available'
        else:lines.append('当前报告未保存可引用的相对变化，不从聊天追加计算。');coverage['relative']='unavailable'
    unit_line='**范围**：'+md(sc['window'])+'；'+md(sc['analysis_unit'])
    if numeric:unit_line+=f"，总样本 **{r['sample_size']:,}**。"
    lines.append(unit_line)
    assignment=sc.get('assignment') or view.get('evidence',{}).get('S01',{}).get('body',{}).get('assignment','unknown')
    if assignment=='unknown':design='随机分配依据未知，只能作描述性比较，不能认定因果关系。'
    else:design='设计资料由使用者核对；'
    limits='未验证全部识别假设、无干扰及外部代表性，不外推长期收益。' if f else '本计划仅授权描述统计，不提供因果效应与推断区间。'
    lines.append('**研究限制**：'+design+limits);coverage['limitations']='available'
    lines.append('完整报告与原始精度见“阅读完整报告”；本轮来源可展开核对。')
    result=dict(text='\n\n'.join(lines),facts=[dict(id=k,**v) for k,v in catalog.items()] if numeric else [],run_ids=r['source_runs'],upload_id=p['data']['upload_id'],
                source='本地保存报告解释（未调用模型）',scope='verified_automation_report',report_sha=digest(r),coverage=coverage)
    a.event(sid,'user',dict(question=question,run_ids=r['source_runs']));a.event(sid,'answer',result)
    return result
