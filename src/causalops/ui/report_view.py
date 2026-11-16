"""Read-only visual rendering of a verified automation_results.snapshot.

No estimator, database access, model output parsing, or execution permission lives here.
Formatting probabilities as percentages does not replace stored numerical evidence.
"""
from __future__ import annotations
import json
import math
from html import escape
from urllib.parse import urlsplit
from .design_system import REPORT_CSS


def _s(value):
    return escape(str(value), quote=True)


def _json(value):
    return _s(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def _link(url, label):
    parsed = urlsplit(url or '')
    if parsed.scheme in ('http', 'https') and parsed.netloc and not parsed.username and not parsed.password:
        return f'<a href="{_s(url)}" target="_blank" rel="noopener noreferrer">{_s(label)}</a>'
    return _s(label)+'：未登记可访问的公开来源'


from causalops.application.report_identity import identity_error as _identity_error


def _groups(view):
    p = view['task']['plan']; sc = p['scope']; r = view.get('report')
    control = sc.get('control_value', '0'); treated = sc.get('treated_value', '1')
    keys = [control, treated]
    if r and r.get('effect'):
        by = {str(x['treatment']): x for x in r['group_summary']}
        return [dict(label=sc['groups'][key], n=by[str(i)]['n'], rate=by[str(i)]['outcome_mean']) for i,key in enumerate(keys)]
    if r and r.get('descriptive'):
        return [dict(label=x['label'], n=x['n'], rate=x['proportion']) for x in r['descriptive']['groups']]
    # A partial report may show saved S02 means, never synthesize an effect or CI.
    ev = view['evidence']; rows = ev.get('S02', {}).get('body', {}).get('grouped', [])
    if not rows:
        return []
    by = {x['group_value']: x for x in rows}
    counts = ev.get('S01', {}).get('body', {}).get('group_counts', {})
    if len(rows) != 2 or set(by) != set(sc['groups']):
        raise ValueError('描述分组不一致')
    groups = []
    for key in keys:
        x = by[key]
        if x['field'] != sc['outcome'] or x['rows'] != x['finite_n'] or x['rows'] != counts.get(key) or not math.isfinite(x['mean']) or not 0 <= x['mean'] <= 1:
            raise ValueError('描述统计指标、样本或有效记录不一致')
        groups.append(dict(label=sc['groups'][key], n=x['rows'], rate=x['mean']))
    return groups


def _charts(groups, effect):
    bars = ''.join(f'<div class="co-bar-row"><div class="co-bar-label"><span>{_s(g["label"])}</span><b>{g["rate"]:.2%}</b></div><div class="co-bar-track"><div class="co-bar-fill {"treated" if i else ""}" style="width:{g["rate"]*100:.6f}%"></div></div><small>n = {g["n"]:,}</small></div>' for i,g in enumerate(groups))
    plot = '<p class="co-report-meta">不提供 A/B 推断区间。没有执行或尚未整合的统计，不能补画为已完成结果。</p>'
    if effect:
        lo, hi = effect['ci_pp']; point = effect['pp']
        low = min(0,lo,point); high = max(0,hi,point); width = max(high-low,1)
        low -= width*.12; high += width*.12
        def x(value): return 35+(value-low)/(high-low)*330
        def pct(value): return (x(value)-20)/380*100
        label = f'估计差 {point:.4f} 个百分点，95%区间 {lo:.4f} 至 {hi:.4f} 个百分点'
        plot = f'<div class="co-interval-figure" role="img" aria-label="{label}"><span class="co-ci-axis"></span><span class="co-ci-zero" style="left:{pct(0):.6f}%"></span><span class="co-ci-range" style="left:{pct(lo):.6f}%;width:{pct(hi)-pct(lo):.6f}%"></span><span class="co-ci-cap" style="left:{pct(lo):.6f}%"></span><span class="co-ci-cap" style="left:{pct(hi):.6f}%"></span><span class="co-ci-point" style="left:{pct(point):.6f}%"></span><span class="co-ci-label low" style="left:{pct(lo):.6f}%">{lo:.2f}</span><span class="co-ci-label" style="left:{pct(hi):.6f}%">{hi:.2f}</span><span class="co-ci-label zero" style="left:{pct(0):.6f}%">0</span></div><p class="co-report-meta">点为绝对差，线为原工具95%区间；零参考线不作为研究有效性的充分条件。</p>'

    return '<section class="co-report-section"><h2>组间比较与不确定性</h2><div class="co-report-charts"><div><h3>同一指标的两组比例</h3>'+bars+'<div class="co-report-axis"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div></div><div><h3>差异区间 · 个百分点</h3>'+plot+'</div></div></section>'


def render_report(view):
    """Render current verified evidence as one atomic, exportable HTML document."""
    from causalops.application.automation_results import STATES
    t = view['task']; p = t['plan']; sc = p['scope']; r = view.get('report')
    issue = _identity_error(view)
    try:
        groups = [] if issue else _groups(view)
    except (KeyError, ValueError, TypeError):
        issue = '描述统计与本任务的指标、有效样本或分组不能一致匹配。'; groups = []
    effect = r.get('effect') if r and not issue else None
    desc = r.get('descriptive') if r and not issue else None
    complete = bool(r and not issue)
    kind = 'conflict' if issue else 'complete' if effect else 'descriptive' if groups else 'pending'
    title = sc['metric']+' · 研究报告'
    parts = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+_s(title)+'</title><style>'+REPORT_CSS+'</style></head><body>',
             '<article class="co-automation-report" data-task-id="'+_s(t['id'])+'" data-plan-id="'+_s(p['plan_id'])+'" data-report-kind="'+kind+'" data-interval="'+('available' if effect else 'unavailable')+'">',
             '<h1>'+_s(title)+'</h1><p class="co-report-meta">已保存研究范围 · '+_s(sc['window'])+' · 分析单位：'+_s(sc['analysis_unit'])+' · 计划 v'+str(p['version'])+'</p>',
             '<p><b>研究目标：</b>'+_s(p['objective'])+'</p>']
    if issue:
        parts.append('<div class="co-report-limit conflict" role="alert"><strong>来源冲突 · 暂不展示联合统计结论</strong><p>'+_s(issue)+' 不使用其他任务的成功结果填补当前报告。</p></div>')
    elif groups:
        headline = '两组在登记窗口中的比例存在差异' if effect else '已保存描述统计，尚不能作因果解释'
        if effect:
            direction = '高于' if effect['pp'] > 0 else '低于' if effect['pp'] < 0 else '等于'
            headline = groups[1]['label']+'的'+sc['metric']+direction+groups[0]['label']
        interval = ('['+', '.join(f'{v:.2f}' for v in effect['ci_pp'])+']') if effect else '不提供'
        value = f'{effect["pp"]:+.2f}' if effect else f'{desc["difference_pp"]:+.2f}' if desc else '尚未整合'
        n = r['sample_size'] if r else view['evidence']['S01']['body']['rows']
        status = '研究已完成' if effect else '描述研究已完成' if complete else '部分完成 · 已保存描述统计'
        parts.append('<section class="co-report-lead"><span class="co-report-status '+('' if effect else 'warning')+'">'+status+'</span><h2 class="co-conclusion">'+_s(headline)+'</h2><p class="co-report-meta">比较组减对照组；只解释已登记对象、指标和窗口。数值来自本任务已保存的结构化证据。</p><div class="co-report-metrics">')
        for label,number,unit,cls,hint in [
            ('绝对差' if effect else '描述性比例差',value,'个百分点' if effect or desc else '无已整合差值','effect','非相对增长；不外推长期收益'),
            ('原工具95%区间',interval,'个百分点' if effect else '未执行或未整合A/B区间','interval','独立组均值差 · 1.96正态近似' if effect else '不补造因果效应区间'),
            ('分析样本',f'{n:,}',sc['analysis_unit'],'','仅当前登记的两个组'),
            ('观察窗口',sc['window'],'按数据合同登记范围','window','窗口文字不代表额外数据筛选')]:
            parts.append('<div><small>'+_s(label)+'</small><strong class="'+cls+'">'+_s(number)+'</strong><span class="unit">'+_s(unit)+'</span><div class="hint">'+_s(hint)+'</div></div>')
        parts.append('</div></section><section aria-label="关键研究限制" class="co-report-limit"><strong>'+('随机分配依据未知' if sc.get('assignment')=='unknown' else '结论的适用范围与尚未验证条件')+'</strong><p>'+('分配机制缺少可核对依据；仅作描述比较，不能据此认定因果关系。补充设计来源或更换研究范围，需要新候选方案并重新审核。' if sc.get('assignment')=='unknown' else '程序核对结构、声明与来源一致性，不证明全部识别假设。未实施基线协变量平衡检查，未验证无干扰和外部代表性；不支持其他指标、长期利润或任意人群的结论。')+(' 小样本或稀少事件的正态近似区间可能不充分，不代表精确检验。' if effect else ' 本报告不包含未经执行与证据整合的A/B结论。')+'</p></section>')
        parts.append(_charts(groups,effect))
    else:
        parts.append('<section class="co-report-limit"><strong>尚无通过核验的统计结果</strong><p>此任务尚未完成审核、执行或恢复核查。未执行步骤不显示统计数字，不生成完整研究结论。</p></section>')
    if t.get('reason'):
        parts.append('<p><b>当前停止原因：</b>'+_s(t['reason'])+'</p>')
    if view.get('binding_error'):
        parts.append('<div class="co-report-limit"><strong>当前执行授权不可用</strong><p>'+_s(view['binding_error'])+' 已保存结果只属于其来源版本，不授予新的执行权限。</p></div>')
    parts.append('<section class="co-report-section"><h2>研究口径、方法与统计依据</h2><dl class="co-report-facts">')
    fields = [('正式指标',sc['metric']+' / '+sc['outcome']),('分析单位',sc['analysis_unit']),('比较组',' 对比 '.join(sc['groups'].values())),('观察窗口',sc['window']),('当前任务状态',STATES.get(t['status'],t['status'])),('统计方法','已注册 ab_test · 独立组均值差与原区间' if effect else '已保存分组描述统计' if groups else '尚未完成统计')]
    for key,val in fields: parts.append('<div><dt>'+_s(key)+'</dt><dd>'+_s(val)+'</dd></div>')
    parts.append('</dl><p>'+_link(sc.get('assignment_source',''),'查看登记的研究设计来源')+'</p>')
    if 'configuration' in p:
        parts.append('<p class="co-report-meta">使用者登记的研究依据：'+_s(p['configuration'].get('design_evidence','尚未确认'))+'</p>')
    parts.append('<details><summary>已保存统计 Run、计划版本与来源哈希</summary><div class="co-report-scroll"><table><thead><tr><th>步骤</th><th>实际状态</th><th>Run / 证据哈希</th></tr></thead><tbody>')
    for row in view['steps']:
        parts.append('<tr><td>'+_s(row['name'])+'</td><td>'+_s(STATES.get(row['status'],row['status']))+'</td><td><code>'+_s(row.get('run_id') or row.get('output_sha') or '尚无成功证据')+'</code></td></tr>')
    identity = dict(task_id=t['id'],plan_id=p['plan_id'],plan_version=p['version'],plan_sha=t['plan_sha'],data=p['data'],contract_ref=p['contract_ref'],approval_id=(r or {}).get('approval_id'),source_runs=(r or {}).get('source_runs',[]))
    parts.append('</tbody></table></div><pre>'+_json(identity)+'</pre></details>')
    if r and not issue:
        parts.append('<details><summary>原始精度与保存的完整结论</summary><pre>'+_json(r.get('effect') or r.get('descriptive') or r)+'</pre><p>'+_s(r['text']).replace('\n','<br>')+'</p></details>')
    parts.append('<details><summary>结构化步骤证据与实际检查记录</summary><pre>'+_json(dict(evidence=view['evidence'],risks=view['risks'],errors=view['errors']))+'</pre></details></section><p class="co-report-meta">确定性事实报告；模型不生成这里的统计数字。诊断建议、研究决定和查看报告均不授予统计执行权限。完整原精度与来源可导出为结构化证据。</p></article></body></html>')
    return ''.join(parts)
