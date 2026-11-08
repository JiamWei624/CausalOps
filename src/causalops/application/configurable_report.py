"""Evidence-only configurable report; no model-sourced numeric facts."""
from html import escape as e
from causalops.general.service import DesignError

def complete_report(t,rates,groups,bundle,record,receipt,runs):
    p=t["plan"];sc=p["scope"];c=p["configuration"]
    text=(f"研究目标：{p['objective']}\n"
          f"{sc['groups'][c['control_value']]}：n={groups['0']['n']}，{sc['metric']}为{rates['control_rate']:.2%}；"
          f"{sc['groups'][c['treated_value']]}：n={groups['1']['n']}，{rates['treated_rate']:.2%}。"
          f"绝对差（后者减前者）{rates['pp']:.4f}个百分点，原工具95%区间[{rates['ci_pp'][0]:.4f}, {rates['ci_pp'][1]:.4f}]个百分点。\n"
          f"分析单位：{sc['analysis_unit']}；窗口：{sc['window']}；{sc['record_grain']}。"
          f"分配机制依据：{c['source_url']}；使用者核对说明：{c['design_evidence']}。"
          "方法：已注册ab_test，独立组均值差和1.96正态近似区间；小样本或稀少事件的近似可能不充分，不代表精确检验。"
          "结论仅支持已登记对象、分配机制和观察窗口中的二元概率差。未验证无干扰、外部代表性及全部识别假设，不支持其他指标、长期收益或任意人群的结论。"
          "独立记录及研究设计由用户确认；程序只核对声明、结构和来源一致性，不证明随机分配真实发生。"
          +("技术记录键依据用户确认的记录粒度生成，不是额外的身份核验。" if not c['entity'] else "")+
          f"\n描述统计Run：{runs[0]}；A/B Run：{runs[1]}；计划v{p['version']}；批准{receipt['approval_id']}。")
    return dict(status="complete",objective=p["objective"],scope=sc,source_runs=runs,sample_size=bundle.estimate.sample_size,
                group_summary=list(groups.values()),effect=rates,standard_error=bundle.estimate.standard_error,method="ab_test",
                interval_method="independent-group mean difference; normal approximation 1.96",design_source=c["source_url"],
                approval_id=receipt["approval_id"],plan_version=p["version"],domain_revision_id=record.revision_id,model_calls=0,text=text)


def html(view):
    t=view["task"];p=t["plan"];sc=p["scope"];c=p["configuration"];r=view["report"]
    parts=['<article class="co-automation-report" data-task-id="'+e(t['id'])+'" style="line-height:1.8;overflow-wrap:anywhere"><h2>'+e(sc['metric'])+' · 研究结果</h2>',
           '<p>任务 '+e(t['id'])+' · 计划 '+e(p['plan_id'])+' v'+str(p['version'])+'</p>',
           '<p>目标：'+e(p['objective'])+'</p><p>分析单位：'+e(sc['analysis_unit'])+'；观察窗口：'+e(sc['window'])+'</p>']
    if r:
        parts.append('<p>'+e(r['text']).replace('\n','<br>')+'</p>')
    elif 'S02' in view['evidence'] and not view['errors']:
        rows=view['evidence']['S02']['body']['grouped'];values={x['group_value']:x for x in rows}
        if set(values)!=set(sc['groups']) or any(x['field']!=sc['outcome'] for x in rows):raise DesignError('描述统计与当前指标不匹配，未展示数字。')
        parts.append('<h3>部分完成：实际描述统计</h3>')
        for k in (c['control_value'],c['treated_value']):
            x=values[k];parts.append(f'<p>{e(sc["groups"][k])}：样本量 {x["rows"]}，有效样本 {x["finite_n"]}，实际比例 <b>{x["mean"]:.2%}</b>。</p>')
        diff=100*(values[c['treated_value']]['mean']-values[c['control_value']]['mean'])
        ab_state='A/B未执行，随机化依据未知。' if c['assignment']=='unknown' else 'A/B结果尚未整合成完整报告，已保存的Run见下方。' if 'S04' in view['evidence'] else '尚无通过核验的A/B结果，不交付效应区间；不确定的运行须先调和。'
        parts.append(f'<p>描述性比例差（{e(c["treated_label"])} 减 {e(c["control_label"])}）：{diff:.4f} 个百分点。{ab_state}不能将此描述性摘要替代完整研究结论。</p>')
        parts.append('<p>描述统计 Run：'+e(view['evidence']['S02']['body']['run_id'])+'</p>')
    else:parts.append('<p>尚无可完整核验的统计报告，不生成未执行的结果。</p>')
    if c['assignment']=='unknown':parts.append('<p><b>随机分配依据未知</b>。请补充可核查的设计来源，修改研究范围后创建新的候选方案并重新审核。</p>')
    if view.get('binding_error'):parts.append('<p>当前执行授权不可用：'+e(view['binding_error'])+'。以下保留结果仅属于报告登记版本，不授予新执行权限。</p>')
    if t['reason']:parts.append('<p>'+e(t['reason'])+'</p>')
    for key in ('S02','S04'):
        if key in view['evidence']:parts.append('<p>'+key+' Run：'+e(view['evidence'][key]['body']['run_id'])+'</p>')
    parts.append('<p>数据指纹：'+e(p['data']['frame_sha'])+'；合同版本：'+str(p['contract_ref']['version'])+'。</p>')
    parts.append('<p>来源与用户设计说明：'+e(c['source_url']+' '+c['design_evidence'])+'</p>')
    parts.append('<p>未检查的假设不视为通过；模型调用0次。本流程不是通用自主研究。</p></article>')
    return ''.join(parts)

