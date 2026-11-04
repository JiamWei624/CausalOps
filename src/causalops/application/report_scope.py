"""Interpret the outcome and horizon of the selected, saved report."""
import re
from causalops.application.task_conclusions import source_dictionary

PROFIT = re.compile(r"净利(?:润)?|纯利|net[ _-]*profit", re.I)
YEAR = re.compile(r"明年|下一年|来年|next year", re.I)
METRICS = {"留存率":r"留存|retention","访问率": r"访问率|访问概率|visit(?:s| rate)?\b", "购买率": r"购买率|购买概率|conversion\b"}
UNITS = re.compile(r"百分点|[%％]|百分之|百分比|相对(?:增|变|提|降)|概率差|percentage points?|relative (?:change|lift|growth)", re.I)


def saved_answer(facts, run, dictionary, question, *, bundle=None):
    from causalops.application.saved_answers import saved_answer as resolve
    return resolve(facts, run, dictionary, question,bundle=bundle)


def report_scope(a, sid, run):
    dictionary, _ = source_dictionary(a, sid, run["run_id"])
    return dictionary.get("metric_label") or dictionary.get("outcome") or "", dictionary.get("metric_window") or ""


def scope_message(question, scopes):
    if not scopes:
        return ""
    labels = "、".join(dict.fromkeys(label for label, _ in scopes if label))
    names = "；".join(dict.fromkeys((label or "未登记指标")+"（"+(window or "窗口未登记")+"）" for label, window in scopes))
    issues = []
    if PROFIT.search(question) and not any(PROFIT.search(label) for label, _ in scopes):
        issues.append("净利润需要同一客户与观察期的收入、退货、商品成本及投放成本，并约定净利润口径")
    if re.search(r'留存|retention',question,re.I) and not re.search(r'留存|retention',labels,re.I):
        issues.append('留存率需要明确顾客或用户标识、起始队列、后续追踪与观察窗口；现有报告不能推算跨期留存。')
    if YEAR.search(question) and not any(YEAR.search(window) for _, window in scopes):
        issues.append("明年的结果需要明确起止日期，并补充该期间的跟踪数据；若目标是预测，须另立预测方案")
    for label, pattern in METRICS.items():
        if not issues and re.search(pattern, question, re.I) and labels and not re.search(pattern, labels, re.I):
            issues.append("请先选择对应"+label+"的报告，或登记该指标并建立新计划")
    if issues:
        return "当前选择："+names+"。该报告无法回答所问指标或期间。"+"。".join(issues)+"。"
    return ""


def unit_answer(facts, run, label, window, *, control=None, treated=None):
    prefix = run["run_id"] + ":rate."
    items = {k[len(prefix):]: (k, f) for k, f in facts.items() if k.startswith(prefix)}
    if not {"pp","raw","control_rate","treated_rate"} <= items.keys():
        return None
    cited = []
    def number(name, scale=1, places=2, suffix=""):
        k, fact = items[name]
        cited.append(dict(id=k, citation_label="证据"+str(len(cited)+1), **fact))
        value = fact["value"]
        shown = " 至 ".join(f"{x*scale:.{places}f}" for x in value) if isinstance(value, list) else f"{value*scale:.{places}f}"
        return shown+suffix+"［证据"+str(len(cited))+"］"
    control_name = f"对照组（{control}）" if control else "对照组"
    treated_name = f"处理组（{treated}）" if treated else "处理组"
    text = f"{label or '所选指标'}（{window or '该报告观察期'}）：{control_name} {number('control_rate',100,suffix='%')}，{treated_name} {number('treated_rate',100,suffix='%')}。"
    text += f"两组概率差为 {number('raw',places=5)}，乘以 100 得 {number('pp',suffix=' 个百分点')}。"
    difference=items['raw'][1]['value']
    if difference:
        text += f"{treated_name if difference<0 else control_name}的事件率较低。"
    else:
        text += "两组观测事件率相同。"
    if "ci_pp" in items:
        text += f"绝对差的置信区间为 {number('ci_pp',suffix=' 个百分点')}。"
    if "relative_pct" in items:
        text += f"以对照组为分母，相对变化为 {number('relative_pct',suffix='%')}。"
    elif items["control_rate"][1]["value"] == 0:
        text += "对照组事件率为零，相对变化没有定义。"
    text += "这两种幅度使用不同的单位；解释仅限本次样本、指标和观察期。"
    return {"source":"本地运行证据与单位换算","text":text,"facts":cited,"citations":[]}

