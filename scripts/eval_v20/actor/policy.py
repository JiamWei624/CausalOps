"""A reproducible, page-only simulated user. The controller owns all I/O with the page."""
import hashlib
import json
import re
from pathlib import Path


MAX_ACTIONS = 24
MAX_WAITS = 6
BUDGETS = {"disconnect": 2, "ambiguous": 2, "unchanged": 2}
CHAT = ("输入分析目标", "结果解读问题", "向研究助手提问", "输入问题")
APPROVE = ("接受计划并批准本次执行", "批准本次执行")
SENSITIVE = ("批准", "执行", "运行", "删除", "撤回")
NUM = r"(?<![0-9.])-?\d+(?:\.\d+)?(?:%|％)?"
TOPICS = {
    "B01": ("访问", "visit"),
    "B02": ("相关", "pearson", "spearman"),
    "B03": ("购买率", "访客", "分母", "转化率"),
    "B04": ("均值", "平均", "参考值", "基准", "检验"),
    "B05": ("访客", "指标", "新方案", "新计划"),
    "B06": ("窗口", "观察期", "期间", "日期", "追踪"),
}


def load_tasks():
    items = json.loads(Path(__file__).with_name("tasks.json").read_text(encoding="utf-8-sig"))
    return {item["id"]: item for item in items}


def _clean(text):
    return " ".join(str(text or "").split()).casefold()


def _mentions(text, tokens):
    return any(_clean(token) in text for token in tokens)


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _lines(text):
    # Only the current foreground text is supplied by the browser controller.
    return [_clean(line) for line in str(text or "").splitlines() if _clean(line)]


def _visible_response(task, obs, history):
    last_submit = next((a for a in reversed(history) if a.get("submitted")), None)
    if not last_submit:
        return ""
    prompts = {_clean(a.get("value")) for a in history if a.get("submitted")}
    if obs.get("reply_is_current", True) and obs.get("reply"):
        body = [_clean(line) for line in str(obs["reply"]).splitlines()]
    else:
        previous = set(last_submit.get("visible_line_hashes", []))
        body = [line for line in _lines(obs.get("text")) if _hash(line) not in previous]
    # Remove both prompt text and button/field labels. Leave displayed answers intact.
    labels = {_clean(c.get("name")) for c in obs.get("controls", [])}
    return "\n".join(line for line in body if line and line not in labels and
                     not any(prompt in line for prompt in prompts if prompt))


def _answer_state(case, body):
    if not body or not _mentions(body, TOPICS[case]):
        return None
    # Completion means that the user found an on-topic response, not that its
    # arithmetic, identification claims, source binding or conclusion are correct.
    limitation = _mentions(body, ("无法", "不能回答", "不足以", "不支持", "缺少", "未提供", "需要补充"))
    if case == "B05":
        return None  # The observable new review state is checked separately.
    if case == "B06" and limitation and _mentions(body, ("原", "报告", "留存", "窗口", "观察期", "数据")):
        return "页面解释了已有报告对所问观察期的限制。"
    if case == "B03" and _mentions(body, ("汇总", "合并", "加权", "等权")) and _mentions(body, ("分母", "访客")) and _mentions(body, ("零", "0")):
        return "已看到针对购买率口径和权重的说明。"
    if case == "B02" and re.search(r"(?:相关系数|pearson|spearman|\br\b)[^\n。]{0,32}?(?<!\d)-?(?:0\.\d+|1\.0+|0(?=\s*[。；,，]))", body):
        return "已看到一个明示的相关系数。"
    if case == "B01" and len(re.findall(NUM, body)) >= 2 and _mentions(body, ("差", "百分点", "比较", "高于", "低于")):
        return "已看到报告中关于访问率差异的数值答复。"
    if case == "B04" and re.search(r"(?<!\d)9(?:\.0+)?(?!\d)", body) and _mentions(body, ("差", "高于", "低于", "等于", "检验", "区间")) and len(re.findall(NUM, body)) >= 2:
        return "已看到样本与指定基准的数值比较。"
    return None


def _choices(controls, role, tokens):
    return [c for c in controls if c.get("role") in role and _mentions(_clean(c.get("name")), tokens)]


