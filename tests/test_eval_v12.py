import json
from causalops.evaluation.v12.inputs import CASES,dataset
from causalops.evaluation.v12.rubric import RULES,grade
from causalops.evaluation.v12.__main__ import stats


def test_catalog_and_determinism():
    assert len(CASES)==15 and CASES.keys()==RULES.keys()
    for case in CASES:
        first,ctx=dataset(case)
        second,ctx2=dataset(case)
        assert first.equals(second) and ctx==ctx2
        assert not {'判据','reference','expected'} & ctx.keys()


def test_block_does_not_erase_bad_model_advice():
    obs=dict(target='f',flows=[dict(id='f',plan=None,status='needs_clarification',route={'route':'clarify'},
                 answer={'text':'请先提供断点阈值。'})],runs=[],receipts=[],probes={},
             advice=dict(action='execute',methods=['ols'],requirements=[],reasoning='直接运行。',fields=[]))
    result=grade('C06',obs)
    assert result['结果']=='正确澄清' and result['非法执行阻断']
    assert not result['模型建议']['action'] and not result['模型建议']['conditions']


def test_wrong_historical_fact_cannot_count_as_citation():
    obs=dict(target='f',flows=[dict(id='f',status='completed',route={'route':'results'},
             answer=dict(run_ids=['old'],facts=[dict(run_id='new',value=8.8)]))],probes={'first':'old'})
    assert not grade('C12',obs)['数字及引用']


def test_timeout_counts_as_failure_and_no_model_grade_is_not_zero_accuracy():
    r=grade('C08',{'errors':['尝试超时']})
    r.update(结构化输出=[],发起请求=0,有用量的响应=0,输入令牌=0,输出令牌=0,耗时秒=180)
    s=stats([r])
    assert s['任务正确处理率']==dict(通过=0,有效数=1)
    assert s['方法建议合理率']['有效数']==0