def match_requested_report(service,sid,question,selected,binding):
    """Resolve explicit periods and registered outcomes against immutable same-task runs."""
    from causalops.application.plan_scope import DAY_SPAN, ISO_DATE, requested_scope
    explicit_dates=ISO_DATE.findall(question)
    has_window=bool(DAY_SPAN.search(question) or explicit_dates)
    references=service.a.completed_runs(sid)
    if not references:return None
    # Only constrain by an explicit request for a metric, not a covariate mentioned in a question.
    target=re.search(r'(?:指标|结果变量)(?:为|是|为：|：|设为)\s*([A-Za-z_]\w*)',question)
    registered=service.contracts.latest(sid)
    body=registered['body'] if registered else {}
    required_metric=target[1] if target else None
    if not required_metric and re.search('均值|中位数|平均|指标',question) and not re.search('相关|回归|关联|比较.*字段',question):
        fields=[body.get('outcome'),*body.get('predictors',[]),*(entry.get('field') for entry in body.get('fields',[]))]
        named={field for field in fields if field and re.search(r'(?<![A-Za-z0-9_])'+re.escape(field)+r'(?![A-Za-z0-9_])',question,re.I)}
        if len(named)==1:required_metric=named.pop()
    if not has_window and not required_metric:return None
    selected_dicts=[source_dictionary(service.a,sid,rid)[0] for rid in selected]
    span=None
    if has_window:
        if len(set(explicit_dates))==1 and not DAY_SPAN.search(question):
            return {'error':'请确认该日期是起点、终点还是单日观察窗口；尚未改变报告的日期口径。','ids':[]}
        probe=requested_scope(question,body,service.ws.load_upload(binding['upload_id']))
        if not probe or probe.get('error'):
            return {'error':(probe or {}).get('error','缺少已登记的时间字段或起止日期，请核对观察窗口。'),'ids':[]}
        span=(probe['start'],probe['end'])
    matches=[]
    for ref in references:
        dic,contract=source_dictionary(service.a,sid,ref['run_id'])
        if not contract or contract.get('data_sha')!=binding['frame_sha']:continue
        if required_metric and dic.get('outcome')!=required_metric:continue
        if not required_metric and selected_dicts and not any(
            all(dic.get(key)==src.get(key) for key in ('outcome','metric_unit','analysis_unit','control_value','treated_value'))
            for src in selected_dicts):continue
        if span:
            # Match the filter actually used by the statistical step, not dates mentioned in prose.
            steps=service.a.get_plan(ref['plan_id'])['plan']['steps']
            configurations=[step['config'] for step in steps if step['config']['method']==ref['method']]
            if len(configurations)!=1:continue
            config=configurations[0]
            if (config.get('date'),config.get('window_start'),config.get('window_end'))!=(body.get('time'),*span):continue
        matches.append(ref['run_id'])
    constrained=any(r['run_id'] in question for r in references) or bool(re.search('所选|选中|指定运行',question))
    if constrained:matches=[rid for rid in matches if rid in selected]
    chosen=[rid for rid in selected if rid in matches]
    if len(chosen)==1:return {'ids':chosen,'reason':'报告的已执行口径与请求一致'}
    if len(matches)==1:return {'ids':matches,'reason':'已匹配相同指标及观察窗口的运行'}
    if matches:return {'ids':[],'error':'有多份符合口径的运行，请选择报告编号：'+'、'.join(matches[:4])}
    return {'ids':[],'error':'当前报告不能回答所问指标或观察窗口'+('（'+' 至 '.join(span)+'）' if span else '')+'。请为该口径建立新方案并重新审核。'}
