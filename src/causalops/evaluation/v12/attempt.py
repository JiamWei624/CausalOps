"""One fresh service workspace. Fixtures are prepared identically in both modes."""
import argparse,json,os
from pathlib import Path
from time import perf_counter
from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace,DesignError
from causalops.evaluation.v1.worker import save
from .inputs import CASES,dataset
from .capture import Advice,Metered,append


def run(folder,case,mode):
    frame,body=dataset(case)
    sc=CASES[case]
    workspace=AssistantWorkspace(GeneralWorkspace(folder/'work'))
    service=ResearchService(workspace)
    model=None
    sid=service.create_task(payload=frame.to_csv(index=False).encode(),name='synthetic.csv',title=case)
    out=dict(case=case,mode=mode,sid=sid,advice=None,flows=[],runs=[],receipts=[],probes={},errors=[])
    def snapshot():
        out['flows']=[]
        for f in reversed(service.flows(sid)):
            get=lambda k:service.output(f['id'],k) or {}
            plan=workspace.get_plan(f['plan_id']) if f.get('plan_id') else {}
            out['flows'].append(dict(id=f['id'],question=f['request']['question'],status=f['status'],route=get('route'),
                methods=[step['config'] for step in plan.get('plan',{}).get('steps',[])],plan=plan.get('id'),
                sha=plan.get('sha'),data=f['request']['data']['frame_sha'], readiness=get('readiness'),answer=get('answer'),
                execution=get('execution'),events=service.events(f['id'])))
        out['runs']=[]
        for ref in workspace.completed_runs(sid):
            row={k:ref[k] for k in ('plan_id','plan_sha','run_id','method','kind')}
            row['data']=ref['contract']['data_fingerprint']
            if row['kind']=='exploration':
                b=workspace.ex.load(ref['run_id'])
                row.update(claim=b['claim_level'],regression=b.get('regression'),numeric=b['summary']['numeric'],pairs=b['summary']['correlations'])
            out['runs'].append(row)
        with service.ws.connection() as c:
            out['receipts']=[json.loads(row[0]) for row in c.execute('select body from workflow_approvals')]
        save(folder/'observation.json',out)
    def bind():
        prior=service.contracts.latest(sid)
        service.contracts.save(sid,body,expected_sha=prior['sha'] if prior else None,human_confirmed=True)
    def turn(question,**params):
        append(folder/'operator.jsonl',dict(action='提交问题',question=question))
        return service.start(sid,question,**params)
    def approve(f,dispatch=True):
        if not f.get('plan_id') or f['status']!='awaiting_review':return False
        p=workspace.get_plan(f['plan_id'])
        append(folder/'operator.jsonl',dict(action='测试操作者审核当前版本',flow=f['id'],plan=p['id'],sha=p['sha']))
        try:service.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],
              expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,use_contract_facts=True,dispatch=dispatch)
        except DesignError as e:out['probes']['refusal']=str(e)
        return True
    def switch_metric():
        body.update(outcome='visitors',metric_label='每日访客数',metric_unit='人')
        bind()
    def seed(dispatch):
        f=turn('生成 orders 的描述统计分布报告。',mode='plan')
        approve(f,dispatch)
        return f
    start=perf_counter()
    try:
        bind()
        old=None
        if sc.operation in ('revise','stale','history','beyond'):
            if sc.operation=='revise':old=turn('制定 orders 的描述统计分布计划。',mode='plan')
            else:old=seed(sc.operation!='stale')
        if sc.operation=='history':
            out['probes']['first']=workspace.selected_run(sid)
            switch_metric()
            approve(turn('生成 visitors 的描述统计分布报告。',mode='plan'))
        out['before_runs']=[r['run_id'] for r in workspace.completed_runs(sid)]
        out['setup_flows']=[f['id'] for f in service.flows(sid)]
        if mode=='deepseek':
            model=Metered(os.environ['DEEPSEEK_API_KEY'],folder)
            service.model=model
            workspace.consent(sid,True,model.provider_config)
            # Separate pre-gate research judgment, never forwarded to the service or replaced by its gate.
            out['advice']=model.complete_json(system_instruction='给出独立的研究设计建议。用中文说明理由，action 用 execute、clarify、block、explain 或 revise，methods 使用统计方法标识；不需要方法时留空。只建议，不运行统计。',user_payload=dict(question=sc.question,context=sc.context,fields=list(frame.columns),shape=list(frame.shape),dictionary=body),output_schema=Advice.model_json_schema())
        if sc.operation=='revise':
            switch_metric()
            f=turn(sc.question,parent_flow_id=old['id'])
        elif sc.operation=='stale':
            body['research']['observation_period']='下一期；当前需要重新核对纳入范围'
            bind()
            f=turn(sc.question)
            try:service.gateway.execute(old['id'])
            except DesignError as e:out['probes']['stale']=str(e)
        elif sc.operation=='history':
            f=turn(sc.question,run_ids=[out['probes']['first']])
        elif sc.operation=='resume':
            f=service.begin(sid,sc.question)
            service.cancel(f['id'],human_confirmed=True)
            try:service.continue_flow(f['id'])
            except Exception as e:out['probes']['stop']=type(e).__name__
            out['probes']['stopped_runs']=len(workspace.completed_runs(sid))
            f=service.resume(f['id'],human_confirmed=True)
        else:f=turn(sc.question)
        out['target']=f['id']
        if sc.operation=='compute' or case in ('C04','C06','C15'):
            approve(service.flow(f['id']))
    except Exception as e:
        out['errors'].append(str(e)[:450].replace(os.environ.get('DEEPSEEK_API_KEY') or '\x00','[已移除]'))
    finally:
        out['seconds']=perf_counter()-start
        snapshot()
        if model:model.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('folder',type=Path);p.add_argument('case',choices=list(CASES));p.add_argument('mode',choices=['local','deepseek'])
    args=p.parse_args()
    if args.folder.exists() or Path(os.environ['CAUSALOPS_HOME']).resolve()!=(args.folder/'work').resolve():
        p.error('必须使用新建的隔离评测目录')
    args.folder.mkdir(parents=True)
    run(args.folder,args.case,args.mode)
