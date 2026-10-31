"""Add run-bound, validated discussion to exported reports without executing new statistics."""
from html import escape
import json,re

def attach_discussion(html,events,run_id,library):
    items=[];question=''
    for event in events:
        if event['kind']=='user':question=event['body']['question']
        if event['kind']!='answer':continue
        answer=event['body'];facts=answer.get('facts',[])
        scope=set(answer.get('run_ids',[])) or {f['run_id'] for f in facts}
        if run_id not in scope:continue
        if len(scope)>1:continue  # Cross-run discussions require a comparison report, not a single-run appendix.
        sources=[]
        saved={r['card_id']:r for r in answer.get('method_provenance',[])}
        for cid in answer.get('citations',[]):
            if cid in saved:records=saved[cid]['sources']
            else:
                card=next((c for c in library.cards if c['card_id']==cid),None)
                records=[library.catalog['sources'][v] for v in card['source_ids']] if card else []
            for source in records:sources.append('<li><a href="'+escape(source['url'],quote=True)+'">'+escape(source['title'])+'</a>（'+escape(source['access_scope'])+'）</li>')
        text=escape(answer['text']).replace('\n','<br>');text=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',text)
        items.append('<article style="border-left:3px solid #176b65;padding:12px 20px;margin:24px 0"><h3>'+escape(question)+'</h3><p>回答来源：'+escape(answer['source'])+'；不新增计算，按原运行解释等级讨论。</p><p>'+text+'</p><ul>'+''.join(dict.fromkeys(sources))+'</ul><details><summary>展开完整引用与精确数值</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+escape(json.dumps(facts,ensure_ascii=False,indent=2))+'</pre></details></article>')
    if not items:return html
    section='<section><h2>围绕本次结果的持续讨论与结论解释</h2><p>以下保留本地证据或已通过引用校验的模型解释。涉及多项运行时，以每条引用的运行编号区分；不把讨论变成额外估计或新的审批。</p>'+''.join(items)+'</section>'
    return html.replace('</html>',section+'</html>') if '</html>' in html else html+section
