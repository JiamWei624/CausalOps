"""Central presentation tokens and scoped styles; no research state or permissions."""
TOKENS = {
    'canvas': '#FFFFFF', 'surface': '#FFFFFF', 'ink': '#24272D',
    'muted': '#68717D', 'brand': '#303842', 'line': '#E2E3E7',
    'positive': '#17643D', 'warning': '#855A08', 'danger': '#A3312B',
}

REPORT_CSS = """
.co-automation-report{font:15px/1.8 'Segoe UI','Microsoft YaHei',sans-serif;color:#24272d;overflow-wrap:anywhere;max-width:1280px;margin:0 auto}
.co-automation-report *{box-sizing:border-box}.co-automation-report h1{font-size:28px!important;line-height:1.5!important;letter-spacing:0;margin:0 0 8px!important}
.co-automation-report h2{font-size:19px!important;line-height:1.5!important;margin:0 0 16px!important;padding:0!important}.co-automation-report h3{font-size:16px!important;margin:0 0 12px!important}
.co-automation-report p{font-size:16px;line-height:1.85;margin:8px 0 14px}.co-report-meta{color:#68717d;font-size:13px!important}
.co-report-lead{background:#fff;border:1px solid #e2e3e7;border-top:3px solid #303842;border-radius:10px;padding:26px 28px;margin:20px 0}
.co-report-lead .co-conclusion{font-size:24px!important;font-weight:650;line-height:1.5!important;margin:14px 0 8px!important}.co-report-status{display:inline-block;font-size:12px;font-weight:600;padding:3px 9px;border-radius:4px;background:#eaf5ef;color:#17643d}
.co-report-status.warning{color:#855a08;background:#fff4d8}.co-report-status.danger{color:#a3312b;background:#fceeed}
.co-report-metrics{display:grid;grid-template-columns:1fr 1.3fr .8fr 1fr;gap:20px;border-top:1px solid #e8edef;padding-top:20px;margin-top:22px}
.co-report-metrics>div+div{border-left:1px solid #e2e3e7;padding-left:20px}.co-report-metrics small{display:block;font-size:13px;color:#68717d;margin-bottom:8px}
.co-report-metrics strong{font-size:30px;font-weight:650;line-height:1.45;font-variant-numeric:tabular-nums;letter-spacing:-.4px}.co-report-metrics .effect{font-size:36px;color:#303842}.co-report-metrics .interval{font-size:23px}.co-report-metrics .window{font-size:20px;letter-spacing:0}
.co-report-metrics .unit{font-size:12px;font-weight:400;color:#68717d;display:block;letter-spacing:0}.co-report-metrics .hint{font-size:12px;color:#68717d;margin-top:7px}
.co-report-limit{background:#fff8e8;border:1px solid #ead49d;border-left:3px solid #b47c15;border-radius:6px;padding:17px 20px;margin:18px 0 24px;color:#6a4708}.co-report-limit strong{display:block;font-size:15px}.co-report-limit p{font-size:14px;margin:5px 0 0}.co-report-limit.conflict{background:#fff1ef;border-color:#e7bbb7;color:#8f2e28}
.co-report-section{background:white;border:1px solid #e2e3e7;border-radius:9px;padding:24px;margin-top:20px}.co-report-charts{display:grid;grid-template-columns:1fr 1fr;gap:30px}.co-report-charts>div+div{border-left:1px solid #e8edef;padding-left:30px}
.co-bar-row{margin:17px 0}.co-bar-label{display:flex;justify-content:space-between;gap:12px;font-size:14px}.co-bar-label b{font-variant-numeric:tabular-nums}.co-bar-track{height:13px;background:#eef2f5;border-radius:3px;margin:8px 0 4px}.co-bar-fill{height:100%;border-radius:3px;background:#8aa0af}.co-bar-fill.treated{background:#303842}.co-bar-row small{color:#68717d;font-size:12px}.co-report-axis{display:flex;justify-content:space-between;color:#68717d;font-size:12px;border-top:1px solid #e2e3e7;padding-top:5px;margin-top:12px}
.co-interval-figure{width:100%;height:154px;position:relative;display:block}.co-ci-axis{position:absolute;left:0;right:0;top:86px;border-top:1px solid #e2e3e7}.co-ci-zero{position:absolute;top:28px;height:80px;border-left:1px dashed #8aa0af}.co-ci-range{position:absolute;top:72px;border-top:2px solid #303842}.co-ci-cap{position:absolute;top:65px;height:16px;border-left:1px solid #303842}.co-ci-point{position:absolute;top:68px;width:10px;height:10px;margin-left:-5px;background:#303842;border-radius:50%}.co-ci-label{position:absolute;top:100px;transform:translateX(-50%);font-size:12px;color:#68717d}.co-ci-label.low{top:35px}.co-ci-label.zero{top:125px}.co-automation-report table{width:100%;border-collapse:collapse;font-size:14px}.co-automation-report td,.co-automation-report th{padding:12px 9px;text-align:left;border-bottom:1px solid #e8edef;vertical-align:top}.co-automation-report th{color:#68717d;font-weight:500;background:#f8fafb}.co-report-scroll{overflow-x:auto}
.co-automation-report details{border-top:1px solid #e8edef;padding:14px 0;margin:0}.co-automation-report summary{cursor:pointer;font-size:14px;font-weight:550;color:#303842}.co-automation-report pre{font:12px/1.8 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#fafafa;border:1px solid #e2e3e7;border-radius:6px;padding:16px;max-height:420px;overflow:auto}.co-automation-report code{font-size:12px;overflow-wrap:anywhere}.co-automation-report a{color:#303842;text-decoration:underline;text-underline-offset:3px}
.co-report-facts{display:grid;grid-template-columns:1fr 1fr;gap:8px 30px}.co-report-facts div{padding:8px 0;border-bottom:1px solid #e8edef}.co-report-facts dt{font-size:12px;color:#68717d}.co-report-facts dd{margin:4px 0 0;font-size:14px}
@media(max-width:1100px){.co-report-metrics{grid-template-columns:1fr 1fr;gap:20px}.co-report-metrics>div:nth-child(3){border-left:0;padding-left:0}}
@media(max-width:700px){.co-report-lead{padding:20px 17px}.co-automation-report h1{font-size:24px!important}.co-report-lead .co-conclusion{font-size:21px!important}.co-report-metrics{gap:16px}.co-report-metrics>div+div{padding-left:14px}.co-report-metrics strong{font-size:26px}.co-report-metrics .effect{font-size:30px}.co-report-metrics .interval{font-size:19px}.co-report-metrics .window{font-size:18px}.co-report-charts,.co-report-facts{grid-template-columns:1fr}.co-report-charts>div+div{border-left:0;border-top:1px solid #e2e3e7;padding:22px 0 0}.co-report-section{padding:18px}.co-report-limit{padding:14px}.co-automation-report p{font-size:14px}}
@media print{.co-automation-report{max-width:none}.co-report-lead,.co-report-limit,.co-report-section{break-inside:avoid;box-shadow:none}.co-automation-report pre{max-height:none}}
"""

