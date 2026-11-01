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
    from causalops import __version__
    st.caption('版本 '+__version__+' · 本地单用户工作区')
    st.title('CausalOps',anchor=False)
    st.markdown('<p class="hero-note">数据分析与研究工作台。支持数据理解、研究设计、统计分析与结果解读。</p>',unsafe_allow_html=True)
    st.caption('数据导入 → 问题与方案 → 分析执行 → 结果解读')
    from causalops.ui.model_setup import render_model_setup
    render_model_setup()
    st.subheader('数据导入')
    st.button('导入分析数据',type='primary',on_click=navigate,args=('assistant',),width='stretch')
    st.info('支持 CSV 与 Parquet。系统先核查数据结构并提供分析建议，必要口径由使用者确认。')
    with st.expander('示例分析与功能范围'):
        st.subheader('示例分析')
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
        st.subheader('分析产出')
        st.markdown('**分析结论**：样本参考水平、估计幅度、实际含义及后续建议。\n\n**运行证据**：样本口径、方法、诊断、区间和保存运行。\n\n**解释范围**：相关不自动等于因果；显著不自动等于值得推广。')
        st.caption('本机单用户工作台。支持方法文献检索、只读MCP证据查询及本地A2A方法审阅；研究设计审批和数据发送授权仍由使用者控制。')

def real_view():
    st.title('用户行为研究 · 已保存结果')
    st.info('只读回看：本页不加载原始CSV、不重新估计、不修改原研究会话，也不向外部模型发送数据。')
    if not (ROOT/'artifacts/real-panel-20261030/full-summary.json').is_file():st.info('发行包不包含作者的真实微博数据或研究派生记录。请使用“分析我的数据”上传自己的分析表。');return
    bundle,path=read_real_run();e=bundle.evidence.get('estimator',{})
    st.markdown('**研究问题：在控制已登记的帖子与历史行为特征后，当前事件收到AI回复，与后续再次@AI的概率有什么关系？**')
    a,b,c=st.columns(3);a.metric('有效事件记录',f'{bundle.estimate.sample_size:,}');b.metric('用户聚类数',f"{e['cluster_count']:,}" if e.get('cluster_count') is not None else '未记录');c.metric('分析层级','用户发帖事件')
    st.caption('结果是各事件观察结束前是否再次@AI，并非统一长度的留存率；当前结果与论文中的不同估计口径不能混用。')
    show_conclusion(bundle)
    st.subheader('平台应用与后续研究')
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
    st.title('使用说明与方法范围')
    st.markdown('**首次使用：** 首页填写模型与密钥（可跳过） → 点击导入分析数据 → 上传表格 → 生成基础报告或推荐分析方向 → 选择问题 → 确认必要事实与计划 → 本地计算 → 阅读结论、下载报告并继续追问。无需先选A/B或回归。已有结果会保留，刷新不重新计算。')
    st.subheader('常用统计概念')
    st.dataframe([{'概念':a,'说明':b} for a,b in [
       ('绝对变化 / 百分点','概率从20%到23%，绝对变化是3个百分点。相对变化是15%；两者不能混写。'),
       ('95%置信区间','衡量当前估计的不确定性；不是“真实效果有95%概率在这个固定区间内”的直接表述。'),
       ('统计显著与业务价值','区间、样本与设计帮助判断统计差异；是否推广还要结合成本、风险、最小有意义差异。'),
       ('条件相关与因果','观察性数据中控制了部分变量仍可能有混杂；不能自动写成某干预导致了结果。')]],hide_index=True,width='stretch')
    st.subheader('研究设计与方法选择')
    st.dataframe([{'场景':a,'候选方法':b,'执行条件':c} for a,b,c in [
       ('处理被真实随机分配','A/B；有合适处理前指标时考虑CUPED','分配单位、结果窗口、重复观测、样本污染；CUPED不使用处理后协变量'),
       ('观测性用户截面','回归调整、PSM、IPW或DML','处理前混杂、重叠性、选择机制；算法不能消除未测混杂'),
       ('同一实体处理前后面板','DID / 事件研究','对照构造、处理时点、平行趋势、预期效应、干扰；交错处理需合适估计器'),
       ('条件或数据不足','描述性 / 关联分析','保留无法识别的部分，不用显著性包装因果结论')]],hide_index=True,width='stretch')
    st.subheader('进阶方法与执行范围')
    st.dataframe([{'方法':a,'已支持':b,'主要限制':c} for a,b,c in [
        ('工具变量2SLS','一个内生变量；稳健或单向聚类推断；指定效应值AR型检验','无AR置信集合与CLR；工具有效性需实质论证'),
        ('清晰/模糊断点','局部线性、偏差校正区间及预定带宽比较；模糊断点另报处理概率跳跃','无自动密度/协变量连续性检验；模糊断点无弱第一阶段稳健区间'),
        ('交错DID','批次ATT、事件期效应、处理前联合检验；从未或尚未处理对照','限平衡面板与实体层聚类；无同时置信带，不支持处理反转')]],hide_index=True,width='stretch')
    st.subheader('方法检索与文献依据')
    st.write('“方法与文献”提供本地知识卡检索。每条卡片记录适用问题、数据要求、识别条件、诊断、失败情形及来源。实证条目区分摘要核对与全文相关页核对，保留具体范围；检索不到依据时明确说明，不生成替代引用。')
    st.subheader('模型、MCP与A2A的权限')
    st.write('模型可提出待审计划和解释已保存结果，不能自行确认研究事实或执行分析。MCP仅提供方法检索及显式导出的数字证据查询。A2A连接本地独立审阅服务，返回方法规则与来源，不具有审批或执行权限。新任务的数据发送须单独授权。')
    st.subheader('结果解读与验证')
    st.write('使用“结果与报告”查阅估计、区间、诊断与方法限制。统计显著性不能替代业务基线、成本或识别论证；缺少这些依据时不计算总体收益或ROI。历史运行保持独立，新的计划与估计不覆盖原始证据。')
    st.markdown('[rdrobust官方实现](https://github.com/rdpackages/rdrobust) · [linearmodels官方说明](https://bashtage.github.io/linearmodels/) · [differences官方说明](https://bernardodionisi.github.io/differences/latest/) · [statsmodels稳健推断](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.get_robustcov_results.html)')


