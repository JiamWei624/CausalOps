"""Unified local portfolio: guided demos plus a read-only real-study viewer."""
from __future__ import annotations
import os,json,hashlib,uuid,traceback
from pathlib import Path
from datetime import datetime,timezone
import streamlit as st
from causalops.ui.showcase_support import ROOT,ROUTES,checked_route,source_fingerprint,safe_error,read_real_run
from causalops.ui.showcase_widgets import style,show_conclusion
from causalops.metadata.presentation_zh import diagnostic_rows_zh,diagnostics_for_display
from causalops.visualization import build_regression_diagnostic_figures
from causalops.reporting import render_html_report

from causalops.config import workspace_root
OUT=workspace_root()/'system'

def navigate(route):
    st.session_state['showcase_route']=route;st.query_params['route']=route

def sync_route():st.query_params['route']=st.session_state['showcase_route']

def home():
    st.markdown('<div class="eyebrow">CAUSALOPS / EVIDENCE TO DECISION</div>',unsafe_allow_html=True)
    st.title('从业务问题，到有依据的结论')
    st.markdown('<p class="hero-note">先看清研究设计，再执行统计分析。把结果解释为可理解的幅度、边界与行动建议；每条结论都能回到具体运行核对。</p>',unsafe_allow_html=True)
    st.button('开始分析我的数据',type='primary',on_click=navigate,args=('analysis',),width='stretch')
    st.info('上传自己的CSV/Parquet，明确变量与指标口径。已有研究可直接恢复；下面三条路线是示例中心。')
    st.subheader('示例中心 · 先学习也可以')
    cols=st.columns(3)
    cards=[('experiment','01 · 随机实验','发一封营销邮件，访问概率差多少？','公开随机实验数据 · 42,613条分析观测','核对设计 → 确认运行 → 阅读提升幅度','进入随机实验'),
           ('diagnostic','02 · 识别失败','估计很显著，就能说干预有效吗？','固定种子合成数据 · 专门设置前趋势问题','运行诊断 → 看趋势图 → 理解结论降级','进入识别失败演示'),
           ('weibo','03 · 真实研究','AI回复与用户再次互动有什么关系？','本地真实研究 · 488,472条有效事件','回看已有证据 → 解读量化差异 → 看平台意义','进入真实研究回看')]
    for col,(route,label,q,source,steps,button) in zip(cols,cards):
        available=route=='diagnostic' or (Path(os.environ.get('CAUSALOPS_PUBLIC_CATALOG','E:/ugc_ai_portfolio_public_data/prepared/catalog.json')).is_file() if route=='experiment' else (ROOT/'artifacts/real-panel-20261030/full-summary.json').is_file())
        with col,st.container(border=True,height=365):
            st.markdown('### '+label);st.markdown('**'+q+'**');st.caption(source);st.write(steps)
            st.button(button,key='go_'+route,on_click=navigate,args=(route,),width='stretch',disabled=not available)
            if not available:st.caption('可选历史示例未附带；通用上传和合成示例不受影响。')
    st.subheader('你会得到什么')
    st.markdown('**一份读得懂的结论**：原来什么水平、差多少、意味着什么、下一步做什么。\n\n**一套可核对的证据**：样本口径、方法、诊断、区间和保存运行。\n\n**明确的解释边界**：相关不自动等于因果；显著不自动等于值得推广。')
    st.caption('这是本机单用户分析入口。研究设计与执行中的人工审核仍然保留；RAG、MCP和A2A尚未作为本轮已实现能力。')

