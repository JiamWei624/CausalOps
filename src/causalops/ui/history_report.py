"""Render one complete, explicitly sourced history snapshot per Streamlit delta."""
from html import escape
import json
from urllib.parse import urlsplit


def report_label(dictionary):
    metric = dictionary.get("metric_label") or dictionary.get("outcome") or "指标未登记"
    window = dictionary.get("metric_window") or "窗口未登记"
    groups = [dictionary.get(field) for field in ("treated_label", "control_label")]
    comparison = " 对 ".join(groups) if all(groups) else "未登记组间比较"
    return f"{metric} · {window} · {comparison} · 已完成"


def history_html(title, run, dictionary, conclusion, sources):
    def safe(value):
        return escape(str(value), quote=True)

    rid = safe(run["run_id"])
    links = []
    for item in sources:
        url = item["url"]
        if urlsplit(url).scheme in ("http", "https"):
            links.append(f'<li><a href="{safe(url)}">{safe(item["title"])}</a></li>')
    metric = dictionary.get("metric_label") or dictionary.get("outcome") or "未登记"
    window = dictionary.get("metric_window") or "未登记"
    facts = json.dumps(conclusion["evidence"], ensure_ascii=False, indent=2)
    return (
        f'<section data-history-rid="{rid}" aria-label="所示报告">'
        f'<strong>所示报告：{safe(title)} · {safe(metric)} · V{safe(run["plan_version"])}</strong>'
        f'<p>观察窗口：{safe(window)}</p><p>运行编号：{rid}</p>'
        f'<p>批准的计划指纹：{safe(run["plan_sha"])}</p>'
        f'<p>{safe(conclusion["sections"]["magnitude"])}</p>'
        '<details><summary>方法来源与运行证据</summary>'
        f'<ul>{"".join(links)}</ul><pre>{safe(facts)}</pre></details></section>'
    )