BASE_CSS = """
:root{--co-ink:#24272d;--co-muted:#68717d;--co-brand:#303842;--co-bg:#ffffff;--co-line:#e2e3e7}
[data-testid=stAppViewContainer],[data-testid=stMain],.stApp{background:var(--co-bg);color:var(--co-ink);font-family:'Segoe UI','Microsoft YaHei',sans-serif}
[data-testid=stMainBlockContainer]{max-width:1380px;padding:3.5rem 36px 48px;overflow-wrap:anywhere}
[data-testid=stHeader]{background:#ffffffe8}[data-testid=stToolbar]{opacity:.65}
[data-testid=stMarkdownContainer] p{font-size:16px;line-height:1.85}h1{font-size:29px!important;font-weight:650!important;line-height:1.5!important;letter-spacing:0!important}h2{font-size:22px!important;line-height:1.5!important}h3{font-size:18px!important;line-height:1.6!important}
[data-testid=stWidgetLabel] p{font-size:16px!important;font-weight:550;line-height:1.7!important}[data-testid=stCaptionContainer] p{font-size:13px!important;line-height:1.8!important;color:var(--co-muted)!important}
[data-testid=stButton] button,[data-testid=stFormSubmitButton] button,[data-testid=stDownloadButton] button{min-height:40px;border-radius:6px;font-size:14px;box-shadow:none}
[data-testid=stButton] button[kind=primary]:enabled,[data-testid=stFormSubmitButton] button[kind=primary]:enabled{background:var(--co-brand);border-color:var(--co-brand);color:white}
[data-testid=stButton] button:focus-visible,[data-testid=stDownloadButton] button:focus-visible{outline:3px solid #a6b5c8;outline-offset:2px}
[data-testid=stAlert]{border-radius:6px;font-size:14px}[data-testid=stAlert] p{font-size:16px!important}
[data-testid=stTextInput] input,[data-testid=stTextArea] textarea{font-size:15px}[data-testid=stMetricValue]{font-variant-numeric:tabular-nums;font-size:30px}
[data-testid=stSidebar]{background:#f3f4f6;border-right:1px solid var(--co-line)}[data-testid=stSidebarContent]{padding-left:0!important;padding-right:0!important}[data-testid=stSidebarUserContent]{padding:12px 14px 24px}
[data-testid=stSidebar] [data-testid=stButton] button{justify-content:flex-start;text-align:left;min-height:42px;border:0;background:transparent;color:#48505c;font-weight:500;border-radius:6px;padding:9px 12px}
[data-testid=stSidebar] [data-testid=stButton] button[kind=primary]{background:#eceef1;color:#303842;font-weight:650}
[data-testid=stSidebar] [data-testid=stButton] button:hover{background:#f0f1f3}[data-testid=stSidebar] [data-testid=stVerticalBlock]{gap:5px}
[data-testid=stSidebar] button [data-has-shortcut]{justify-content:flex-start!important;width:100%}.co-logo{position:relative;flex:none}.co-logo:before,.co-logo:after{content:'';position:absolute;width:18px;height:18px;left:5px;border:2px solid currentColor;transform:rotate(45deg) scale(.8);background:white}.co-logo:before{top:8px}.co-logo:after{top:2px}
.co-brand{display:flex;gap:9px;align-items:center;font-size:23px;font-weight:700;color:#303842;letter-spacing:-.6px;margin:0 5px 2px}.co-logo{width:29px;height:29px;display:inline-grid;place-items:center}.co-brand-sub{font-size:10px;color:#68717d;letter-spacing:1.25px;margin:0 0 18px 44px}.co-navcap{font-size:12px;color:#68717d;margin:18px 8px 7px}.co-status{font-size:12px;line-height:1.8;color:#68717d;border-top:1px solid var(--co-line);padding:15px 5px;margin-top:16px}.co-status small{display:block}
.co-top{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:0 0 18px;border-bottom:1px solid var(--co-line);margin-bottom:22px}.co-top strong{font-size:16px}.co-top small{color:var(--co-muted);font-size:13px;margin-left:12px}.co-pill{background:#eef0f3;color:#46646c;border-radius:4px;font-size:12px;padding:5px 9px;white-space:nowrap}
.co-research-context{font-size:13px;line-height:1.8;margin-bottom:20px;color:#68717d}.co-research-context strong{color:#24272d;font-weight:550}.co-identity{display:block;font-size:12px;color:#68717d}
.co-welcome h1{font-size:32px!important;margin:3px 0 8px!important}.co-welcome p{font-size:15px;color:#68717d;margin:0 0 24px;line-height:1.85}.co-kicker{font-size:12px;color:var(--co-brand);font-weight:650;letter-spacing:.5px}
[class*="st-key-panel_"],.co-preview{background:#fff;border:1px solid var(--co-line);border-radius:9px;padding:23px;box-shadow:none}
.st-key-panel_start_data,.st-key-panel_start_example{border-top:2px solid #303842;min-height:230px}
.co-section-heading{margin:16px 0 14px;font-size:19px;font-weight:600}.co-empty{padding:24px 0;color:#68717d;font-size:14px}.co-small-label{font-size:12px;color:#68717d}.co-task-row{padding:16px 0;border-bottom:1px solid #e5ecef}.co-task-row strong{font-size:15px}.co-task-row p{margin:5px 0;color:#68717d;font-size:13px}.co-task-row a{color:#303842;text-decoration:none}.co-task-row a:hover{text-decoration:underline}
.co-badge{display:inline-block;font-size:12px;padding:2px 8px;border-radius:4px;line-height:1.8;background:#edf2f4;color:#49606d}.co-badge.positive{background:#eaf5ef;color:#17643d}.co-badge.warning{background:#fff3d9;color:#855a08}.co-badge.danger{background:#fceeed;color:#a3312b}
.co-preview header{display:flex;align-items:center;justify-content:space-between;gap:12px}.co-preview p{color:#68717d}.co-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.co-kpis b{font-size:25px}.co-kpis small{display:block;color:#68717d;font-size:12px}.co-bars{height:150px;display:flex;align-items:flex-end;gap:12px;border-bottom:1px solid #e2e3e7;margin:18px 0}.co-bin{flex:1;text-align:center}.co-bin div{background:#303842;border-radius:3px 3px 0 0}.co-bin small{font-size:12px;color:#68717d}.co-note{padding:12px 15px;background:#f3f4f6;border-left:3px solid #303842;font-size:14px;color:#4a5665}
.flow,.co-steps{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:15px 0 24px}.flow span,.co-stage{font-size:13px;color:#68717d;padding:7px 10px}.flow .active,.co-stage.active{background:#eceef1;color:#303842;border-radius:5px}.co-stage b{margin-right:7px}.co-steps i{height:1px;width:24px;background:#e2e3e7}
.co-kv div{display:grid;grid-template-columns:120px 1fr;gap:15px;padding:10px 0;border-bottom:1px solid #e5ecef}.co-kv dd{margin:0}.co-paper{background:#fff;padding:28px;border:1px solid #e2e3e7;border-radius:9px}.co-paper-metrics{display:flex;gap:30px;flex-wrap:wrap}.co-paper-metrics strong{display:block;font-size:30px}.co-paper-metrics small{color:#68717d}
[data-testid=stFileUploaderDropzone]{background:#fafafa;border:1px dashed #b7bec8;border-radius:7px}[data-testid=stChatMessage]{border-radius:8px;background:#fff}
.st-key-phone_nav{display:none}.co-research-context code{font-size:11px}[data-stale=true] .co-automation-report,[data-stale=true] .co-research-context{visibility:hidden}
@media(min-width:900px){[data-testid=stSidebar][data-collapsed=false]{width:242px!important;min-width:242px!important;max-width:242px!important}}
@media(max-width:768px){[data-testid=stMainBlockContainer]{padding:3.5rem 16px 30px}.co-welcome h1{font-size:27px!important}.co-top{flex-wrap:wrap;gap:8px}.co-top small{display:none}.co-top strong{font-size:14px}.co-pill{font-size:11px}.co-brand{font-size:22px}[class*="st-key-panel_"],.co-preview{padding:18px}.co-kv div{grid-template-columns:90px 1fr}.st-key-phone_nav{display:block}.co-top .co-pill{white-space:normal}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
"""


def apply_theme():
    import streamlit as st
    st.html('<style>'+BASE_CSS+REPORT_CSS+'</style>')


def badge(text, status=''):
    from html import escape
    tone = 'positive' if status in ('completed','succeeded','verified') else 'danger' if status in ('blocked','cancelled','issue') else 'warning' if status in ('candidate','paused','interrupted','unknown') else ''
    return '<span class="co-badge '+tone+'">'+escape(str(text))+'</span>'


def brand_html():
    return '<div class="co-brand"><span class="co-logo" aria-hidden="true"></span>CausalOps</div><div class="co-brand-sub">RESEARCH WORKSPACE</div>'
