import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/eval_v22"))
from browser_actions import InvalidAction, check_action, decide, guard_dispatch
from causalops.llm.providers import OutputContractError, ProviderError


def action(kind="done", ref="", value=""):
    return dict(action=kind,ref=ref,value=value,note="说明")


@pytest.mark.parametrize("op,category",[
    (action("input","x","内容"),"parameter"),(action("click","stale"),"target"),
    (action("upload","x","hidden.csv"),"parameter"),(action("done","x"),"parameter"),
    (action("other"),"parameter")])
def test_invalid_actions(op,category):
    with pytest.raises(InvalidAction) as err:
        check_action(op,[dict(ref="x",role="button",disabled=False)],("issued.csv",))
    assert err.value.category==category


def test_bounded_repair_and_unmodified_task():
    class Model:
        last_telemetry={"status_code":200}
        inputs=[]
        def complete_json(self,**kwargs):
            self.inputs.append(kwargs["user_payload"])
            if len(self.inputs)==1:
                raise OutputContractError("缺少字段")
            return action()
    model=Model()
    event={}
    payload={"task":"查阅报告","page":{"controls":[]}}
    assert decide(model,"",payload,event,())==action()
    assert len(event["requests"])==2 and event["requests"][1]["repair"]
    assert model.inputs[1]["task"]==model.inputs[0]["task"] and "action_validation_feedback" not in payload


@pytest.mark.parametrize("error,n",[(OutputContractError("结构错误"),2),(ProviderError("HTTP 401"),1)])
def test_failure_limit(error,n):
    class Model:
        last_telemetry={}
        def complete_json(self,**kwargs): raise error
    event={}
    with pytest.raises(type(error)):
        decide(Model(),"",{"page":{"controls":[]}},event,())
    assert len(event["requests"])==n


@pytest.mark.parametrize("kind,name,value",[("upload","文件","a.csv"),("click","创建任务并检查数据",""),("click","接受计划并批准本次执行",""),("send","问题","修改口径")])
def test_no_automatic_replay(kind,name,value):
    seen=set(); obs=dict(location="?route=a",text="当前结果：visitors。")
    op=action(kind,"x",value)
    guard_dispatch(op,{"name":name},obs,"N06",seen)
    with pytest.raises(InvalidAction,match="不重复派发"):
        guard_dispatch(op,{"name":name},obs,"N06",seen)


def test_approval_requires_expected_scope():
    with pytest.raises(InvalidAction,match="未授权"):
        guard_dispatch(action("click","x"),{"name":"批准本次执行"},{"text":"结果：orders","location":"a"},"N06",set())

