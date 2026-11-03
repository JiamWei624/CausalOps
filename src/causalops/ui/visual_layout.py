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
    st.html("""<style>
    :root{--co-ink:#172b37;--co-muted:#617986;--co-brand:#0e7772;--co-bg:#f5f8fa;--co-line:#dce6e9}
    [data-testid=stAppViewContainer],[data-testid=stMain],.stApp{background:var(--co-bg);color:var(--co-ink)}
    [data-testid=stHeader]{background:transparent;height:0;pointer-events:none}
    [data-testid=stToolbar], [data-testid=stDecoration]{display:none}
    [data-testid=stExpandSidebarButton]{pointer-events:auto;position:fixed;top:12px;left:6px;z-index:999}
    [data-testid=stMainBlockContainer]{max-width:none!important;padding:0 40px 36px!important}
    [data-testid=stSidebar]{background:#fff;border-right:1px solid var(--co-line)}
    @media(min-width:769px){[data-testid=stSidebar][aria-expanded=true]{width:232px!important;min-width:232px!important;max-width:232px!important}}
    [data-testid=stSidebarHeader]{height:0!important;min-height:0!important;padding:0!important}
    [data-testid=stSidebarUserContent]{padding:32px 17px 24px!important}
    [data-testid=stSidebar] [data-testid=stVerticalBlock]{gap:6px}
    [data-testid=stSidebar] [data-testid=stButton] button{justify-content:flex-start;min-height:52px;background:transparent;color:#506875;border:0;border-radius:11px;padding:10px 15px;font-weight:650;box-shadow:none}
    [data-testid=stSidebar] [data-testid=stButton] button[kind=primary]{color:#0e7772;background:#e8f4f0}
    .co-brand{display:flex;align-items:center;gap:12px;font-weight:750;font-size:22px;padding:7px 11px 26px}.co-logo,.co-icon{display:inline-grid;place-items:center;width:34px;height:34px;border-radius:10px;background:#14877e;color:white}.co-navcap{color:#718590;font-size:12px;font-weight:bold;margin:13px 12px 7px}
    .co-status{background:#f6faf9;border-radius:10px;padding:13px;color:#48656c;font-size:13px}.co-status small,.co-kpis small{display:block;color:var(--co-muted)}
    @media(min-width:769px) and (min-height:780px){[data-testid=stSidebar]:not(:has([data-testid=stSelectbox])) .co-status{position:absolute;bottom:24px;left:17px;right:17px}}
    .co-top{height:70px;margin:0 -40px 10px;padding:0 38px;display:flex;align-items:center;gap:22px;background:white;border-bottom:1px solid var(--co-line);font-size:16px}.co-top small{color:var(--co-muted)}.co-top .co-pill{margin-left:auto}
    .co-pill{border-radius:18px;background:#eaf2f2;color:#42676c;font-size:12px;padding:5px 12px;font-weight:650}
    .co-preview,[class*="st-key-panel_"]{background:white;border:1px solid var(--co-line);border-radius:17px;padding:23px;box-shadow:0 9px 28px rgba(24,57,68,.065)}
    .co-preview{min-height:446px}.co-preview header,.co-foothead{display:flex;align-items:center;justify-content:space-between;gap:12px}.co-preview p{color:var(--co-muted);font-size:14px;margin:12px 0 16px}
    .co-kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.co-kpis>div{padding:13px 12px;background:#f7fafb;border-radius:12px}.co-kpis b{font-size:25px;line-height:1.2}.co-kpis small{font-size:12px}
    .co-bars{height:150px;border-bottom:1px solid #c8d6d9;display:flex;gap:16px;align-items:flex-end;margin:15px 0;padding:0 14px 4px}.co-bin{flex:1;text-align:center;font-size:12px}.co-bin div{background:linear-gradient(#17988d,#0e7772);border-radius:6px 6px 0 0}
    .co-note{color:#29695e;background:#effaf6;border:1px solid #c6e6dd;border-radius:11px;padding:12px 16px;font-size:13px}
    .co-hero{padding:24px 4px 4px}.co-kicker{font-size:12px;font-weight:750;color:var(--co-brand);letter-spacing:1px}.co-hero h1{font-size:42px!important;line-height:1.30!important;letter-spacing:-1.4px;margin:17px 0 22px!important;padding:0!important}.co-hero p{font-size:16px;color:var(--co-muted);line-height:1.75;max-width:590px}
    .st-key-home_grid{margin-top:20px}.st-key-home_actions button{min-height:48px}.co-foothead{font-size:22px;font-weight:bold;margin:20px 0 4px}.co-foothead small{font-size:14px;font-weight:400;color:var(--co-muted)}
    .st-key-directions button{background:white;border:1px solid var(--co-line);border-radius:16px;min-height:84px;justify-content:flex-start;text-align:left;padding:12px 18px}.st-key-directions button span[data-testid=stIconMaterial]{background:#e8f4f0;padding:9px;border-radius:10px;color:var(--co-brand)}
    .co-steps{display:flex;align-items:center;gap:10px;background:white;border:1px solid var(--co-line);border-radius:13px;padding:12px 16px}.co-steps i{height:1px;background:#d5e0e3;flex:1}.co-stage{font-size:13px;color:var(--co-muted)}.co-stage b{display:inline-grid;place-items:center;background:#f1f5f6;border-radius:50%;width:27px;height:27px;margin-right:6px}.co-stage.active{font-weight:bold;color:var(--co-ink)}.co-stage.active b,.co-stage.done b{background:#e5f4f0;color:var(--co-brand)}
    [data-testid=stFileUploaderDropzone]{background:#f4faf8;border:2px dashed #b7dcd4;border-radius:15px;min-height:165px;align-items:center}
    @media(max-width:768px){[data-testid=stMainBlockContainer]{padding:0 16px 24px!important}.co-top{margin:0 -16px 0;padding:0 15px 0 46px;height:54px}.co-top small{display:none}.co-hero{padding:0}.co-hero h1{font-size:30px!important}.co-preview{min-height:0}.co-steps{flex-wrap:wrap}.co-foothead small{display:none}.st-key-home_grid{margin-top:0}.co-bars{gap:8px}.co-kpis b{font-size:22px}[class*="st-key-panel_"]{padding:16px}}
    @media(min-width:769px){
      [data-testid=stSidebar][data-collapsed=false]{width:232px!important;min-width:232px!important;max-width:232px!important}
      [data-testid=stSidebarContent]{padding:0!important}
      [data-testid=stSidebarUserContent]{padding:16px 17px 24px!important}
      [data-testid=stSidebarUserContent]>div{padding-left:0!important;padding-right:0!important}
      [data-testid=stSidebar]:not(:has([data-testid=stSelectbox])) .co-status{position:fixed;bottom:25px;left:17px;width:197px;min-height:96px}
      .co-top{margin-top:-16px}.co-preview{padding:24px}.st-key-home_grid{margin-top:21px}
      .st-key-directions button>div,[data-testid=stSidebar] [data-testid=stButton] button>div{width:100%}
      .st-key-directions button>div>span,[data-testid=stSidebar] [data-testid=stButton] button>div>span{justify-content:flex-start}
    }
    .st-key-home_grid [data-testid=stForm]{background:white;border:1px solid var(--co-line);border-radius:12px;padding:8px}
    .st-key-home_grid [data-testid=stTextInputRootElement]{background:white;border:0}
    .st-key-home_grid [data-testid=stFormSubmitButton] button{border:0;color:var(--co-brand)}
    .st-key-panel_conclusion{background:linear-gradient(100deg,white,#f0f8f5)}.st-key-panel_conclusion [data-testid=stMetricValue]{color:#0e7772}
    [data-testid=stChatMessage]{padding:16px;border:1px solid #d7e6e3;background:white;border-radius:13px}
    [data-testid=stChatMessage]:has([data-testid=stChatMessageAvatarUser]){background:#e9f4f0}
    .st-key-panel_discussion [data-testid=stChatInput]{position:static}
    .st-key-directions [data-testid=stMarkdownContainer] p{font-size:13px!important;text-align:left;color:#617986;line-height:1.5}.st-key-directions strong{font-size:15px;color:#172b37}
    .st-key-directions button [data-testid=stIconMaterial]{font-size:22px!important;line-height:1}
    [data-testid=stAppViewContainer]{font-family:"Microsoft YaHei","Segoe UI",sans-serif}
    [data-testid=stSidebar] [data-testid=stButton] button>div>span{gap:14px}
    .co-preview header{position:static}.co-preview strong{font-size:18px}
    [data-testid=stSidebar] [data-testid=stButton] button [data-has-shortcut],.st-key-directions button [data-has-shortcut]{display:flex!important;width:100%!important;justify-content:flex-start!important}
    [class*="st-key-panel_"] h3{font-size:20px!important;padding-top:0!important;line-height:1.35!important}
    [data-testid=stMainBlockContainer] h1:not(.co-hero h1){font-size:30px!important;line-height:1.35!important;padding-top:0!important;padding-bottom:0!important}
    [class*="st-key-panel_"] div[data-testid=stMetric]{background:#f7fafb;border:0;border-radius:12px;padding:12px 14px}
    .co-kv{font-size:14px;margin:0 0 12px}.co-kv div{display:grid;grid-template-columns:minmax(85px,23%) 1fr;gap:12px;padding:12px 0;border-bottom:1px solid #e5ecef}.co-kv dt{font-weight:650;color:#536d78}.co-kv dd{margin:0}
    @media(min-width:769px){[data-testid=stSidebarUserContent]{padding-left:7px!important;padding-right:7px!important}
    [data-testid=stSidebar]:has([data-testid=stExpander]) .co-status{position:static;width:auto;margin:12px 0}
    [class*="st-key-panel_discussion"],[class*="st-key-panel_design"]{min-height:480px}
    .st-key-panel_approval{min-height:480px}.st-key-panel_field_preview{min-height:590px}
    .co-foothead{margin-top:16px}
    [data-testid=stElementContainer]:has(#causalops-overview){height:0!important;margin-bottom:-16px}
    }
    .co-paper{max-width:1152px;margin:16px auto;background:white;border:1px solid var(--co-line);border-radius:8px;padding:32px clamp(16px,4vw,56px);box-shadow:0 9px 28px #18394412}.co-paper small{font-size:12px;letter-spacing:1px;color:var(--co-brand)}.co-paper h2{font-size:28px}.co-paper p{font-size:16px}.co-paper hr{border:0;border-top:1px solid var(--co-line)}
    @media(min-width:769px){[data-testid=stLayoutWrapper]:has(> .st-key-phone_nav){display:none!important}}
    .st-key-phone_nav,.st-key-phone_nav:empty{display:none!important}
    @media(max-width:768px){
       .st-key-phone_nav{display:block!important;position:fixed;top:9px;left:8px;width:36px!important;z-index:12}
       .st-key-phone_nav button{min-width:34px;padding:4px;border:0}.st-key-phone_nav button svg{display:none}
       .co-top{gap:8px;margin-top:-16px}.co-top strong,.co-top .co-pill{white-space:nowrap}.co-top .co-pill{font-size:10px;padding:4px 6px}
       .st-key-home_grid [data-testid=stForm] [data-testid=stHorizontalBlock]{flex-wrap:nowrap}
       .st-key-home_grid [data-testid=stForm] [data-testid=stColumn]:first-child{min-width:0;flex:1}
       .st-key-home_grid [data-testid=stForm] [data-testid=stColumn]:last-child{min-width:32px;flex:0 0 32px}
    }
    [data-testid=stElementContainer]:has(.co-top){position:sticky;top:0;z-index:6;pointer-events:none}
    [class*="st-key-panel_conclusion_"],.co-paper{scroll-margin-top:80px}
    .st-key-home_actions button[kind=primary],[data-testid=stMain] button[kind=primary]:enabled{background:#126e67;color:white;border-color:#126e67}
    [class*="st-key-panel_case_"]{height:100%;border-top:3px solid #78aca1}
    .co-paper-metrics{display:flex;gap:30px;flex-wrap:wrap}.co-paper-metrics strong{display:block;font-size:32px}.co-paper-metrics small{letter-spacing:0;color:var(--co-muted)}
    </style>""")


def report_paper(report):
    css = """<style>@media screen{html{background:#f5f8fa}body{box-sizing:border-box;background:white;max-width:1152px;margin:32px auto;padding:40px clamp(16px,5vw,56px);border:1px solid #dce6e9;border-radius:8px;color:#172b37;box-shadow:0 9px 28px #18394412}h1{font-size:30px;line-height:1.4}h2{font-size:21px;margin-top:24px}details{margin:12px 0}table{font-size:14px}th{background:#f5f8fa}}@media print{body{border:0;box-shadow:none}}</style>"""
    return report.replace('</head>',css+'</head>',1) if '</head>' in report else report.replace('</style>','</style>'+css,1)
