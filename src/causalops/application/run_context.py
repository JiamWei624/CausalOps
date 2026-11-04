"""Resolve anaphora inside one research task. A selected report alone is not conversation history."""
import re
import json

LAST=re.compile(r'刚才|刚刚|上轮|上一轮|上次答复|前一轮|刚(?:核对|获得|生成)')
HISTORY=re.compile(r'之前.{0,6}报告|旧(?:的)?(?:结果|报告)|历史报告|先前.{0,6}报告')
PAGE=re.compile(r'已选|所选|选中|页面.{0,6}报告')
LATEST=re.compile(r'最新(?:的)?(?:报告|结果|运行)|最近生成')
THIS=re.compile(r'这个指标|这个结果|该结果|这项结果|这份报告')
def split_request(q):
    parts=re.split(r'[,，；;。]?\s*(?:然后|随后|接着|之后再|[；;，,]\s*(?=另拟|另外制定|另行制定)|[；;，,]\s*再|再(?=为|修改|调整|使用|用))',q,maxsplit=1)
    if len(parts)!=2:return None
    first,second=parts
    if not re.search('解释|查看|解读|回顾|核对|看|给出|报告',first) or not re.search('旧|已有|刚才|当前|已保存|历史|之前|上轮|已完成',first):return None
    if re.search('不要.{0,3}(新建|修改|制定)|仅咨询|只咨询',second):return None
    if re.search('计划|方案|窗口|观察期|OLS|线性回归',second,re.I):return first.strip(),second.strip()
    return None


def resolve(service,sid,q,parent,explicit_ids):
    refs=service.a.completed_runs(sid)
    ids=[r['run_id'] for r in refs]
    if not ids:return None
    selected=service.a.selected_run(sid)
    if explicit_ids is not None and any(rid in q and rid not in explicit_ids for rid in ids):
        return {'ids':[], 'reason':'范围待确认','error':'指定编号与选择的运行不一致，请确认要解读哪份报告。'}
    if explicit_ids is not None:return {'ids':list(explicit_ids),'reason':'显式选择'}
    mentions=[rid for rid in ids if rid in q]
    if mentions:return {'ids':mentions,'reason':'指定运行编号'}
    relevant=bool(LAST.search(q) or HISTORY.search(q) or PAGE.search(q) or LATEST.search(q) or THIS.search(q))
    if not relevant:return None
    from causalops.application.task_conclusions import source_dictionary
    prior=service.output(parent,'answer') if parent else None
    previous=list((prior or {}).get('run_ids',[]))
    if not previous and parent:
        previous=list((service.output(parent,'prior_answer') or {}).get('run_ids',[]))
    group=ids.copy()
    candidates=[]
    dates=re.findall(r'\d{4}-\d{2}-\d{2}',q)
    version=re.search(r'(?<![A-Za-z0-9])V(\d+)\b',q,re.I)
    matched=[]
    for ref in refs:
        dictionary,_=source_dictionary(service.a,sid,ref['run_id'])
        if version and ref['plan_version']!=int(version[1]):continue
        if dates and any(date not in (dictionary.get('metric_window') or '') for date in dates):continue
        candidates.append(ref['run_id'])
        names=[dictionary.get('metric_label'),dictionary.get('outcome'),dictionary.get('metric_window')]
        if any(n and (re.search(r'(?<![A-Za-z0-9_])'+re.escape(n)+r'(?![A-Za-z0-9_])',q,re.I) if n.isascii() else n in q) for n in names):
            matched.append(ref['run_id'])
    group=matched or candidates
    def choice(candidates,reason):
        candidates=list(dict.fromkeys(rid for rid in candidates if rid in group))
        if len(candidates)==1:return {'ids':candidates,'reason':reason}
        return {'ids':[],'reason':'范围待确认','error':'请确认所指的报告（运行编号或指标与窗口）：'+ '、'.join(x[:8] for x in (candidates or group)[:5])+'。'}
    if PAGE.search(q):return choice([selected],'页面选中')
    if LAST.search(q):return choice(previous or (group if len(group)==1 else []),'上一轮实际引用')
    if LATEST.search(q):
        # Execution receipts are chronological; plan version alone is not an execution timestamp.
        with service.ws.connection() as c:
            rows=c.execute('SELECT s.body FROM workflow_execution_snapshots s JOIN workflow_flows f ON f.id=s.flow_id WHERE f.session_id=? ORDER BY s.rowid DESC',(sid,)).fetchall()
        for row in rows:
            snapshot=json.loads(row[0])
            if not snapshot.get('completed'):continue
            recent=[rid for rid in snapshot.get('run_ids',[]) if rid in group]
            if recent:return choice(recent[-1:],'最近成功执行')
        return choice(group,'可识别的成功运行')
    if HISTORY.search(q):return choice(group,'指定历史报告')
    return choice([r for r in [selected,*previous] if r in group] or group,'页面与上一轮')


