"""Demonstrate supported changes through the normal service, with explicit test-operator reviews."""
import argparse, json
from pathlib import Path
import pandas as pd
from causalops.application.research_service import ResearchService
from causalops.application.task_conclusions import source_dictionary
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import GeneralWorkspace, DesignError


def main():
    p=argparse.ArgumentParser()
    p.add_argument('output',type=Path)
    root=p.parse_args().output
    root.mkdir(parents=True,exist_ok=False)
    service=ResearchService(AssistantWorkspace(GeneralWorkspace(root/'workspace')))
    frame=pd.DataFrame({'day':pd.date_range('2026-01-01',periods=25).strftime('%Y-%m-%d'),
                        'sales':[i+(i%3) for i in range(25)],'traffic':[21+(i*7)%19 for i in range(25)]})
    sid=service.create_task(payload=frame.to_csv(index=False).encode(),name='daily-example.csv')
    service.contracts.save(sid,dict(analysis_unit='门店日',time='day',outcome='sales',metric_label='销量',metric_unit='件',
        metric_window='全期',predictors=['traffic'],fields=[dict(field='traffic',meaning='当日到店人次',unit='人次')],
        method_facts={'ols':{'independent_rows_reviewed':True}}),human_confirmed=True)
    rows=[]
    def submitted(question, parent=None):
        f=service.start(sid,question,mode='plan',parent_flow_id=parent)
        plan=service.a.get_plan(f['plan_id'])
        try:service.gateway.execute(f['id'])
        except DesignError:blocked=True
        else:raise AssertionError('执行前缺少批准')
        final=service.review(f['id'],accept=True,human_confirmed=True,use_contract_facts=True,
            expected_plan_id=plan['id'],expected_plan_sha=plan['sha'],expected_data_sha=f['request']['data']['frame_sha'])
        execution=service.output(f['id'],'execution')
        assert final['status']=='completed' and execution['completed']
        runs=[]
        for rid in execution['run_ids']:
            body,ref=source_dictionary(service.a,sid,rid)
            bundle=service.a.ex.load(rid)
            runs.append(dict(rid=rid,method=bundle['method'],goal=body['outcome'],window=body['metric_window'],
                contract=ref,n=bundle['summary']['row_count'],averages={x['field']:x['mean'] for x in bundle['summary']['numeric']}))
        rows.append(dict(question=question,blocked_before_review=blocked,version=plan['version'],sha=plan['sha'],
                         selected=service.a.selected_run(sid),runs=runs))
        return f['id']
    first=submitted('请先看 sales 的描述性统计分布。')
    submitted('保留原报告，改为到店人次 traffic，请制定新方案。',first)
    # Intentionally return to the original measure for a separate window task.
    service.a.select_run(sid,rows[0]['runs'][0]['rid'])
    submitted('请只看最近七个自然日的销量，并提交新方案。',first)
    submitted('先描述 sales 的分布，然后用 OLS 分析 sales 与 traffic 的关联。')
    assert rows[1]['runs'][0]['goal']=='traffic' and rows[2]['runs'][0]['n']==7
    assert abs(rows[2]['runs'][0]['averages']['sales']-frame.sales.tail(7).mean())<1e-12
    assert [r['method'] for r in rows[3]['runs']]==['descriptive','ols']
    assert len(service.a.completed_runs(sid))==5
    (root/'runs.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
