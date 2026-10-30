"""Readable evidence cards shared by the demo and portfolio viewer."""
from __future__ import annotations
from html import escape
import streamlit as st
from causalops.metadata.presentation_zh import claim_label_zh
from causalops.results.interpretation import business_sections
from causalops.ui.showcase_support import overview_numbers,conclusion_figures

def style():
    st.markdown("""<style>
    .block-container{max-width:1240px;padding-top:4.5rem;padding-bottom:3rem}
    h1{letter-spacing:-.03em} h2,h3{letter-spacing:-.02em}
    .eyebrow{font-size:.78rem;letter-spacing:.13em;color:#527a78;font-weight:700}
    .hero-note{font-size:1.04rem;line-height:1.85;max-width:900px;color:#637274}
    .flow{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 24px}
    .flow span{border:1px solid #b8cdcb;padding:8px 14px;border-radius:30px;font-size:.88rem}
    .flow .active{background:#176b65;color:white;border-color:#176b65}
    .source-pill{font-size:.82rem;color:#527a78;margin:6px 0 14px}
    div[data-testid=stMetric]{padding:14px;border:1px solid #d8e2df;border-radius:12px}
    div[data-testid=stMetricValue]{font-size:1.85rem}
    div[data-testid=stVerticalBlockBorderWrapper]{border-radius:14px}
    @media(max-width:700px){.block-container{padding:1rem}div[data-testid=stMetricValue]{font-size:1.4rem}}
    </style>""",unsafe_allow_html=True)

def flow(existing:bool):
    st.markdown('<div class="flow"><span>① 理解问题</span><span>② 审核设计</span><span class="'+('' if existing else 'active')+'">③ 确认运行</span><span class="'+('active' if existing else '')+'">④ 阅读结论与证据</span></div>',unsafe_allow_html=True)

def design_summary(spec):
    from causalops.capabilities import format_method_label
    from causalops.metadata.presentation_zh import field_label_zh,unit_label_zh
    friendly={'assigned':'是否随机分配发送男装邮件（assigned）','visit':'两周内是否访问网站（visit）','spend':'两周消费金额（spend）'}
    assignment={'randomized':'随机分配','observational':'观察性分配','unknown':'尚未明确'}.get(spec.assignment_mechanism.value,spec.assignment_mechanism.value)
    st.dataframe([{'要核对的内容':k,'当前设定':v} for k,v in [
      ('研究问题',spec.question),('分析单位','客户' if spec.analysis_unit=='customer' else unit_label_zh(spec.analysis_unit)),
      ('比较什么',friendly.get(spec.treatment,field_label_zh(spec.treatment))),('观察什么结果',friendly.get(spec.outcome,field_label_zh(spec.outcome))),
      ('分析方法','、'.join(format_method_label(x) for x in spec.candidate_methods)),('如何进入处理组',assignment)]],hide_index=True,width='stretch')

def show_conclusion(bundle):
    n=overview_numbers(bundle);a,b,c=st.columns([1.1,1.3,1.4])
    a.metric('主估计差异'+('（百分点）' if n['binary'] else ''),'未估计' if n['estimate'] is None else f"{n['estimate']:+.3f}")
    b.metric('95%置信区间','未记录' if n['ci'] is None else f"[{n['ci'][0]:.3f}, {n['ci'][1]:.3f}]")
    c.metric('允许的结论',{'identified_causal':'有条件因果解释','reduced_form':'受限准实验','associational':'条件相关','descriptive':'描述性结论'}[bundle.claim_level.value])
    st.caption('完整结论等级：'+claim_label_zh(bundle.claim_level))
    if bundle.claim_level.value in ('associational','descriptive'):
        st.warning('当前结果不能表述为“干预导致了改善”。下面仍展示估计幅度，同时保留解释边界。')
    st.caption('二元指标以百分点展示；例如0.03概率差等于3个百分点。数值来自当前保存运行，不由模型生成。' if n['binary'] else '数值按登记指标单位展示；不把系数随意换成百分比。')
    for title,paragraphs in business_sections(bundle):
        with st.container(border=True):
            st.markdown('**'+title+'**')
            for p in paragraphs:st.write(p)
    with st.expander('用图理解幅度与参考水平',expanded=True):
        for title,figure in conclusion_figures(bundle).items():st.plotly_chart(figure,key='summary_'+bundle.run_id+'_'+title,width='stretch')
    st.caption('结论对应运行：'+bundle.run_id+'；数据范围和识别假设不会因为图表更直观而自动成立。')
