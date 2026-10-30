"""Plots drawn only from recorded numeric evidence, never model-generated values.

References: https://plotly.com/python/error-bars/
            https://plotly.com/python/interactive-html-export/
"""
from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from causalops.metadata.presentation_zh import field_label_zh
from causalops.schemas import ResultBundle


def _layout(figure: go.Figure, title: str, x_title: str, y_title: str) -> go.Figure:
    figure.update_layout(
        title=title, template="plotly_white", height=410,
        xaxis_title=x_title, yaxis_title=y_title,
        font={"family": "Microsoft YaHei, SimSun, sans-serif", "size": 13},
        margin={"l": 55, "r": 25, "t": 70, "b": 60},
        legend={"orientation": "h", "y": 1.12},
    )
    return figure


def build_regression_diagnostic_figures(bundle: ResultBundle) -> dict[str, go.Figure]:
    if bundle.plan.selected_method.value!='regression_adjustment': return {}
    if bundle.spec.domain.value!='ugc':
        return _generic_regression_figures(bundle)
    e=bundle.evidence.get('estimator',{});figures={}
    groups=e.get('raw_group_summary',[])
    if groups:
        figure=go.Figure(go.Bar(x=['未收到/尚未收到回复' if r['treatment']==0 else '收到回复' for r in groups],
            y=[r['outcome_mean'] for r in groups],customdata=[r['n'] for r in groups],
            text=[f"{r['outcome_mean']:.2%}" for r in groups],textposition='outside',marker_color=['#aaa','#333'],
            hovertemplate='未调整均值：%{y:.4f}<br>事件数：%{customdata:,}<extra></extra>'))
        figure.update_yaxes(tickformat='.0%')
        figures['未调整分组均值（不是因果效应）']=_layout(figure,'事件级分组均值，未控制样本构成差异','当前事件的回复状态','再次互动概率')
    monthly=e.get('monthly_group_summary',[])
    if monthly:
        figure=go.Figure()
        for status,label in [(0,'未收到/尚未收到'),(1,'收到回复')]:
            rows=sorted([r for r in monthly if r['treatment']==status],key=lambda r:r['period'])
            figure.add_trace(go.Scatter(x=[r['period'] for r in rows],y=[r['outcome_mean'] for r in rows],
                mode='lines+markers',name=label,customdata=[r['n'] for r in rows],
                hovertemplate='%{x}<br>均值：%{y:.4f}<br>事件数：%{customdata:,}<extra>%{fullData.name}</extra>'))
        figure.update_yaxes(tickformat='.0%')
        figures['年月分组的原始结果轨迹']=_layout(figure,'原始月度均值；不是DID趋势检验','发帖年月','再次互动概率')
    context=bundle.evidence.get('study_context',{})
    labels=['原始CSV','本分析入组','完整案例估计'];values=[context.get('raw_source_rows',bundle.evidence['data']['row_count']),
        bundle.evidence['data']['row_count'],e.get('complete_case_rows',0)]
    figure=go.Figure(go.Bar(x=labels,y=values,text=[f'{v:,}' for v in values],textposition='outside',marker_color=['#bbb','#777','#333']))
    figures['来源与估计样本量']=_layout(figure,'样本口径及筛选后的观测行数','阶段','事件记录数')
    return figures


