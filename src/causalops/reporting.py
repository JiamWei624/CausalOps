from __future__ import annotations

from pathlib import Path
from html import escape

from causalops.schemas import ClaimLevel, ResultBundle
from causalops.capabilities import format_method_label
from causalops.results.narrative import conclusion_sections, technical_conclusion_sections
from causalops.results.interpretation import business_sections, interpret_run
from causalops.metadata.presentation_zh import diagnostics_for_display
from causalops.metadata.presentation_zh import (
    claim_label_zh, diagnostic_rows_zh, estimand_label_zh,
    format_p_value_zh, message_zh, research_question_zh,
)


CLAIM_LANGUAGE = {
    ClaimLevel.DESCRIPTIVE: "仅允许描述样本中的统计现象，不得使用因果措辞。",
    ClaimLevel.ASSOCIATIONAL: "仅允许表述条件相关关系；识别或诊断不足，不能声称因果效应。",
    ClaimLevel.REDUCED_FORM: "研究设计支持受限的准实验解释，但仍须结合领域假设和人工复核。",
    ClaimLevel.IDENTIFIED_CAUSAL: "设计与当前诊断支持因果解释，但仍需报告适用范围和假设。",
}


def render_markdown_report(bundle: ResultBundle) -> str:
    """Render only values contained in a validated ResultBundle."""

    estimate = bundle.estimate
    if estimate is None:
        estimate_lines = ["尚未产生估计结果。"]
    else:
        ci = (
            f"[{estimate.confidence_interval[0]:.6g}, {estimate.confidence_interval[1]:.6g}]"
            if estimate.confidence_interval
            else "未计算"
        )
        estimate_lines = [
            f"- 目标量：{estimand_label_zh(estimate.estimand)}",
            f"- 估计值：{estimate.estimate:.6g}",
            f"- 标准误：{estimate.standard_error:.6g}" if estimate.standard_error is not None else "- 标准误：未计算",
            f"- 95%置信区间：{ci}",
            f"- 概率值（P值）：{format_p_value_zh(estimate.p_value)}",
            f"- 估计样本量：{estimate.sample_size}",
        ]
    diagnostics = [
        "| 诊断 | 通过 | 数值 | 阈值 | 诊断说明 | 是否阻断主张 |",
        "|---|---|---:|---|---|---|",
    ]
    for item in diagnostic_rows_zh(diagnostics_for_display(bundle)):
        diagnostics.append(
            "| " + " | ".join(str(item[key]).replace("|", "／") for key in
                ("诊断项目", "是否通过", "数值", "判定标准", "诊断说明", "是否限制因果主张")) + " |"
        )
    warning_lines = [f"- {message_zh(warning)}" for warning in bundle.warnings] or ["- 无额外警告。"]
    return "\n".join(
        [
            "# CausalOps 自动分析报告",
            "",
            f"- 运行编号：`{bundle.run_id}`",
            f"- 生成时间（UTC）：{bundle.created_at.isoformat()}",
            f"- 研究问题：{research_question_zh(bundle.spec.question)}",
            f"- 方法：{format_method_label(bundle.plan.selected_method)}",
            f"- 当前主张等级：{claim_label_zh(bundle.claim_level)}",
            ('- 执行范围：用户已授权仅关联分析；因果识别假设未批准。' if bundle.evidence.get('execution_authorization',{}).get('scope')=='association_only'
             else f"- 人工审核：{'必须' if bundle.plan.requires_human_approval else '非必须'}"),
            "",
            *_business_markdown(bundle),
            "## 估计结果",
            "",
            *estimate_lines,
            "",
            "## 方法诊断",
            "",
            *diagnostics,
            *_did_markdown_sections(bundle),
            "",
            "## 结论边界",
            "",
            CLAIM_LANGUAGE[bundle.claim_level],
            "",
            "## 警告与限制",
            "",
            *warning_lines,
            *_conclusion_markdown(bundle),
            "",
            "## 数据与复现信息",
            "",
            f"- 数据行数：{bundle.evidence['data']['row_count']}",
            f"- 数据列数：{bundle.evidence['data']['column_count']}",
            f"- 数据指纹：`{bundle.evidence['data']['fingerprint_sha256']}`",
            f"- Python：{bundle.evidence['runtime']['python']}",
            f"- Pandas：{bundle.evidence['runtime']['pandas']}",
            "",
            "> 本报告由结构化结果确定性生成，不调用大模型补写数值。",
            "",
        ]
    )


