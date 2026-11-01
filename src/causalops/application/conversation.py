"""Frozen, same-task conversation links. References never authorize computation."""
from __future__ import annotations
import re
from causalops.assistant.service import check_question
from causalops.general.service import DesignError

def resolve_context(service,sid,question,parent_flow_id):
    original=check_question(question)
    if not parent_flow_id:return original,None
    parent=service.flow(parent_flow_id)
    if parent['session_id']!=sid:raise DesignError('所选对话不属于当前数据任务。')
    if parent['request']['data']!=service.data_binding(sid):raise DesignError('上文引用的数据版本已变化，请重新确认分析目标。')
    context={'parent_flow_id':parent_flow_id,'parent_question':parent['request']['question'],'parent_status':parent['status'],'parent_route':(service.output(parent_flow_id,'route') or {}).get('route'),'selected_direction':None}
    # Only an explicit ordinal selection can resolve a previously displayed option.
    selection=re.fullmatch(r'\s*(?:请)?(?:采用|选择|使用|按)?第?([一二三123])(?:个|项|条)?(?:分析)?(?:方向|建议|方案|问题)(?:继续|开展分析|制定计划|进行分析)?[。！!]?\s*',original)
    discovery=service.output(parent_flow_id,'discovery')
    if selection:
        if not discovery:raise DesignError('当前上文没有可选择的分析建议，请先生成建议。')
        ordinal={'一':1,'二':2,'三':3,'1':1,'2':2,'3':3}[selection.group(1)]
        if ordinal>len(discovery['directions']):raise DesignError('该序号超出当前分析建议范围。')
        if parent['request'].get('contract_ref')!=service.contracts.ref(sid):raise DesignError('数据口径已更新，请重新生成分析建议后选择。')
        option=discovery['directions'][ordinal-1]
        context['selected_direction']={'ordinal':ordinal,'title':option['title'],'question':option['question'],'fields':option['fields']}
        return check_question(option['question']),context
    return original,context

def public_context(request):
    value=request.get('conversation_ref')
    if not value:return None
    # Internal IDs and any saved answer prose are intentionally absent.
    return {k:value[k] for k in ('parent_question','parent_status','parent_route','selected_direction')}

def conversation_history(service,fid,limit=6):
    current=service.flow(fid);sid=current['session_id'];rows=[];seen={fid}
    parent=(current['request'].get('conversation_ref') or {}).get('parent_flow_id')
    while parent and len(rows)<limit:
        if parent in seen:raise DesignError('对话引用存在循环。')
        seen.add(parent);f=service.flow(parent)
        if f['session_id']!=sid:raise DesignError('历史对话不属于当前任务。')
        rows.append({'flow_id':parent,'question':f['request'].get('user_question',f['request']['question']),'status':f['status'],'answer':service.output(parent,'answer')})
        parent=(f['request'].get('conversation_ref') or {}).get('parent_flow_id')
    return list(reversed(rows))


def previous_plan(service,request):
    ref=request.get('conversation_ref')
    if not ref:return None
    parent=service.flow(ref['parent_flow_id'])
    if parent['request']['data']!=request['data']:raise DesignError('上文方案的数据来源不一致。')
    if not parent['plan_id']:return None
    plan=service.a.get_plan(parent['plan_id'])
    return {'objective':plan['plan']['objective'],'steps':plan['plan']['steps'],'state':plan['state'],'scope':'historical_candidate_not_authority'}