def asks_previous_status(q):
    previous=LAST.search(q) or re.search('本轮|这一轮|这轮',q)
    return bool((previous or re.search('现有数据|本次流程',q)) and re.search('哪一步|进度|状态|到哪|有没有完成|是否(?:已实际执行|完成)',q)
                and not re.search('新建|重新计算|另外制定|重新批准',q))


def previous_status(service,parent_id):
    flow=service.flow(parent_id)
    answer=service.output(parent_id,'answer')
    if answer and flow['status'] in ('completed','needs_clarification','blocked'):
        label='已完成' if flow['status']=='completed' else '尚需补充条件'
        return {**answer,'text':'上一流程'+label+'。'+answer.get('text',''),
                'source_flow_id':parent_id,'scope':'prior_flow_status'}
    plan=service.a.get_plan(flow['plan_id']) if flow.get('plan_id') else None
    labels={'awaiting_review':'等待人工审核','approved':'已批准','executing':'执行中','cancelled':'已停止',
            'rejected':'已放弃','failed':'执行失败','created':'已登记','executed':'统计已完成，解释待交付'}
    status=labels.get(flow['status'],flow['status'])
    note=' 方案 V'+str(plan['version'])+'。' if plan else ''
    return dict(source='已保存的研究流程状态',text='上一流程状态：'+status+'。'+note,
                facts=[],run_ids=[],citations=[],scope='prior_flow_status',source_flow_id=parent_id)

def review_preview(question):
    """Only a readback of the current candidate, never approval or a change."""
    return bool((re.search(r'(?:若|如果).{0,5}(?:尚未|仍未)批准.{0,18}阶段',question) or re.search('先给我看|查看|先说清|看看|核对哪些|展示|区别|差异|变化',question)
                 and re.search('新版|候选|待审|等我审核|新方案|需要核对',question) or re.search('为什[么麽]|为何',question) and re.search('重新批准|重新审[批核]',question))
                and not re.search('改为|换成|调整为|重新制定|新增|更换|新建',question))

def review_answer(service,parent):
    from causalops.application.conversation import previous_plan,plan_differences
    plan=service.a.get_plan(parent['plan_id'])
    contract=(service.contracts.bound(parent) or {}).get('body',{})
    scope=parent['request'].get('analysis_scope') or {}
    method='、'.join(step['config']['method'] for step in plan['plan']['steps'])
    outcome=scope.get('outcome') or contract.get('outcome') or '待核对'
    window=scope.get('metric_window') or contract.get('metric_window') or '未登记'
    before=previous_plan(service,parent['request'])
    note='没有可对照的前序方案。'
    if before:
        changes=plan_differences(before,plan['plan'])
        note='与前序方案的差异：'+('、'.join(row['项目'] for row in changes) or '无')+'。'
        prev=(parent['request'].get('conversation_ref') or {}).get('parent_flow_id')
        if prev:
            old=(service.contracts.bound(service.flow(prev)) or {}).get('body',{})
            note+=f"之前登记的指标为 {old.get('outcome') or '未登记'}，窗口为 {old.get('metric_window') or '未登记'}。"
    text=(f"待审方案 V{plan['version']}。研究目标：{plan['plan']['objective']}。方法：{method}。"
          f"分析单位：{contract.get('analysis_unit') or '尚待确认'}。目标指标：{outcome}；窗口：{window}。{note}批准只对特定样本、方案和口径版本有效。"
          "请核对这些内容后在原方案审核。本次查看没有批准或执行。")
    return dict(source='本地待审方案记录',text=text,facts=[],citations=[],run_ids=[],review_owner=parent['id'],scope='review_preview')