def _seven_day_range(values):
    from datetime import date
    dates = set()
    for value in values:
        try:
            dates.add(date(*map(int, re.findall(r"\d+", value))))
        except ValueError:
            continue
    return len(dates) == 2 and (max(dates) - min(dates)).days == 6


def decide(task, obs, history):
    case = task["id"]
    text = _clean(obs.get("text"))
    controls = [c for c in obs.get("controls", []) if c.get("ref") and not c.get("disabled") and not c.get("hidden")]
    page = _hash(text + "|" + "|".join(_clean(c.get("name")) + "=" + _clean(c.get("value")) for c in controls))

    def action(kind, reason, **fields):
        return {"action": kind, "reason": reason, "page_fingerprint": page, **fields}

    def wait(reason, bucket):
        total = sum(a.get("action") == "wait" for a in history)
        same = sum(a.get("bucket") == bucket and (bucket == "disconnect" or a.get("page_fingerprint") == page)
                   for a in history)
        if total >= MAX_WAITS or same >= BUDGETS.get(bucket, MAX_WAITS):
            return action("abandon", "达到等待预算。" + reason, bucket=bucket)
        return action("wait", reason, bucket=bucket)

    def use(kind, control, reason, **extra):
        name = _clean(control.get("name"))
        tries = [a for a in history if a.get("page_fingerprint") == page and a.get("action") == kind
                 and a.get("control_name") == name and a.get("value") == extra.get("value")]
        if tries and (tries[-1].get("result") != "failed" or len(tries) >= 2):
            return wait("页面未给出新的可操作状态，避免重复提交。", "unchanged")
        return action(kind, reason, ref=control["ref"], control_name=name, **extra)

    def submit(prompt):
        editors = _choices(controls, {"textbox", "textarea"}, CHAT)
        if len(editors) != 1:
            return wait("未能唯一定位可见的研究问题输入框。", "ambiguous")
        return use("fill", editors[0], "通过可见对话框向产品提交当前用户目标。", value=prompt,
                   submitted=True, visible_line_hashes=[_hash(x) for x in _lines(obs.get("text"))])

    if history and history[-1].get("action") in {"done", "abandon"}:
        return action(history[-1]["action"], history[-1]["reason"])
    if len(history) >= MAX_ACTIONS:
        return action("abandon", "达到本次交互的总动作上限。")
    if obs.get("disconnected"):
        return wait("当前页面断线，等待恢复。", "disconnect")
    if obs.get("pending"):
        return wait("页面显示请求尚在处理中。", "pending")

    sent = [a for a in history if a.get("submitted") and a.get("result") != "failed"]
    body = _visible_response(task, obs, history)
    visible = [c for c in obs.get("controls", []) if c.get("ref") and not c.get("hidden")]
    review = _choices(visible, {"button"}, APPROVE)
    awaiting = _mentions(_clean(obs.get("phase")), ("审核", "待审", "待批准")) or bool(review)
    approved = any(a.get("approved") and a.get("result") != "failed" for a in history)
    if approved and case in {"B05", "B06"}:
        report = _clean(obs.get("report_text", "")) or body
        expected = ("访客", "visitors") if case == "B05" else ("七天", "7天", "7 天", "七个自然日", "7个自然日")
        if (_mentions(report, expected) and re.search(NUM, report) and
                _mentions(report, ("均值", "平均", "总计", "合计", "中位数", "有效观测")) and not review):
            return action("done", "用户本人已批准改后版本，现可见新口径的数值报告。")
    # A user can read the visible report table even when the chat reply is brief.
    # Do not use hidden evidence panels, DOM attributes or prior run storage.
    page_lines = _lines(obs.get("text"))
    snippets = []
    if sent and case in {"B01", "B02", "B04"}:
        for line in page_lines:
            if (len(line) <= 800 and _mentions(line, TOPICS[case]) and re.search(NUM, line)
                    and not any(_clean(a.get("value")) in line for a in sent if a.get("value"))):
                snippets.append(line)
    answer_material = body + "\n" + "\n".join(snippets) if snippets else body
    final = None if case == "B06" and awaiting else _answer_state(case, answer_material)
    if final:
        return action("done", final, observed_evidence=(body[:600] + "\n" + "\n".join(snippets[:5]))[:1400])
    if not sent:
        if not _choices(controls, {"textbox", "textarea"}, CHAT):
            links = _choices(controls, {"button", "link", "tab"}, [task.get("study", task["title"])])
            if len(links) == 1:
                return use("click", links[0], "打开用户任务明确命名的研究。")
        report_terms = task.get("report_terms", [])
        selectors = _choices(controls, {"combobox"}, ("结果展示与追问", "选择报告", "历史报告"))
        chosen = any(a.get("report_selected") and a.get("result") != "failed" for a in history)
        if case == "B04" and not chosen:
            if not selectors:
                openers = _choices(controls, {"button"}, ("选择报告（按指标与观察期）",))
                if len(openers) == 1:
                    return use("click", openers[0], "展开可见的报告选择区域查找较早订单报告。")
            if len(selectors) == 1:
                selector = selectors[0]
                options = [c for c in controls if c.get("role") == "option"]
                labels = [c.get("name", "") for c in options] or selector.get("options", [])
                if not labels:
                    return use("click", selector, "展开下拉框查看可选择的报告原文。")
                matches = [x for x in labels if _mentions(_clean(x), report_terms)]
                if len(matches) != 1:
                    return wait("可见报告选项无法唯一确定较早的订单报告。", "ambiguous")
                option = next((c for c in options if c.get("name") == matches[0]), None)
                if option:
                    return use("click", option, "选择公开名称对应的订单报告。", report_selected=True)
                return use("select", selector, "选择公开名称对应的订单报告。", value=matches[0], report_selected=True)
            if len(selectors) > 1:
                return wait("报告选择器不唯一。", "ambiguous")
        return submit(task["prompt"])

    # In an authorized computation the user can approve a displayed matching
    # plan. An unrelated or unidentified plan must not be approved to get unstuck.
    if task.get("allow_approval") and awaiting and not approved:
        headers = [c for c in controls if c.get("role") == "button" and
                   re.search(r"分析方案\s*·\s*v\d+", _clean(c.get("name")))]
        if not obs.get("plan_text") and len(headers) == 1 and not any(a.get("opened_plan") for a in history):
            return use("click", headers[0], "展开本次分析方案核对指标或窗口。", opened_plan=True)
    if task.get("allow_approval") and awaiting and not approved and not review:
        manual = _choices(controls, {"radio", "tab", "button"}, ("人工审核",))
        if len(manual) == 1 and not any(a.get("manual_review") for a in history):
            return use("click", manual[0], "切换到人工审核以查看这次提出的新方案。", manual_review=True)
    if task.get("allow_approval") and len(review) == 1 and not approved:
        plan = _clean(obs.get("plan_text", ""))
        dates = re.findall(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}", plan)
        dated_week = case != "B06" or _seven_day_range(dates)
        if plan and dated_week and all(_mentions(plan, alternatives) for alternatives in task.get("plan_terms", [])):
            confirmations = _choices(controls, {"checkbox"}, ("我已核对上述计划和本步骤必要事实",))
            other_unchecked = [c for c in controls if c.get("role") == "checkbox" and not c.get("checked")
                               and _mentions(_clean(c.get("name")), ("我确认", "我已核对", "我已确认")) and c not in confirmations]
            if other_unchecked:
                return action("abandon", "页面还有需要人工确认的研究事实，不能代为判断。")
            if len(confirmations) == 1 and not confirmations[0].get("checked"):
                return use("click", confirmations[0], "基于展示的本次方案确认指标或时间口径。")
            if not review[0].get("disabled"):
                return use("click", review[0], "已从可见待审方案核对任务范围，批准本次计算。", approved=True)
            return wait("已核对方案，但批准按钮仍不可用。", "unchanged")
    if review and not task.get("allow_approval") and case != "B05":
        return action("abandon", "页面要求批准新计算，超出本题读取或解释已有报告的范围。")

    # A single task-specific follow-up is allowed only once the page has replied.
    if approved:
        return wait("等待本次批准后产生的新报告。", "pending")
    if body and len(sent) == 1 and task.get("followup"):
        return submit(task["followup"])
    if body and len(sent) >= 2:
        return action("abandon", "已追问一次，页面仍未呈现所需答复或待审方案。")
    return wait("已提交目标，等待本轮答复或可见审核状态。", "unchanged")