def descriptive_summary(t,desc,audit):
    """Pure read of a verified S02 output; never invent a second statistical Run."""
    import math
    sc=t['plan']['scope'];rows=desc['body']['grouped']
    control=sc.get('control_value','0');treated=sc.get('treated_value','1')
    by={r['group_value']:r for r in rows}
    if len(rows)!=2 or set(by)!=set(sc['groups']):raise DesignError('描述统计分组不匹配。')
    groups=[]
    for key,code in ((control,0),(treated,1)):
        x=by[key]
        if (x['field']!=sc['outcome'] or x['rows']!=x['finite_n'] or x['rows']!=audit['body']['group_counts'][key]
            or not math.isfinite(x['mean']) or not 0<=x['mean']<=1):raise DesignError('描述统计样本、指标或比例与审计不一致。')
        groups.append(dict(treatment=code,group_value=key,label=sc['groups'][key],n=x['rows'],proportion=x['mean']))
    total=sum(x['n'] for x in groups)
    if total!=audit['body']['rows']:raise DesignError('描述统计样本总量不匹配。')
    return dict(schema='saved-group-proportions-v1',source_run_id=desc['body']['run_id'],method='descriptive',
                sample_size=total,groups=groups,difference_pp=100*(groups[1]['proportion']-groups[0]['proportion']),
                difference_kind='descriptive_not_causal_effect',interval=None)

def descriptive_manifest(t,desc,audit,receipt):
    d=descriptive_summary(t,desc,audit);p=t['plan'];sc=p['scope'];a,b=d['groups']
    text=(f"研究目标：{p['objective']}\n{a['label']}：n={a['n']}，实际比例{a['proportion']:.2%}；{b['label']}：n={b['n']}，实际比例{b['proportion']:.2%}。"
          f"描述性比例差（后者减前者）{d['difference_pp']:.4f}个百分点。分析单位：{sc['analysis_unit']}；观察窗口：{sc['window']}。"
          "本计划仅执行描述统计和证据核验，没有执行A/B，没有因果效应估计或区间；不能据此认定因果关系。"
          +("随机分配依据未知，请补充设计来源并重新审核新研究范围。" if sc['assignment']=='unknown' else "本次未授权效果分析，不以描述结果代替效果结论。")+
          f"\n描述统计Run：{d['source_run_id']}；计划v{p['version']}；原批准：{receipt['approval_id']}。")
    return dict(status='descriptive_complete',objective=p['objective'],scope=sc,source_runs=[d['source_run_id']],sample_size=d['sample_size'],
                method='descriptive',descriptive=d,design_source=sc['assignment_source'],approval_id=receipt['approval_id'],plan_version=p['version'],model_calls=0,text=text)
