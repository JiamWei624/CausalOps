"""Run one scripted operator through the public local service, in a fresh workspace."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

from .cases import TASKS, prepare


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False), encoding='utf8')


class Recorder:
    def __init__(self, root, case, commit):
        self.path = root/'events.jsonl'
        self.case, self.commit, self.sid = case, commit, None
        self.seq = 0
        self.seen = {}

    def event(self, name, *, status='成功', elapsed=None, when=None, flow=None, plan=None, run=None, **detail):
        self.seq += 1
        item = dict(任务=self.case, 尝试=self.path.parent.name, 会话=self.sid, 提交=self.commit, 模式='本地规则',
                    时间=when or datetime.now(timezone.utc).isoformat(), 顺序=self.seq, 事件=name, 状态=status,
                    流程=flow, 方案版本=plan, 运行=run, 耗时秒=elapsed, 详情=detail)
        with self.path.open('a',encoding='utf8') as out:
            out.write(json.dumps(item, ensure_ascii=False)+'\n')

    def sync(self, service):
        """Keep domain timestamps, sequence and measured start/end intervals; no model payloads."""
        names={'route_intent':'识别研究意图','draft_plan':'研究方案生成','review':'用户批准指定方案',
               'execute_plan':'统计执行','answer_results':'结果解释生成','answer_method':'方法解释'}
        for f in reversed(service.flows(self.sid)):
            fid=f['id']
            events=service.events(fid)
            starts={}
            for e in events:
                node, state = e['node'], e['status']
                if state=='started': starts[node]=datetime.fromisoformat(e['created'])
                if e['seq']<=self.seen.get(fid,0):continue
                self.seen[fid]=e['seq']
                if node not in names or (node=='review' and state!='approved'):continue
                elapsed=None
                if state!='started' and node in starts:
                    elapsed=(datetime.fromisoformat(e['created'])-starts[node]).total_seconds()
                plan=service.a.get_plan(f['plan_id']) if f.get('plan_id') else {}
                run_ids=(service.output(fid,'execution') or {}).get('run_ids',[]) if node in ('execute_plan','answer_results') and state=='completed' else []
                suffix={'started':'开始','completed':'完成','failed':'失败'}.get(state,'')
                self.event(names[node]+suffix,flow=fid,plan=plan.get('version'),when=e['created'],elapsed=elapsed,
                           status='阻断' if node=='execute_plan' and state=='completed' and not (service.output(fid,'execution') or {}).get('completed') else '失败' if state=='failed' else '开始' if state=='started' else '成功',
                           run=run_ids or None,领域序号=e['seq'])


class OfflineFault:
    base_url='https://api.deepseek.com'
    last_telemetry={}
    calls=0

    def complete_json(self, **kwargs):
        self.calls+=1
        raise ConnectionError('模拟连接中断')


def execute(case, root, archive, commit):
    from causalops.application.research_service import ResearchService
    from causalops.assistant.service import AssistantWorkspace
    from causalops.general.service import GeneralWorkspace, DesignError
    from causalops.application.task_conclusions import build_task_conclusion
    from causalops.ui.assistant_app import make_report

    rec=Recorder(root,case,commit)
    started=perf_counter()
    obs=dict(case=case, turns=[], approvals=[], runs=[], errors=[], probes={}, reports=[])
    rec.event('任务开始')
    a=AssistantWorkspace(GeneralWorkspace(root/'work'))
    s=ResearchService(a)
    def turn(question, **opts):
        rec.event('用户提交研究问题',请求=question)
        n=len(s.flows(sid))
        try:
            return s.start(sid,question,**opts)
        finally:
            rec.sync(s)
            flows=s.flows(sid)
            if len(flows)>n:obs['turns'].append(flows[0]['id'])

    def approve(f, dispatch=True):
        p=a.get_plan(f['plan_id'])
        try:
            return s.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],
                expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,
                use_contract_facts=True,dispatch=dispatch)
        finally:rec.sync(s)

    q=TASKS[case]['question']
    try:
        data,sep,body=prepare(case,archive)
        t=perf_counter()
        sid=s.create_task(payload=data,name='public-fixture.csv',title=case,separator=sep)
        rec.sid=sid
        rec.event('数据成功加载',elapsed=perf_counter()-t)
        s.contracts.save(sid,body,expected_sha=None,human_confirmed=True)
        if case in ('T01','T02','T06','T09'):
            from causalops.sample_data.hillstrom import QUESTION
            f=turn(QUESTION if case=='T09' else q)
            if f.get('plan_id'):approve(f)
            if case=='T09' and a.completed_runs(sid):
                rid=a.selected_run(sid)
                turn('解释当前报告，两周访问率相差多少个百分点？',run_ids=[rid])
                turn('据此能说明明年的净利润增加多少吗？',run_ids=[rid])
        elif case=='T03':
            turn(q)
        elif case in ('T04','T05'):
            try:
                f=turn(q)
                if f.get('plan_id'):approve(f)
                blocked=s.output(f['id'],'execution') or {}
                for task in blocked.get('tasks',[]):
                    if task['state']=='blocked':rec.event('方法或字段校验失败',status='阻断',flow=f['id'],原因=task['result'].get('error'))
            except DesignError as e:
                obs['probes']['refusal']=str(e)
                rec.event('方法或字段校验失败',status='阻断',原因=str(e))
        elif case=='T07':
            f=turn(TASKS['T02']['question'])
            obs['probes']['before']=[p['sha'] for p in a.plans(sid)]
            turn(q,parent_flow_id=f['id'])
            obs['probes']['after']=[p['sha'] for p in a.plans(sid)]
        elif case=='T08':
            f=turn(q)
            approve(f,dispatch=False)
            original=a.get_plan(f['plan_id'])
            body['outcome']='z'
            s.contracts.save(sid,body,expected_sha=s.contracts.latest(sid)['sha'],human_confirmed=True)
            try:s.gateway.execute(f['id'])
            except DesignError as e:
                obs['probes']['stale']=str(e)
                rec.event('旧批准校验失败',status='阻断',flow=f['id'],plan=original['version'])
            obs['probes']['before_new_approval']=len(a.completed_runs(sid))
            updated=turn('修改计划：使用 OLS 分析 x 与新结果 z 的关联。',parent_flow_id=f['id'])
            obs['probes']['original_unchanged']=a.get_plan(f['plan_id'])['plan']==original['plan']
            if updated.get('plan_id') and updated['plan_id']!=original['id']:
                rec.event('研究方案修订',flow=updated['id'],plan=a.get_plan(updated['plan_id'])['version'])
                approve(updated)
        elif case=='T10':
            fault=OfflineFault()
            s.model=fault
            a.consent(sid,True)
            try: turn(q)
            except Exception as e:
                obs['probes']['fault']=type(e).__name__
                rec.event('故障发生',status='失败',类型=type(e).__name__)
            obs['probes']['calls']=fault.calls
            obs['probes']['before_recovery_runs']=len(a.completed_runs(sid))
            s=ResearchService(a)
            f=turn(q)
            if f['status']=='completed':
                rec.event('故障恢复',flow=f['id'],方式='操作者明确改用本地模式')
    except FileNotFoundError:
        if case in ('T06','T09') and (not archive or not Path(archive).is_file()):
            obs['unavailable']='缺少指定公开数据'
        else:obs['errors'].append('文件读取失败')
    except Exception as e:
        obs['errors'].append(type(e).__name__+': '+str(e)[:500])
        rec.event('故障发生',status='失败',类型=type(e).__name__)
    finally:
        if rec.sid:
            rec.sync(s)
            obs['flows']=[]
            for f in reversed(s.flows(rec.sid)):
                get=lambda k:s.output(f['id'],k) or {}
                plan=a.get_plan(f['plan_id']) if f.get('plan_id') else {}
                obs['flows'].append(dict(id=f['id'],status=f['status'],route=get('route').get('route'),
                    reason=get('route').get('reason'),plan_id=f.get('plan_id'),plan_sha=plan.get('sha'),
                    data=f['request']['data']['frame_sha'],steps=(plan.get('plan') or {}).get('steps',[]),
                    audit=get('research_quality').get('audit',{}).get('checks',[]), readiness=get('readiness'),
                    answer={k:v for k,v in get('answer').items() if k in ('text','facts','run_ids','citations','scope','source')},
                    execution=get('execution')))
            with s.ws.connection() as c:
                obs['approvals']=[json.loads(row[0]) for row in c.execute('select body from workflow_approvals')]
            for ref in a.completed_runs(rec.sid):
                rid=ref['run_id']
                row=dict(ref)
                if ref['kind']=='exploration':
                    b=a.ex.load(rid)
                    row.update(summary={k:b['summary'][k] for k in ('numeric','correlations','row_count')},regression=b.get('regression'),claim=b['claim_level'])
                else:
                    b,_=a.ws.bundle(rid)
                    row.update(ci=list(b.estimate.confidence_interval) if b.estimate and b.estimate.confidence_interval else [],sample_size=b.estimate.sample_size if b.estimate else None,estimate=b.estimate.estimate if b.estimate else None,claim=b.claim_level.value)
                obs['runs'].append(row)
                report=make_report(a,ref,rec.sid,build_task_conclusion(a,rec.sid,rid))
                path=root/(rid+'.html');path.write_text(report,encoding='utf8')
                obs['reports'].append(dict(run=rid,file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        obs['seconds']=perf_counter()-started
        save(root/'observations.json',obs)
        rec.event('任务失败' if obs['errors'] else '任务结束待评分',elapsed=obs['seconds'],status='失败' if obs['errors'] else '完成')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('case',choices=list(TASKS));parser.add_argument('root',type=Path)
    parser.add_argument('commit');parser.add_argument('--archive')
    args=parser.parse_args()
    expected = (args.root/'work').resolve()
    if (os.environ.get('CAUSALOPS_EVAL_CHILD')!='1' or args.root.exists()
            or Path(os.environ.get('CAUSALOPS_HOME','.')).resolve()!=expected):
        parser.error('使用独立评测入口创建新的尝试目录')
    args.root.mkdir(parents=True)
    execute(args.case,args.root,args.archive,args.commit)
