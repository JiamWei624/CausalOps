"""Chat presentation only: local fonts, one reading grid, lossless saved-text views."""
from html import escape
import re

FONT_STACK = '-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei UI","Microsoft YaHei","PingFang SC",sans-serif'
READING_WIDTH = 720

def display_parts(answer):
    text=answer.get('text','本轮未保存可核验的回复。')
    if answer.get('scope')!='verified_automation_report':return [('markdown',text)]
    # Reorder existing paragraphs only. No new estimate, conclusion or source.
    parts=text.split('\n\n');lead=None
    for i,p in enumerate(parts):
        plain=p.replace('**','')
        if plain.startswith(('绝对差（','描述性差异（')):lead=i;break
    ordered=([('lead',parts[lead].replace('**',''))] if lead is not None else [])
    ordered += [('markdown',p.replace('**','')) for i,p in enumerate(parts) if i!=lead]
    return ordered

def lead_html(text):
    value=re.search(r'[-+]?\d+(?:\.\d+)?\s*个百分点',text)
    if not value:return '<p class="co-result-lead">'+escape(text)+'</p>'
    return '<p class="co-result-lead">'+escape(text[:value.start()])+'<span class="co-result-value">'+escape(value.group())+'</span>'+escape(text[value.end():])+'</p>'

