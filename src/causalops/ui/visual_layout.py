"""Responsive shell and data-backed visual components for the local workbench."""
from html import escape
from io import BytesIO
import pandas as pd
import streamlit as st
from causalops.sample_data import wine_example


def steps(labels, current):
    items = []
    for index, label in enumerate(labels):
        mark = '✓' if index < current else str(index + 1)
        state = 'active' if index == current else 'done' if index < current else ''
        items.append(f'<span class="co-stage {state}"><b>{mark}</b>{escape(label)}</span>')
    st.html('<div class="co-steps">' + '<i></i>'.join(items) + '</div>')


def wine_card():
    raw, meta = wine_example()
    scores = pd.read_csv(BytesIO(raw), sep=meta['separator'])['quality']
    counts = scores.value_counts().sort_index()
    bars = ''.join(
        f'<div class="co-bin" title="{score} 分：{count} 条"><div style="height:{count/counts.max()*110:.2f}px"></div><small>{score}分</small></div>'
        for score, count in counts.items()
    )
    tiles = ''.join(f'<div><b>{value}</b><small>{label}</small></div>' for label,value in
                    [('记录数',f'{len(scores):,}'),('平均评分',f'{scores.mean():.3f}'),('中位数',f'{scores.median():g}')])
    st.html(f'<article class="co-preview"><header><strong>公开示例 · 葡萄酒质量分布</strong><span class="co-pill">公开数据</span></header>'
            f'<p>红葡萄酒检测数据，按质量评分统计样本数。</p><div class="co-kpis">{tiles}</div>'
            f'<div class="co-bars" role="img" aria-label="质量评分分布，5 分与 6 分的样本最多">{bars}</div>'
            '<div class="co-note">评分分布描述当前样本，不能据此判断配方的干预效果。</div></article>')


def shell_style():
    # Theme is injected once by showcase_widgets.style(). Kept as a compatible
    # entry point for other local callers; no competing CSS framework.
    from causalops.ui.design_system import apply_theme
    apply_theme()


def report_paper(report):
    css = """<style>@media screen{html{background:#f5f8fa}body{box-sizing:border-box;background:white;max-width:1152px;margin:32px auto;padding:40px clamp(16px,5vw,56px);border:1px solid #dce6e9;border-radius:8px;color:#172b37;box-shadow:0 9px 28px #18394412}h1{font-size:30px;line-height:1.4}h2{font-size:21px;margin-top:24px}details{margin:12px 0}table{font-size:14px}th{background:#f5f8fa}}@media print{body{border:0;box-shadow:none}}</style>"""
    return report.replace('</head>',css+'</head>',1) if '</head>' in report else report.replace('</style>','</style>'+css,1)
