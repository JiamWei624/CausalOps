"""Deterministic first-use helpers; no model has authority to invoke approvals."""
from __future__ import annotations
from causalops.assistant.service import profile
from causalops.general.service import DesignError
BASIC_QUESTION='请生成当前表的基础分析报告（descriptive）：数据质量、缺失、数值分布与类别频数。'

def overview(frame):
    p=profile(frame);safe=[x for x in p['fields'] if not x['likely_identifier']]
    return {'rows':p['rows'],'columns':p['columns'],'numeric':sum(x['numeric'] for x in safe),'other':sum(not x['numeric'] for x in safe),'missing_cells':sum(x['missing_n'] for x in p['fields']),'text':f"这张表有 {p['rows']:,} 行、{p['columns']} 个字段，缺失单元格共 {sum(x['missing_n'] for x in p['fields']):,} 个。字段类型只能说明存储形式，不能证明每一行的业务含义。"}

def start_basic_report(a,sid,*,user_requested=False):
    if user_requested is not True:raise DesignError('基础报告须由使用者点击按钮启动。')
    from causalops.application.research_service import ResearchService
    from causalops.application.background import BackgroundJobs,ACTIVE
    s=ResearchService(a);jobs=BackgroundJobs(s)
    for f in s.flows(sid):
        if f['request']['question']!=BASIC_QUESTION or f['request']['data']!=s.data_binding(sid) or f['request'].get('contract_ref')!=s.contracts.ref(sid):continue
        existing=[j for j in jobs.jobs(sid) if j['flow_id']==f['id']]
        if any(j['status'] in ACTIVE for j in existing):return {'flow_id':f['id'],'reused':True}
        if f['status']=='completed' and s.output(f['id'],'execution'):
            from causalops.assistant.runtime import execution_source_sha
            import json
            with s.ws.connection() as c:receipt=c.execute('SELECT body FROM workflow_approvals WHERE flow_id=?',(f['id'],)).fetchone()
            if receipt and json.loads(receipt[0])['source_sha']==execution_source_sha():return {'flow_id':f['id'],'reused':True}
    jobs.capacity();f=s.start(sid,BASIC_QUESTION,mode='plan');p=a.get_plan(f['plan_id'])
    if not p['plan']['steps'] or any(x['tool']!='exploration' or x['config'].get('method')!='descriptive' for x in p['plan']['steps']):raise DesignError('一键报告仅允许描述统计，其他方法须单独审核。')
    s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,confirmations={},dispatch=False)
    jobs.submit(f['id']);return {'flow_id':f['id'],'reused':False}