def status():
    st.title('系统状态与故障排查')
    current=source_fingerprint();loaded=os.environ.get('CAUSALOPS_SOURCE_FINGERPRINT')
    a,b,c=st.columns(3);a.metric('访问方式','仅本机');b.metric('模型模式','浏览器会话已配置' if __import__('causalops.ui.model_setup',fromlist=['current_connection']).current_connection()[1] else '本地分析模式');c.metric('存储位置','当前工作区')
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
    st.set_page_config(page_title='CausalOps · 数据分析与研究工作台',page_icon='◈',layout='wide');style()
    initial=checked_route(st.query_params.get('route','home'))
    if 'showcase_route' not in st.session_state:st.session_state['showcase_route']=initial
    with st.sidebar:
        st.markdown('## CausalOps');st.caption('数据分析 · 研究设计 · 证据管理')
        route=st.radio('工作台导航',list(ROUTES),format_func=lambda k:ROUTES[k][0],key='showcase_route',on_change=sync_route)
        st.divider();st.caption('操作流程：导入数据 → 制定计划 → 审核设计 → 执行分析 → 查阅报告。')
        st.caption('本地单用户工作区 · 数据发送须单独授权')
    try:
        if route=='assistant':
            from causalops.ui.assistant_app import render_assistant
            render_assistant()
        elif route=='home':home()
        elif route=='analysis':
            options=['causal','descriptive','correlation','ols'];labels={'causal':'研究与效应分析','descriptive':'描述性统计分析','correlation':'相关分析','ols':'线性关联回归'}
            requested=st.query_params.get('mode','descriptive');kind=st.radio('分析任务类型',options,index=options.index(requested) if requested in options else 0,format_func=lambda x:labels[x],horizontal=True,key='analysis_kind')
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
