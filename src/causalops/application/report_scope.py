"""Interpret the outcome and horizon of the selected, saved report."""
import re
from causalops.application.task_conclusions import source_dictionary

PROFIT = re.compile(r"净利(?:润)?|纯利|net[ _-]*profit", re.I)
YEAR = re.compile(r"明年|下一年|来年|next year", re.I)
METRICS = {"访问率": r"访问率|访问概率|visit(?:s| rate)?\b", "购买率": r"购买率|购买概率|conversion\b"}
UNITS = re.compile(r"百分点|[%％]|百分之|百分比|相对(?:增|变|提|降)|概率差|percentage points?|relative (?:change|lift|growth)", re.I)


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
    if YEAR.search(question) and not any(YEAR.search(window) for _, window in scopes):
        issues.append("明年的结果需要明确起止日期，并补充该期间的跟踪数据；若目标是预测，须另立预测方案")
    for label, pattern in METRICS.items():
        if not issues and re.search(pattern, question, re.I) and labels and not re.search(pattern, labels, re.I):
            issues.append("请先选择对应"+label+"的报告，或登记该指标并建立新计划")
    if issues:
        return "当前选择："+names+"。该报告无法回答所问指标或期间。"+"。".join(issues)+"。"
    return ""


def unit_answer(facts, run, label, window):
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
    text = f"{label or '所选指标'}（{window or '该报告观察期'}）：对照组 {number('control_rate',100,suffix='%')}，处理组 {number('treated_rate',100,suffix='%')}。"
    text += f"两组概率差为 {number('raw',places=5)}，乘以 100 得 {number('pp',suffix=' 个百分点')}。"
    if "ci_pp" in items:
        text += f"绝对差的置信区间为 {number('ci_pp',suffix=' 个百分点')}。"
    if "relative_pct" in items:
        text += f"以对照组为分母，相对变化为 {number('relative_pct',suffix='%')}。"
    else:
        text += "对照组事件率为零，相对变化没有定义。"
    text += "这两种幅度使用不同的单位；解释仅限本次样本、指标和观察期。"
    return {"source":"本地运行证据与单位换算","text":text,"facts":cited,"citations":[]}