CHAT_CSS=r'''
:root{--co-chat-font:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei UI","Microsoft YaHei","PingFang SC",sans-serif;--co-chat-width:720px;--co-chat-ink:#24272d;--co-chat-muted:#596270}
[data-testid=stHeader]{height:44px;background:#fff}
[data-testid=stMainBlockContainer]{max-width:1540px;padding:52px 28px 12px}
[data-testid=stBottomBlockContainer]{max-width:1540px!important;padding:0 28px 12px!important}
.st-key-chat_reading,.st-key-chat_composer_area{width:100%;max-width:var(--co-chat-width);margin-inline:auto}
.st-key-chat_composer_area{padding:4px 0 8px;background:#fff}
[class*="st-key-chat_scroll_"],.st-key-chat_panel_scroll{height:clamp(220px,calc(100dvh - 360px),700px)!important;min-height:0!important;max-height:none!important;flex:0 0 auto!important}
[class*="st-key-chat_scroll_"]{row-gap:26px!important}
.st-key-chat_reading [data-testid=stChatMessage]{background:transparent;padding:0;border-radius:0;gap:0;margin:0 auto;width:100%;max-width:none;font-family:var(--co-chat-font);flex:0 0 auto}
[data-testid=stChatMessageAvatarUser],[data-testid=stChatMessageAvatarAssistant]{display:none}
.st-key-chat_reading [data-testid=stChatMessageContent]{width:100%;min-width:0;font-family:var(--co-chat-font)}
.st-key-chat_reading [data-testid=stChatMessageContent] [data-testid=stMarkdownContainer]{margin-bottom:0!important}
.st-key-chat_reading [data-testid=stChatMessageContent]>[data-testid=stVerticalBlock]{gap:10px!important}
.st-key-chat_reading [data-testid=stChatMessage]:has([data-testid=stChatMessageAvatarUser]){width:fit-content;max-width:85%;margin:0 0 0 auto;padding:10px 14px;background:#f0f1f3;border-radius:16px}
.st-key-chat_reading [data-testid=stChatMessage]:has([data-testid=stChatMessageAvatarUser]) p{font-family:var(--co-chat-font)!important;font-size:16px!important;font-weight:400;line-height:1.6!important;margin:0!important}
[class*="st-key-chat_body_"]{font-family:var(--co-chat-font);font-size:16px;line-height:1.6;gap:8px!important}
[class*="st-key-chat_body_"] :is(p,li,td,th,a,strong,em,blockquote){font-family:var(--co-chat-font)!important}
[class*="st-key-chat_body_"] p{font-size:16px!important;font-weight:400;line-height:1.6!important;margin:0 0 10px!important}
[class*="st-key-chat_body_"] p:last-child{margin-bottom:0!important}
[class*="st-key-chat_body_"] :is(h1,h2){font-family:var(--co-chat-font)!important;font-size:21px!important;line-height:1.4!important;font-weight:600!important;margin:20px 0 8px!important;padding:0!important}
[class*="st-key-chat_body_"] :is(h3,h4){font-family:var(--co-chat-font)!important;font-size:18px!important;line-height:1.45!important;font-weight:600!important;margin:18px 0 8px!important;padding:0!important}
[class*="st-key-chat_body_"] :is(ul,ol){margin:4px 0 12px;padding-left:24px}
[class*="st-key-chat_body_"] li{font-size:16px;line-height:1.6;margin:3px 0;padding:0}
[class*="st-key-chat_body_"] li p{margin:0!important}
[class*="st-key-chat_body_"] strong{font-weight:500!important}
[class*="st-key-chat_body_"] a{color:#475a73;text-underline-offset:3px}
[class*="st-key-chat_body_"] blockquote{border-left:2px solid #d5d9df;margin:12px 0;padding:0 0 0 16px;color:#596270}
[class*="st-key-chat_body_"] code{font-family:"Cascadia Code",Consolas,"SFMono-Regular",monospace;font-size:14px}
[class*="st-key-chat_body_"] pre{padding:12px 14px;border:1px solid #e5e7eb;border-radius:8px;line-height:1.55}
[class*="st-key-chat_body_"] table{width:100%;font-size:15px;border-collapse:collapse;margin:8px 0 12px;font-variant-numeric:tabular-nums}
[class*="st-key-chat_body_"] :is(td,th){font-size:15px;line-height:1.6;padding:7px 8px;border:0;border-bottom:1px solid #e5e7eb;background:transparent;font-weight:400}
[class*="st-key-chat_body_"] th{color:#596270;font-weight:500}
[class*="st-key-chat_body_"] .co-result-lead{font-size:16px!important;line-height:1.65!important;margin:0 0 12px!important}
.co-result-value{font-size:24px;font-weight:500;line-height:1.35;font-variant-numeric:tabular-nums;white-space:nowrap}
.co-chat-head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 0 8px;margin:0;border-bottom:1px solid #eceef1;font-family:var(--co-chat-font)}
.co-chat-head strong{font-family:var(--co-chat-font);font-size:16px;font-weight:500;line-height:1.5;white-space:nowrap;text-overflow:ellipsis;overflow:hidden;flex:1;min-width:0}
.co-chat-context{font-family:var(--co-chat-font);font-size:13px;line-height:1.5;color:#596270;max-width:43%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:none}
.co-chat-welcome{max-width:var(--co-chat-width);margin:auto;padding:24px 0}
.co-chat-welcome h1{font-family:var(--co-chat-font)!important;font-size:22px!important;font-weight:600!important;line-height:1.4!important;margin:0 0 12px!important}
.co-chat-welcome p{font-family:var(--co-chat-font);font-size:16px;line-height:1.6;color:#596270;margin:0 0 10px}
.st-key-chat_artifacts{border-left:1px solid #eceef1;padding-left:20px;font-family:var(--co-chat-font)}
.st-key-chat_artifacts [data-testid=stMarkdownContainer] p{font-family:var(--co-chat-font)!important;font-size:14px!important;line-height:1.6!important}
.st-key-chat_artifacts h3{font-family:var(--co-chat-font)!important;font-size:18px!important;font-weight:600!important;margin:0 0 12px!important}
.st-key-chat_artifacts button p{font-family:var(--co-chat-font)!important;font-size:14px!important;font-weight:400}
[data-testid=stSidebar] :is(button p,input,[data-testid=stCaptionContainer] p){font-family:var(--co-chat-font)!important}
[data-testid=stSidebarHeader]{height:44px;min-height:44px;padding-block:6px}
[data-testid=stSidebar] .co-brand{font-family:var(--co-chat-font);font-size:20px;font-weight:600}
[class*="st-key-chat_session_"] button{min-height:38px!important;padding:7px 10px!important}
[class*="st-key-chat_session_"] button p{font-size:14px!important;line-height:1.45!important;font-weight:400!important;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
[class*="st-key-chat_session_"] button[kind=primary]{background:#e9ebee!important;box-shadow:none;color:#24272d!important}
.st-key-chat_composer_area :is(button p,textarea,[data-testid=stCaptionContainer] p){font-family:var(--co-chat-font)!important}
.st-key-chat_composer_area [data-testid=stChatInput]{height:80px!important;min-height:80px!important;max-height:80px!important;border-radius:18px;background:#f4f4f5;border:1px solid #e2e3e7}
.st-key-chat_composer_area textarea{font-size:16px!important;line-height:1.6!important;height:44px!important;min-height:44px!important;max-height:44px!important;overflow-y:auto!important}
.st-key-chat_composer_area button{min-height:32px!important}
.st-key-chat_composer_area [data-testid=stCaptionContainer] p{font-size:12px!important;line-height:1.5!important}
.st-key-chat_identity [data-testid=stButton] button{min-height:36px}
[data-testid=stSidebar] [data-testid=stCaptionContainer],.st-key-chat_reading [data-testid=stCaptionContainer],.st-key-chat_artifacts [data-testid=stCaptionContainer],.st-key-chat_composer_area [data-testid=stCaptionContainer]{opacity:1!important}
.st-key-chat_reading [data-testid=stCaptionContainer] p,.st-key-chat_artifacts [data-testid=stCaptionContainer] p{font-family:var(--co-chat-font)!important;color:#596270!important;font-size:13px!important;line-height:1.5!important}
[class*="st-key-chat_source_"] [data-testid=stExpander], [class*="st-key-chat_source_"] details{border:0;border-radius:0}
[class*="st-key-chat_source_"] summary{min-height:28px;padding:3px 0}
[class*="st-key-chat_source_"] summary p{font-family:var(--co-chat-font)!important;font-size:13px!important;font-weight:400!important;line-height:1.5!important;color:#596270}
[data-stale=true] .st-key-chat_identity,[data-stale=true] .st-key-chat_messages,[data-stale=true] .st-key-chat_artifacts,[data-stale=true] .st-key-chat_focused{visibility:hidden}
@media(max-width:1140px){[data-testid=stColumn]:has(.st-key-chat_composer_spacer){display:none}}
@media(max-width:768px){[data-testid=stMainBlockContainer]{padding:52px 14px 12px}[data-testid=stBottomBlockContainer]{padding:0 14px 12px!important}.co-chat-head{flex-wrap:wrap;gap:2px}.co-chat-head strong{flex-basis:100%;font-size:15px}.co-chat-context{max-width:100%;font-size:12px}.st-key-chat_artifacts{border-left:0;border-top:1px solid #eceef1;padding:12px 0}.co-result-value{font-size:22px}}
'''