def real_view():
    st.title('真实微博研究 · 从已有证据解释平台问题')
    st.info('只读回看：本页不加载原始CSV、不重新估计、不修改原研究会话，也不向外部模型发送数据。')
    if not (ROOT/'artifacts/real-panel-20261030/full-summary.json').is_file():st.info('发行包不包含作者的真实微博数据或研究派生记录。请使用“分析我的数据”上传自己的分析表。');return
    bundle,path=read_real_run();e=bundle.evidence.get('estimator',{})
    st.markdown('**研究问题：在控制已登记的帖子与历史行为特征后，当前事件收到AI回复，与后续再次@AI的概率有什么关系？**')
    a,b,c=st.columns(3);a.metric('有效事件记录',f'{bundle.estimate.sample_size:,}');b.metric('用户聚类数',f"{e['cluster_count']:,}" if e.get('cluster_count') is not None else '未记录');c.metric('分析层级','用户发帖事件')
    st.caption('结果是各事件观察结束前是否再次@AI，并非统一长度的留存率；当前结果与论文中的不同估计口径不能混用。')
    show_conclusion(bundle)
    st.subheader('落实到平台：这条证据能支持什么')
    st.write('它可以支持进一步研究回复覆盖、回复时机和用户持续参与之间的关系，形成下一轮实验问题；不能直接证明“扩大AI回复就会提高留存”，也不能从本次关联系数推出新增用户总量或商业收入。')
    st.write('可执行的下一步是核对回复发生与结果观察的时序、固定随访窗口、识别回复选择机制，并设计随机或有充分依据的准实验。每次变更都应建立新研究版本，而非在问答中改写旧结果。')
    with st.expander('样本、诊断与可视化证据',expanded=True):
        st.dataframe(diagnostic_rows_zh(diagnostics_for_display(bundle)),hide_index=True,width='stretch')
        for title,figure in build_regression_diagnostic_figures(bundle).items():st.plotly_chart(figure,key='real_'+title,width='stretch')
    with st.expander('查看复现说明与分析边界'):
        st.write('当前只回看登记的full_any主运行；估计使用固定效应和按用户聚类的推断，解释等级为条件相关。完整研究页面还保留7/30天窗口等不同队列，不能把不同人群与窗口的系数差直接当成偏差大小。')
        st.code('运行编号：'+bundle.run_id+'\n证据SHA256：'+hashlib.sha256(path.read_bytes()).hexdigest())
    st.download_button('下载本次真实研究的完整图文报告',render_html_report(bundle).encode('utf-8'),file_name='CausalOps_真实研究_当前运行报告.html',mime='text/html')
    st.link_button('需要持续结果问答？打开原研究页','http://127.0.0.1:8502/?dataset=full_any')
    st.caption('原研究页是保留的高级入口；若未启动，请使用原有启动器，不要删除已有数据库。真实研究派生报告只供本地使用，不随公开源码发布。')

def guide():
    st.title('使用说明 · 先学会读懂一次分析')
    st.markdown('**主流程：** 上传自己的表 → 选择字段和两组取值 → 填写指标单位与窗口 → 保存草案 → 核对后执行 → 阅读结论、下载报告和证据。也可先使用合成示例。已有结果会自动恢复，刷新不重复执行。')
    st.subheader('四个常见词，怎么理解')
    st.dataframe([{'概念':a,'通俗解释':b} for a,b in [
       ('绝对变化 / 百分点','概率从20%到23%，绝对变化是3个百分点。相对变化是15%；两者不能混写。'),
       ('95%置信区间','衡量当前估计的不确定性；不是“真实效果有95%概率在这个固定区间内”的直接表述。'),
       ('统计显著与业务价值','区间、样本与设计帮助判断统计差异；是否推广还要结合成本、风险、最小有意义差异。'),
       ('条件相关与因果','观察性数据中控制了部分变量仍可能有混杂；不能自动写成某干预导致了结果。')]],hide_index=True,width='stretch')
    st.subheader('方法选择：先看设计，再看算法')
    st.dataframe([{'场景':a,'候选方法':b,'必须核对':c} for a,b,c in [
       ('处理被真实随机分配','A/B；有合适处理前指标时考虑CUPED','分配单位、结果窗口、重复观测、样本污染；CUPED不使用处理后协变量'),
       ('观测性用户截面','回归调整、PSM、IPW或DML','处理前混杂、重叠性、选择机制；算法不能消除未测混杂'),
       ('同一实体处理前后面板','DID / 事件研究','对照构造、处理时点、平行趋势、预期效应、干扰；交错处理需合适估计器'),
       ('条件或数据不足','描述性 / 关联分析','保留无法识别的部分，不用显著性包装因果结论')]],hide_index=True,width='stretch')
    st.caption('本表是人工整理的设计提示，不是自动方法识别证明，也不是已接入的RAG知识库。')
    st.subheader('已实现与后续扩展')
    st.write('已实现：证据约束的统计工具执行、版本化审核、图文报告、结果解释与原研究页的持续问答。当前统一首页默认使用本地证据，不需要API。')
    st.write('下一轮RAG：以可追溯的方法文献和指标口径为检索资料，记录出处、版本、适用条件、反例和引用；区分“文献建议”和“本次运行已证实”。先验收检索命中、引用正确与缺证拒答，再接入设计对话。UTD期刊文章需逐篇核实原文和授权范围，不能把期刊标签当成方法有效性的证明。')
    st.write('MCP：在现有白名单、审批、数据权限不变的前提下暴露工具和报告查询接口；它负责互联，不会自动提高结论质量。A2A：只有实际出现跨Agent交接时再加入，并与单流程比较。')
    st.markdown('[随机营销实验来源](https://blog.minethatdata.com/2008/03/minethatdata-e-mail-analytics-and-data.html) · [DoWhy方法与识别说明](https://www.pywhy.org/dowhy/) · [DoubleML官方说明](https://docs.doubleml.org/stable/) · [MCP官方介绍](https://modelcontextprotocol.io/docs/getting-started/intro)')

