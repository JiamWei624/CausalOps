"""Presentation of local exploratory evidence; never calls a model."""
from __future__ import annotations
from html import escape
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from causalops.general.exploration import LABELS
COLUMNS={'field':'字段','dtype':'类型','missing':'缺失数','missing_pct':'缺失比例(%)','distinct_nonmissing':'非缺失不同取值数','finite_n':'有限有效数','missing_n':'缺失数','infinite_n':'无穷值数','mean':'均值','median':'中位数','std_ddof1':'样本标准差','min':'最小值','max':'最大值','q25':'25%分位数','q75':'75%分位数','zero_n':'零值数','iqr_flag_n':'IQR异常标记数（未删除）','group_value':'分组取值','rows':'行数','value':'分类取值','is_missing':'是否缺失','n':'频数','pct_of_all_rows':'占全表比例(%)','period':'时间期','x':'变量一','y':'变量二','pairwise_n':'成对有效数','pearson':'Pearson系数','spearman':'Spearman系数','status':'状态','p_values':'显著性处理','term':'回归项','coefficient':'关联系数','standard_error':'标准误','ci95_low':'95%区间下限','ci95_high':'95%区间上限','p_value':'P值','exp_coefficient':'exp系数（OR或条件均值比）','exp_ci95':'OR或条件均值比的95%区间'}
def display(rows):return pd.DataFrame(rows).rename(columns=COLUMNS)
def figures(b):
    result={};s=b['summary']
    for row in s['histograms'][:4]:
        edges=row['edges'];centers=[(a+c)/2 for a,c in zip(edges,edges[1:])];width=[c-a for a,c in zip(edges,edges[1:])]
        f=go.Figure(go.Bar(x=centers,y=row['counts'],width=width,marker_color='#176b65'));f.update_layout(title=row['field']+' · 有限有效值分布',xaxis_title=row['field'],yaxis_title='频数',template='plotly_white',height=300);result['分布_'+row['field']]=f
    for row in s['categorical'][:3]:
        x=['（缺失）' if r['is_missing'] else r['value'] for r in row['top']];y=[r['n'] for r in row['top']]
        f=go.Figure(go.Bar(x=x,y=y,marker_color='#527b82'));f.update_layout(title=row['field']+' · 前20类频数',yaxis_title='频数（分母为全表）',template='plotly_white',height=300);result['频数_'+row['field']]=f
    if s['trend']:
        rows=pd.DataFrame(s['trend'])
        for field,g in rows.groupby('field',sort=False):
            f=go.Figure(go.Scatter(x=g['period'],y=g['mean'],name=field,mode='lines+markers'))
            f.update_layout(title=field+' · 分期有效值均值（未补缺期）',yaxis_title=field+'（原始单位）',template='plotly_white',height=320);result['时间汇总_'+field]=f
    if s['correlations']:
        fields=list(dict.fromkeys([r['x'] for r in s['correlations']]+[r['y'] for r in s['correlations']]))
        z=[[None]*len(fields) for _ in fields];counts=[[None]*len(fields) for _ in fields]
        for r in s['correlations']:
            i,j=fields.index(r['x']),fields.index(r['y']);z[i][j]=z[j][i]=r['pearson'];counts[i][j]=counts[j][i]=r['pairwise_n']
        for i,c in enumerate(fields):
            v=next(r for r in s['numeric'] if r['field']==c)
            if v['std_ddof1'] is not None and v['std_ddof1']>0:z[i][i]=1;counts[i][i]=v['finite_n']
        f=go.Figure(go.Heatmap(z=z,x=fields,y=fields,zmin=-1,zmax=1,colorscale='RdBu',reversescale=True,customdata=counts,hovertemplate='%{x} / %{y}<br>Pearson=%{z:.3f}<br>成对有效数=%{customdata}<extra></extra>'))
        f.update_layout(title='Pearson探索性相关（不同变量对样本数可不同）',template='plotly_white',height=420);result['相关矩阵']=f
    return result

def render_report(b):
    def tbl(rows):return '<p>无适用记录</p>' if not rows else display(rows).to_html(index=False,escape=True,na_rep='未计算')
    s=b['summary'];parts=['<h1>'+escape(LABELS[b['method']])+'</h1><p>'+escape(b['design']['question'])+'</p><p>运行：'+escape(b['run_id'])+'；配置V'+str(b['design_version'])+'；数据指纹：'+escape(b['data_fingerprint'])+'</p>','<h2>结论与下一步</h2>',''.join('<p>'+escape(x)+'</p>' for x in b['conclusions']),'<h2>数据质量</h2>',tbl(s['columns']),'<h2>数值描述</h2>',tbl(s['numeric'])]
    for r in s['categorical']:parts+=['<h2>分类频数：'+escape(r['field'])+'</h2><p>分母='+str(r['denominator'])+'；前20类之外剩余'+str(r['remaining_n'])+'行；完整频数合计'+str(r['complete_frequency_total'])+'。</p>',tbl(r['top'])]
    for title,key in [('分组描述','grouped'),('时间汇总','trend'),('探索性相关','correlations')]:
        if s[key]:parts+=['<h2>'+title+'</h2>',tbl(s[key])]
    if s.get('date_quality'):parts+=['<p>时间字段不可用行数：'+str(s['date_quality']['unusable_rows'])+'；'+escape(s['date_quality']['rule'])+'</p>']
    if b['regression']:parts+=['<h2>关联回归</h2><p>'+escape(b['regression']['note'])+' 协方差：'+escape(b['regression']['covariance'])+'</p>',tbl(b['regression']['coefficients'])]
    figs=figures(b)
    if figs:parts+=['<h2>图表（由保存汇总数据绘制）</h2>','<script>'+get_plotlyjs()+'</script>']+[f.to_html(full_html=False,include_plotlyjs=False) for f in figs.values()]
    parts+=['<h2>边界与统计口径</h2>',''.join('<p>'+escape(x)+'</p>' for x in b['warnings']),'<h2>来源</h2>',''.join('<p><a href="'+escape(u,quote=True)+'">'+escape(u)+'</a></p>' for u in b['sources'])]
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(LABELS[b['method']])+'</title><style>body{font-family:Microsoft YaHei,Arial;max-width:1180px;margin:40px auto;padding:0 24px;line-height:1.85;color:#21343a}table{border-collapse:collapse;width:100%;font-size:13px;overflow-wrap:anywhere}th,td{border:1px solid #d1dbd8;padding:8px;text-align:left}h2{margin-top:32px;border-bottom:1px solid #8ba7a0}p{overflow-wrap:anywhere}@page{size:A4;margin:16mm}@media print{table{font-size:8pt}h2{break-after:avoid}tr{break-inside:avoid}}</style>'+''.join(parts)+'</html>'