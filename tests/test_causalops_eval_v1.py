"""Exercise independent adjudication, isolation and denominators."""
import json

import pytest
from causalops.evaluation.v1.cases import prepare, TASKS
from causalops.evaluation.v1.score import grade, REFERENCE
from causalops.evaluation.v1.worker import execute
from causalops.evaluation.v1.__main__ import summary


@pytest.fixture
def assessed(tmp_path):
    folder=tmp_path/'attempt-1'
    folder.mkdir()
    execute('T01',folder,None,'test-build')
    return folder


def test_positive_attempt_and_trace(assessed):
    assert grade(assessed,'T01')['状态']=='已通过'
    events=[json.loads(s) for s in (assessed/'events.jsonl').read_text('utf8').splitlines()]
    names=[e['事件'] for e in events]
    assert names.index('用户批准指定方案') < names.index('统计执行开始') < names.index('结果解释生成完成')
    assert [e['顺序'] for e in events]==list(range(1,len(events)+1))
    assert not any('payload' in e['详情'] for e in events)


def test_forged_result_and_missing_approval_are_not_passes(assessed):
    p=assessed/'observations.json'
    o=json.loads(p.read_text('utf8'))
    for r in o['runs']:
        for field in r['summary']['numeric']:
            if field['field']=='quality':field['mean']=0
    p.write_text(json.dumps(o),encoding='utf8')
    assert not grade(assessed,'T01')['判据']['质量评分的样本均值与中位数']
    o['approvals']=[]
    p.write_text(json.dumps(o),encoding='utf8')
    assert grade(assessed,'T01')['状态']=='失败'


def test_changed_report_not_valid(assessed):
    next(assessed.glob('*.html')).write_text('changed',encoding='utf8')
    assert not grade(assessed,'T01')['有效报告']


def test_data_and_reference_separation():
    assert set(TASKS)==set(REFERENCE) and len(TASKS)==10
    assert all(set(x)=={'title','data','question','pre'} for x in TASKS.values())
    assert prepare('T08',None)[0]==prepare('T08',None)[0]


def test_missing_marketing_data_remains_in_denominator(tmp_path):
    execute('T06',tmp_path,None,'test-build')
    r=grade(tmp_path,'T06')
    r['任务总耗时秒']=1.0
    assert r['状态']=='尚未测试'
    metrics=summary([r])
    assert metrics['有效报告完成率']==dict(分子=0,分母=1,比例=0.)
    assert metrics['不合法任务阻断率']['比例'] is None

def test_event_index_binds_saved_followup_and_keeps_original(tmp_path):
    from causalops.evaluation.v1.evidence import event_index
    folder=tmp_path/'T09/attempt-1'
    folder.mkdir(parents=True)
    event={'事件':'结果解释生成完成','流程':'follow','运行':None}
    source=folder/'events.jsonl'
    source.write_text(json.dumps(event)+'\n',encoding='utf8')
    (folder/'observations.json').write_text(json.dumps({'flows':[{'id':'follow','answer':{'run_ids':['r']}}]}),encoding='utf8')
    indexed=json.loads(event_index(tmp_path,['T09']).read_text('utf8'))
    assert indexed['运行']==['r'] and json.loads(source.read_text('utf8'))['运行'] is None
