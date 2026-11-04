"""Construct historical records by using the product's normal service and review entry points."""
import argparse,os
from pathlib import Path
from common import ROOT,CASES,bounded,save,inventory
from fixture_data import materials

def build(case,destination):
    folder=bounded(destination)
    folder.mkdir(parents=True,exist_ok=False)
    work=folder/'workspace'
    os.environ['CAUSALOPS_HOME']=str(work)
    from causalops.application.research_service import ResearchService
    from causalops.assistant.service import AssistantWorkspace
    from causalops.general.service import GeneralWorkspace
    frame,body=materials(case)
    service=ResearchService(AssistantWorkspace(GeneralWorkspace(work)))
    titles={'B01':'营销实验研究','B02':'顾客体验与消费研究','B03':'门店运营口径','B04':'订单研究历史报告','B05':'门店指标研究','B06':'门店时间窗研究'}
    sid=service.create_task(payload=frame.to_csv(index=False).encode(),name=titles[case]+'.csv',title=titles[case])
    service.contracts.save(sid,body,expected_sha=None,human_confirmed=True)
    def plan(question):
        f=service.start(sid,question,mode='plan')
        if f['status']!='awaiting_review':raise RuntimeError(f"初始化未进入待审态 {case} {f['status']}")
        return f
    def review(f):
        p=service.a.get_plan(f['plan_id'])
        service.review(f['id'],accept=True,expected_plan_id=p['id'],expected_plan_sha=p['sha'],
            expected_data_sha=f['request']['data']['frame_sha'],human_confirmed=True,use_contract_facts=True)
        if service.flow(f['id'])['status']!='completed':raise RuntimeError('初始化批准后未完成')
    if case=='B01':
        from causalops.sample_data.hillstrom import QUESTION
        review(plan(QUESTION))
    if case=='B02':
        review(plan('使用相关分析计算 satisfaction 与 spend 的 Pearson 相关系数，描述顾客满意度与购买金额的样本内关联。'))
    if case in ('B04','B05','B06'):
        review(plan('生成 orders 每日订单数的描述统计分布报告。'))
    if case=='B04':
        old=service.contracts.latest(sid)
        revised={**body,'outcome':'visitors','metric_label':'每日访客人数','metric_unit':'人'}
        service.contracts.save(sid,revised,expected_sha=old['sha'],human_confirmed=True)
        review(plan('生成 visitors 每日访客人数的描述统计分布报告。'))
    refs=service.a.completed_runs(sid)
    if case=='B02':
        corr=next(r for r in refs if r['method']=='correlation')
        stats=service.a.ex.load(corr['run_id'])['summary']['correlations']
        assert any({v['x'],v['y']}=={'satisfaction','spend'} and abs(v['pearson']-frame.satisfaction.corr(frame.spend))<1e-9 for v in stats)
    if case=='B04':assert len(refs)==2
    initial=dict(case_id=case,session_id=sid,upload_id=service.a.session(sid)['upload_id'],contract_sha=service.contracts.latest(sid)['sha'],
        selected_run=service.a.selected_run(sid) if refs else None,
        runs=[{'id':r['run_id'],'method':r['method'],'plan_id':r['plan_id'],'plan_sha':r['plan_sha'],'version':r['plan_version']} for r in refs],
        plans=[{'id':p['id'],'sha':p['sha'],'state':p['state'],'version':p['version']} for p in service.a.plans(sid)],
        flows=[f['id'] for f in service.flows(sid)],data=service.data_binding(sid))
    with service.ws.connection() as conn:conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    save(folder/'initial.json',initial)
    save(folder/'files.json',inventory(work))
    return initial
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case',choices=CASES);p.add_argument('destination',type=Path)
    args=p.parse_args();build(args.case,args.destination)