def build_did_diagnostic_figures(bundle: ResultBundle) -> dict[str, go.Figure]:
    evidence = bundle.evidence.get("estimator", {})
    figures: dict[str, go.Figure] = {}
    if evidence.get("diagnostic_charts_available"):
        rows = evidence.get("event_study_table", [])
        estimated = [row for row in rows if not row["is_reference"]]
        if estimated:
            figure = go.Figure()
            for is_pre, label, symbol in [(True, "处理前系数", "circle"), (False, "处理后系数", "square")]:
                subset = [r for r in estimated if (r["relative_day"] < 0) == is_pre]
                if not subset:
                    continue
                figure.add_trace(go.Scatter(
                    x=[r["relative_day"] for r in subset], y=[r["estimate"] for r in subset],
                    mode="lines+markers", name=label,
                    line={"color": "#333333" if is_pre else "#777777"}, marker={"symbol": symbol},
                    error_y={"type": "data", "symmetric": False,
                             "array": [r["ci_upper"] - r["estimate"] for r in subset],
                             "arrayminus": [r["estimate"] - r["ci_lower"] for r in subset]},
                    hovertemplate="相对日：%{x}<br>系数：%{y:.4f}<extra>%{fullData.name}</extra>",
                ))
            if any(row["is_reference"] for row in rows):
                figure.add_trace(go.Scatter(x=[-1], y=[0], name="基准期（归一化为零，非估计值）",
                    mode="markers", marker={"symbol": "diamond-open", "size": 10, "color": "black"}))
            figure.add_hline(y=0, line_dash="dash", line_color="#888888")
            figure.add_vline(x=-0.5, line_dash="dot", line_color="#888888", annotation_text="处理开始")
            figure.update_xaxes(dtick=1)
            figures["动态效应与逐点置信区间"] = _layout(
                figure, "动态效应：以处理前第1日为基准", "相对处理日（0为处理当日）", "相对于基准期的系数")

        trajectories = evidence.get("group_trajectories", [])
        if trajectories:
            figure = go.Figure()
            for group, label, dash in [("treated", "处理组", "solid"), ("never_treated", "从未处理组", "dash")]:
                subset = sorted([r for r in trajectories if r["group"] == group], key=lambda r: r["relative_day"])
                figure.add_trace(go.Scatter(
                    x=[r["relative_day"] for r in subset], y=[r["mean_outcome"] for r in subset],
                    customdata=[[r["users"], r["calendar_date"]] for r in subset],
                    name=label, mode="lines+markers", connectgaps=False,
                    line={"dash": dash, "color": "#222222" if group == "treated" else "#888888"},
                    hovertemplate="相对日：%{x}<br>均值：%{y:.4f}<br>用户数：%{customdata[0]}<br>日期：%{customdata[1]}<extra>%{fullData.name}</extra>",
                ))
            figure.add_vline(x=-0.5, line_dash="dot", line_color="#888888", annotation_text="处理开始")
            figure.update_xaxes(dtick=1)
            figures["处理组与对照组轨迹"] = _layout(
                figure, "处理组与从未处理组的原始均值轨迹", "相对处理日", field_label_zh(bundle.spec.outcome))

    sensitivity = bundle.evidence.get("window_sensitivity") or {}
    rows = [r for r in sensitivity.get("rows", []) if r.get("status") == "estimated" and r.get("ci_lower") is not None]
    if rows:
        figure = go.Figure(go.Scatter(
            x=[f"{'主分析：' if r['is_primary'] else ''}前{r['pre_days']}天／后{r['post_days']}天" for r in rows],
            y=[r["estimate"] for r in rows], mode="markers", name="窗口估计值与95%区间",
            marker={"color": "#333333", "size": 10},
            error_y={"type": "data", "symmetric": False,
                     "array": [r["ci_upper"] - r["estimate"] for r in rows],
                     "arrayminus": [r["estimate"] - r["ci_lower"] for r in rows]},
        ))
        figure.add_hline(y=0, line_dash="dash", line_color="#888888")
        figures["预设窗口敏感性分析"] = _layout(figure, "预设缩短窗口的探索性比较", "分析窗口（后窗包含处理当日）", "双重差分估计值")
    return figures


def event_table_zh(bundle: ResultBundle) -> list[dict[str, Any]]:
    return [{"相对处理日": r["relative_day"], "系数": r["estimate"],
             "标准误": r["standard_error"], "区间下限": r["ci_lower"], "区间上限": r["ci_upper"],
             "是否基准期": "是（归一化，未估计）" if r["is_reference"] else "否"}
            for r in bundle.evidence.get("estimator", {}).get("event_study_table", [])]


def sensitivity_table_zh(bundle: ResultBundle) -> list[dict[str, Any]]:
    return [{"分析设定": "主分析" if r["is_primary"] else "预设比较",
             "前窗天数": r["pre_days"], "后窗天数": r["post_days"],
             "状态": "已估计" if r["status"] == "estimated" else "无法估计",
             "估计值": r.get("estimate"), "标准误": r.get("standard_error"),
             "区间下限": r.get("ci_lower"), "区间上限": r.get("ci_upper"),
             "样本行数": r.get("sample_size"), "处理用户数": r.get("treated_users"),
             "对照用户数": r.get("control_users"), "前趋势检验概率值": r.get("pretrend_p_value"),
             "无法估计原因": r.get("reason", "无")}
            for r in (bundle.evidence.get("window_sensitivity") or {}).get("rows", [])]


def _generic_regression_figures(bundle: ResultBundle) -> dict[str,go.Figure]:
    e=bundle.evidence.get('estimator',{});groups=e.get('raw_group_summary',[]);figures={}
    binary=e.get('outcome_binary',False)
    if groups:
        f=go.Figure(go.Bar(x=[f"处理状态 {r['treatment']:g}" for r in groups],
             y=[r['outcome_mean'] for r in groups],text=[f"{r['outcome_mean']:.4g}" for r in groups],
             customdata=[r['n'] for r in groups],textposition='outside',
             hovertemplate='未调整结果均值：%{y:.5g}<br>观测数：%{customdata:,}<extra></extra>'))
        if binary:f.update_yaxes(tickformat='.0%')
        figures['未调整分组均值（非因果效应）']=_layout(f,'未调整的处理组与对照组均值',bundle.spec.treatment,'结果概率' if binary else bundle.spec.outcome+' 原始单位')
    n=bundle.evidence['data']['row_count'];m=e.get('complete_case_rows',n)
    f=go.Figure(go.Bar(x=['输入数据','完整案例估计'],y=[n,m],text=[f'{n:,}',f'{m:,}'],textposition='outside'))
    figures['输入与估计观测数']=_layout(f,'分析样本口径','阶段','观测行数')
    return figures
