"""Evidence-only presentation and local runtime diagnostics for the portfolio."""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path
import plotly.graph_objects as go
from causalops.schemas import ResultBundle
from causalops.results.interpretation import interpret_run

ROOT=Path(__file__).resolve().parents[3]
ROUTES={
 'home':('首页与模型连接','首次使用引导、连接模型并开始分析。'),
 'assistant':('分析工作台','上传、对话、方法检索、受控执行与证据解释。'),
 'analysis':('专业分析','上传自己的表、确认研究设计、执行并恢复分析。'),
 'settings':('模型与隐私','模型连接及任务授权'),
 'history':('研究记录','恢复已保存研究'),
 'examples':('分析示例','载入葡萄酒公开样本或进入政策评估教学案例。'),
 'experiment':('营销实验示例','营销邮件是否提高访问概率？读懂绝对变化、区间和实际意义。'),
 'diagnostic':('政策评估示例','如果处理前趋势已经不同，为什么不能把估计称为因果效应？'),
 'weibo':('用户行为研究回看','回看已保存的全量研究结果；不重新读取原始CSV或估计。'),
 'guide':('使用说明与方法范围','理解指标、方法适用条件、权限边界和后续扩展。'),
 'status':('系统状态与故障排查','确认服务版本，按明确步骤恢复，不反复尝试相同操作。'),
}

def source_fingerprint(root:Path=ROOT)->str:
    h=hashlib.sha256()
    source=root/'src/causalops'
    if not source.is_dir():source=Path(__file__).resolve().parents[1]
    for p in sorted(source.rglob('*.py')):
        h.update(p.relative_to(source).as_posix().encode());h.update(p.read_bytes())
    return h.hexdigest()

def checked_route(value:str)->str:
    return value if value in ROUTES else 'home'

def safe_error(exc:Exception)->dict[str,str]:
    # Never display arbitrary exception text: it can contain paths, IDs or secrets.
    if isinstance(exc,ImportError):return {'title':'组件版本未同步','action':'关闭作品集启动窗口，然后双击“启动作品集.cmd”；已有研究记录会保留。'}
    if isinstance(exc,FileNotFoundError):return {'title':'所需文件尚未就绪','action':'请打开“系统状态与故障排查”核对数据和报告；可先使用识别失败的合成演示。'}
    if isinstance(exc,(ValueError,KeyError)):return {'title':'数据或证据未通过核验','action':'保留当前记录，不要修改原始证据；请查看故障编号并重新核对数据版本。'}
    return {'title':'本次操作未完成','action':'请保留当前页面和故障编号；重新打开作品集。如果再次出现，请提供编号。'}

def read_real_run(root:Path=ROOT)->tuple[ResultBundle,Path]:
    base=root/'artifacts/real-panel-20261030'
    payload=json.loads((base/'full-summary.json').read_text(encoding='utf-8'))
    item=next(x for x in payload['results'] if x['case_id']=='full_any')
    # Resolve the known local evidence file, never accept a user-supplied path.
    path=base/'full/full_any/evidence'/f"run-{item['run_id']}.json"
    bundle=ResultBundle.model_validate_json(path.read_text(encoding='utf-8'))
    if bundle.run_id!=item['run_id'] or bundle.claim_level.value!='associational':
        raise ValueError('真实结果与登记记录不一致。')
    if bundle.estimate is None or bundle.estimate.sample_size!=item['sample_size']:
        raise ValueError('真实结果样本口径不一致。')
    return bundle,path

def overview_numbers(bundle:ResultBundle)->dict:
    value=interpret_run(bundle);mag=value['magnitude'];binary=value['metric']['kind']=='binary'
    scale=100 if binary else 1
    return {'binary':binary,'unit':'个百分点' if binary else value['metric']['unit'],
            'estimate':None if mag['estimate'] is None else mag['estimate']*scale,
            'ci':None if mag['confidence_interval'] is None else [x*scale for x in mag['confidence_interval']],
            'baseline':value['baseline'],'metric':value['metric'],'texts':value['texts']}

def conclusion_figures(bundle:ResultBundle)->dict[str,go.Figure]:
    n=overview_numbers(bundle);figures={};base=n['baseline']
    if n['estimate'] is not None:
        f=go.Figure();ci=n['ci'];err={} if ci is None else {'error_x':{'type':'data','symmetric':False,'array':[ci[1]-n['estimate']],'arrayminus':[n['estimate']-ci[0]]}}
        f.add_trace(go.Scatter(x=[n['estimate']],y=['主估计'],mode='markers',marker={'size':15,'color':'#176b65'},**err,hovertemplate='估计差异：%{x:.4g} '+n['unit']+'<extra></extra>'))
        f.add_vline(x=0,line_dash='dash',line_color='#89959b')
        f.update_layout(title='估计值与 95% 置信区间' if ci is not None else '估计值（本次运行未提供区间）',xaxis_title=n['unit'],height=250,template='plotly_white',margin={'l':45,'r':45,'t':65,'b':45})
        # Zoom to the estimate and its uncertainty, always keep zero visible.
        points=[0,n['estimate']]+(ci or []);width=max(max(points)-min(points),.1);f.update_xaxes(range=[min(points)-width*.15,max(points)+width*.15])
        figures['幅度与不确定性']=f
    if base.get('available'):
        ab=bundle.plan.selected_method.value=='ab_test';binary=n['binary'];factor=100 if binary else 1
        labels=['未发送邮件','发送男装邮件'] if ab and bundle.spec.outcome=='visit' else ['处理字段=0','处理字段=1']
        means=[base['control_mean']*factor,base['treated_mean']*factor]
        f=go.Figure(go.Bar(x=labels,y=means,text=[f'{v:.2f}'+('%' if binary else '') for v in means],textposition='outside',marker_color=['#b6c5c6','#176b65']))
        f.update_layout(title='同一分析样本的未调整分组均值'+('' if ab else '（不是调整后的效应）'),yaxis_title='结果概率（%）' if binary else n['metric']['unit'],height=330,template='plotly_white',margin={'l':45,'r':30,'t':65,'b':50})
        f.update_yaxes(rangemode='tozero');figures['参考水平']=f
    return figures