def status():
    st.title('系统状态与故障处理')
    current=source_fingerprint();loaded=os.environ.get('CAUSALOPS_SOURCE_FINGERPRINT')
    a,b,c=st.columns(3);a.metric('访问方式','仅本机');b.metric('模型模式','已配置官方API' if os.environ.get('DEEPSEEK_API_KEY') else '本地证据模式');c.metric('存储位置','当前工作区')
    st.caption('工作区：'+str(workspace_root()))
    if loaded and loaded!=current:st.warning('磁盘代码已更新，本服务仍是旧启动版本。请关闭启动窗口，再双击“启动作品集.cmd”；刷新页面不足以保证模块同步。')
    elif loaded:st.success('启动代码指纹与当前磁盘一致。')
    else:st.info('本次不是由统一启动器启动，无法确认进程版本；建议使用“启动作品集.cmd”。')
    st.code('当前代码指纹：'+current[:16]+'\n启动代码指纹：'+(loaded[:16] if loaded else '未登记'))
    required={'公开营销数据目录':Path('E:/ugc_ai_portfolio_public_data/prepared/catalog.json'),'真实研究汇总':ROOT/'artifacts/real-panel-20261030/full-summary.json'}
    st.dataframe([{'检查项':k,'状态':'已就绪' if p.is_file() else '缺少本地文件'} for k,p in required.items()],hide_index=True,width='stretch')
    st.markdown('**打不开网页：** 先双击项目目录的“启动作品集.cmd”，等待出现访问地址；不要先删除数据库。\n\n**导入错误或更新后界面不变：** 关闭启动窗口后重新启动，让进程重新加载模块。\n\n**端口已占用：** 启动器会说明是否是同一项目；只对本项目登记的进程提供重启，不自动关闭其他程序。\n\n**按钮灰色：** 先阅读设计并勾选核对框。生成候选不等于接受，接受也不等于批准。\n\n**模型不可用：** 本地分析、报告和证据仍能使用；不要把本地兜底当作模型回答。')
    st.caption('上述数据检查仅针对可选历史示例；缺少这些文件不影响通用工作台。')
    st.caption('故障日志只记录异常类型和代码位置，不记录API密钥、问题正文或原始行。')

def main():
    st.set_page_config(page_title='CausalOps · 研究与决策作品集',page_icon='◈',layout='wide');style()
    initial=checked_route(st.query_params.get('route','analysis'))
    if 'showcase_route' not in st.session_state:st.session_state['showcase_route']=initial
    with st.sidebar:
        st.markdown('## CausalOps');st.caption('有证据的分析 · 有边界的结论')
        route=st.radio('工作台导航',list(ROUTES),format_func=lambda k:ROUTES[k][0],key='showcase_route',on_change=sync_route)
        st.divider();st.caption('主流程：上传自己的表 → 映射并保存 → 审核执行 → 读结论与证据。示例中心用于学习。')
        st.caption('个人本地工作台 · 数据不自动外发')
    try:
        if route=='home':home()
        elif route=='analysis':
            options=['causal','descriptive','correlation','ols'];labels={'causal':'研究与效应分析','descriptive':'描述性统计分析','correlation':'相关分析','ols':'线性关联回归'}
            requested=st.query_params.get('mode','causal');kind=st.radio('分析任务类型',options,index=options.index(requested) if requested in options else 0,format_func=lambda x:labels[x],horizontal=True,key='analysis_kind')
            if kind=='causal':
                from causalops.ui.general_app import render_general
                render_general()
            else:
                from causalops.ui.exploration_app import render_exploration
                render_exploration(kind)
        elif route in ('experiment','diagnostic'):
            st.caption(ROUTES[route][1]);from causalops.ui.portfolio_demo import render_demo
            render_demo('hillstrom_men_visit' if route=='experiment' else 'did_bad_trend')
        elif route=='weibo':real_view()
        elif route=='guide':guide()
        else:status()
    except Exception as exc:
        fault=uuid.uuid4().hex[:12];OUT.mkdir(parents=True,exist_ok=True)
        with (OUT/'faults.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'fault_id':fault,'route':route,'at':datetime.now(timezone.utc).isoformat(),'exception_type':type(exc).__name__,
                    'frames':[{'file':Path(x.filename).name,'function':x.name,'line':x.lineno} for x in traceback.extract_tb(exc.__traceback__)]})+'\n')
        hint=safe_error(exc);st.error(hint['title']);st.write(hint['action']);st.caption('故障编号：'+fault)
        st.button('查看系统状态',on_click=navigate,args=('status',))

if __name__=='__main__':main()