def write_markdown_report(bundle: ResultBundle, output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"report-{bundle.run_id}.md"
    _write_interpretation_evidence(bundle, output_dir)
    target.write_text(render_markdown_report(bundle), encoding="utf-8")
    return target


def _markdown_table(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["当前记录未提供该项数据。"]
    columns = list(rows[0])
    output = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        output.append("| " + " | ".join(str(row.get(c, "—")).replace("|", "／") for c in columns) + " |")
    return output


def _conclusion_markdown(bundle: ResultBundle) -> list[str]:
    lines = ["", "## 详细解释、综合结论与后续建议", ""]
    for title, paragraphs in technical_conclusion_sections(bundle):
        lines += [f"### {title}", ""]
        for paragraph in paragraphs:
            lines += [paragraph, ""]
    return lines


def _did_markdown_sections(bundle: ResultBundle) -> list[str]:
    if bundle.plan.selected_method.value != "did":
        return []
    from causalops.visualization import event_table_zh, sensitivity_table_zh
    output = ["", "## 动态效应与处理前诊断", "",
              "基准期为处理前第1日，其零值是归一化设定，不是估计出的零效应。其余区间为按实体聚类的逐点95%置信区间，未经同时推断校正。", "",
              *_markdown_table(event_table_zh(bundle)), "", "## 预设窗口敏感性分析", "",
              "比较仅使用预设缩短窗口；不得按显著性筛选结果或替换主分析。", "",
              *_markdown_table(sensitivity_table_zh(bundle))]
    sensitivity = bundle.evidence.get("window_sensitivity") or {}
    output.extend(["", *["- " + item for item in sensitivity.get("limitations", [])]])
    return output


def _html_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>当前记录未提供该项数据。</p>"
    columns = list(rows[0])
    head = "".join(f"<th>{escape(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(
        f"<td>{escape(format(v, '.6g') if isinstance(v, float) else str(v) if v is not None else '—')}</td>"
        for v in [row.get(c) for c in columns]) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render_html_report(bundle: ResultBundle) -> str:
    """Self-contained HTML; charts and narrative come from this exact ResultBundle."""
    from causalops.visualization import build_did_diagnostic_figures, build_regression_diagnostic_figures, event_table_zh, sensitivity_table_zh
    estimate = bundle.estimate
    estimate_rows = []
    if estimate:
        estimate_rows = [{"目标量": estimand_label_zh(estimate.estimand), "估计值": estimate.estimate,
                          "标准误": estimate.standard_error, "样本行数": estimate.sample_size,
                          "概率值": format_p_value_zh(estimate.p_value),
                          "95%置信区间": str(estimate.confidence_interval)}]
    sections = [
        ("<h1>CausalOps 关联分析与诊断报告</h1>" if bundle.plan.selected_method.value=='regression_adjustment' else "<h1>CausalOps 因果分析与诊断报告</h1>"),
        f"<p><strong>研究问题：</strong>{escape(research_question_zh(bundle.spec.question))}</p>",
        f"<p>运行编号：{escape(bundle.run_id)}<br>生成时间：{escape(bundle.created_at.isoformat())}<br>"
        f"分析方法：{escape(format_method_label(bundle.plan.selected_method))}<br>"
        f"当前主张等级：{escape(claim_label_zh(bundle.claim_level))}</p>",
        _business_html(bundle),
        "<h2>主分析估计</h2>", _html_table(estimate_rows),
        "<h2>方法诊断</h2>", _html_table(diagnostic_rows_zh(diagnostics_for_display(bundle))),
        f"<p class='note'>{escape(CLAIM_LANGUAGE[bundle.claim_level])}</p>",
    ]
    figures = build_did_diagnostic_figures(bundle)
    figures.update(build_regression_diagnostic_figures(bundle))
    for index, (title, figure) in enumerate(figures.items()):
        sections += [f"<h2>{escape(title)}</h2>", figure.to_html(
            full_html=False, include_plotlyjs=True if index == 0 else False,
            include_mathjax=False, config={"displaylogo": False, "responsive": True})]
    if figures and bundle.plan.selected_method.value=='did':
        sections += ["<p>动态效应图中的区间为逐点95%置信区间；原始均值轨迹未经回归调整，不能依据图形证明识别假设。</p>",
                     "<h2>逐期估计明细</h2>", _html_table(event_table_zh(bundle)),
                     "<h2>窗口敏感性分析明细</h2>", _html_table(sensitivity_table_zh(bundle))]
    sensitivity = bundle.evidence.get("window_sensitivity") or {}
    if sensitivity.get("reason"):
        sections.append(f"<p>{escape(sensitivity['reason'])}</p>")
    sections += ["<h2>警告与限制</h2>", "<ul>" + "".join(
        f"<li>{escape(message_zh(w))}</li>" for w in bundle.warnings) + "</ul>"]
    sections += [f"<p>{escape(w)}</p>" for w in sensitivity.get("limitations", [])]
    sections.append("<h2>详细解释、综合结论与后续建议</h2>")
    for title, paragraphs in technical_conclusion_sections(bundle):
        sections.append(f"<h3>{escape(title)}</h3>")
        sections.extend(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
    references = bundle.evidence.get("estimator", {}).get("method_reference_urls", []) + [
        "https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.results.PanelResults.conf_int.html",
        "https://plotly.com/python/error-bars/", "https://plotly.com/python/interactive-html-export/",
    ]
    sections += ["<h2>技术参考</h2>", "<ul>" + "".join(
        f'<li><a href="{escape(url, quote=True)}">{escape(url)}</a></li>'
        for url in dict.fromkeys(references)) + "</ul>",
        "<details><summary>原始结构化证据与复现信息</summary><pre>"
        + escape(bundle.model_dump_json(indent=2)) + "</pre></details>"]
    style = """body{font:15px/1.65 'Microsoft YaHei',SimSun,serif;color:#111;background:#fff;max-width:1180px;margin:32px auto;padding:0 24px}h1{font-size:25px;border-bottom:2px solid #222}h2{font-size:19px;margin-top:28px}.note{border-left:3px solid #333;padding:10px 16px;background:#f4f4f4}table{border-collapse:collapse;width:100%;font-size:12px}td,th{border:1px solid #aaa;padding:6px;text-align:left}th{background:#eee}.table-wrap{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}a{color:#222}@page{size:A4;margin:15mm}@media print{body{margin:0;padding:0;font-size:11px}h2{break-after:avoid}.table-wrap{overflow:visible}table{font-size:9px}.modebar{display:none!important}}"""
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CausalOps 分析诊断报告</title><style>' + style + "</style></head><body>" + "\n".join(sections) + "</body></html>"


def write_html_report(bundle: ResultBundle, output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"report-{bundle.run_id}.html"
    _write_interpretation_evidence(bundle, output_dir)
    target.write_text(render_html_report(bundle), encoding="utf-8")
    return target


def _business_markdown(bundle):
    lines=['## 一页读懂：主要结论','']
    for title,paragraphs in business_sections(bundle):
        lines.extend(['### '+title,'',*paragraphs,''])
    return lines


def _business_html(bundle):
    return '<section class="note"><h2>一页读懂：主要结论</h2>'+''.join('<h3>'+escape(title)+'</h3>'+''.join('<p>'+escape(p)+'</p>' for p in paragraphs) for title,paragraphs in business_sections(bundle))+'</section>'


def _write_interpretation_evidence(bundle,output_dir):
    import json
    value=interpret_run(bundle)
    target=output_dir/f"interpretation-{bundle.run_id}-{value['version']}.json"
    if target.is_file() and json.loads(target.read_text(encoding='utf-8'))!=value:
        raise ValueError('已有不同内容的结论解释版本，拒绝覆盖。')
    if not target.exists():target.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return target
