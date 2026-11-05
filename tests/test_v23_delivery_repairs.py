"""Product regressions: no development task IDs, gold files or model stubs."""
import pandas as pd
import pytest
from causalops.application.research_semantics import issue, consultation
from causalops.application.saved_answers import saved_answer
from causalops.application.plan_scope import requested_scope, check_steps
from causalops.general.service import DesignError
from test_v21_flow_boundaries import study, completed_orders, review, reopen

@pytest.mark.parametrize("field",["concentration","migration_time","calibration","duration","ratio_index"])
def test_identifier_substrings_are_not_ratios(field):
    assert not issue(f"按原始记录描述 {field} 的分布和均值，不作总体推断。",{})

@pytest.mark.parametrize("q",["计算总体 ratio","汇总 rate","计算全渠道转化率"])
def test_actual_ratio_still_requires_definition(q):
    assert "分母" in issue(q,{})

def test_declared_metadata_is_separate_from_current_request(tmp_path):
    s=reopen(tmp_path)
    sid=s.create_task(payload=b"signal,batch\n2,1\n4,2\n",name="readings.csv")
    context="每个生产批次的检测记录；信号只是记录级测量。"
    s.contracts.save(sid,dict(outcome="signal",analysis_unit="试样",research={"population":context}),expected_sha=None,human_confirmed=True)
    f=s.start(sid,context+"\n请描述 signal 的分布。")
    assert f["request"]["question"]=="请描述 signal 的分布。"
    assert f["request"]["submitted_question"].startswith(context)
    assert f["status"]=="awaiting_review"

def test_record_mean_plan_and_no_implicit_execution(tmp_path):
    s=reopen(tmp_path)
    sid=s.create_task(payload=b"calibration\n2\n4\n6\n",name="measure.csv")
    s.contracts.save(sid,dict(outcome="calibration",analysis_unit="一次检测",metric_unit="毫克/升"),expected_sha=None,human_confirmed=True)
    f=s.start(sid,"按原始记录描述 calibration 分布和均值，不作总体推断，审核后计算。")
    assert f["status"]=="awaiting_review"
    with pytest.raises(DesignError): s.gateway.execute(f["id"])
    assert not s.a.completed_runs(sid)
    assert review(s,f)["status"]=="completed"

@pytest.mark.parametrize("q",["只分析夜班的新草案","仅保留地区为北区的样本，生成计划","另建只看晚班的新方案"])
def test_subset_cannot_live_only_in_prose(q):
    assert "筛选" in issue(q,{"outcome":"defects"},[{"method":"descriptive","numeric":["defects"],"question":q}])

def test_grouping_is_not_denominator_but_must_be_executable():
    q="按生产批次分组，计算检测值均值。"
    body={"outcome":"signal","fields":[{"field":"lot","meaning":"生产批次"}]}
    assert not issue(q,body,[{"method":"descriptive","numeric":["signal"],"group":"lot"}])
    assert "分组" in issue(q,body,[{"method":"descriptive","numeric":["signal"]}])

def test_outcome_revision_does_not_require_window(study):
    s,sid,_=study
    old,rid=completed_orders(s,sid)
    f=s.start(sid,"先解释旧报告，再拟一份改按 visitors 的待审计划。",run_ids=[rid],parent_flow_id=old["id"])
    assert f["status"]=="awaiting_review"
    scope=f["request"]["analysis_scope"]
    assert scope["outcome"]=="visitors" and not scope.get("start")
    assert s.output(f["id"],"prior_answer")
    with pytest.raises(DesignError): s.gateway.execute(f["id"])
    assert review(s,f)["status"]=="completed"
    assert len(s.a.completed_runs(sid))==2

def test_registered_alias_only_and_preserve_window():
    df=pd.DataFrame({"settled":[1.,2.],"promised":[3.,4.]})
    body={"outcome":"settled","metric_window":"已登记季度","research":{"population":"promised 为承诺额，settled 为实际额。"}}
    scope=requested_scope("改按承诺额提交待审计划",body,df)
    assert scope["outcome"]=="promised" and not scope.get("start")

def test_unsolicited_window_in_outcome_only_plan_is_rejected():
    with pytest.raises(DesignError):
        check_steps({"outcome":"x","base_outcome":"y"},[{"config":{"method":"descriptive","numeric":["x"],"date":"d","window_start":"2024-01-01","window_end":"2024-01-02"}}])

@pytest.mark.parametrize("word",["检测限","检出限","定量限"])
def test_sample_minimum_is_not_instrument_limit(word):
    facts={"m":dict(run_id="run-x",text="signal / min",path="summary.numeric[0].min",value=7.3)}
    a=saved_answer(facts,{"run_id":"run-x","method":"descriptive"},{"outcome":"signal","metric_unit":"微克/升"},"报告中 signal 最小值和单位是多少？能作为仪器"+word+"吗？")
    assert "7.3微克/升" in a["text"] and word in a["text"] and "不能" in a["text"]
    assert "校准" in a["text"] and a["facts"][0]["run_id"]=="run-x"

@pytest.mark.parametrize("q",["重复测量次数不同，记录平均与每个对象等权平均一定不同吗？只解释。","按试样行平均和每个标本一票，权重有什么不同？只谈口径。"])
def test_unequal_counts_do_not_imply_unequal_means(q):
    a=consultation(q)
    assert "可能" in a and "不必然" in a and "相同" in a
    assert "组内均值" in a and "权重" in a

def test_report_background_does_not_invent_denominator():
    facts={"m":dict(run_id="r",text="defects / max",path="summary.numeric[0].max",value=6)}
    a=saved_answer(facts,{"run_id":"r","method":"descriptive"},{"outcome":"defects","metric_unit":"件"},"每个生产批次的检测记录。\n报告最大 defects 是多少？这是未来上限吗？")
    assert "6件" in a["text"] and "分母" not in a["text"] and "未来" in a["text"]


def test_primary_mean_and_unit_are_delivered_from_same_run():
    f={"mean":dict(run_id="r",text="yield / mean",path="summary.numeric[0].mean",value=3.7)}
    a=saved_answer(f,{"run_id":"r","method":"descriptive"},{"outcome":"yield","metric_unit":"吨","metric_window":"本季度"},"本报告样本均值和单位是什么？")
    assert "3.7吨" in a["text"] and "本季度" in a["text"]
    assert a["facts"][0]["run_id"]=="r"

def test_subset_plan_cannot_be_approved_or_directly_executed(study):
    s,sid,_=study
    old,rid=completed_orders(s,sid)
    f=s.start(sid,"保留旧报告，另建只看夜班的方案。",parent_flow_id=old["id"])
    assert f["status"]=="needs_clarification" and not f["plan_id"]
    assert "筛选" in s.output(f["id"],"answer")["text"]
    with pytest.raises(DesignError): s.gateway.execute(f["id"])
    assert [r["run_id"] for r in s.a.completed_runs(sid)]==[rid]

def test_readonly_mean_does_not_create_a_new_plan(study):
    s,sid,_=study
    old,rid=completed_orders(s,sid)
    n=len(s.a.plans(sid))
    f=s.start(sid,"只读所选报告的样本均值和单位。",run_ids=[rid])
    assert f["status"]=="completed" and len(s.a.plans(sid))==n
    assert s.output(f["id"],"answer")["run_ids"]==[rid]


def test_metric_only_revision_preserves_previously_filtered_window(study):
    s,sid,_=study
    old,rid=completed_orders(s,sid)
    narrow=s.start(sid,"改为最近四个自然日的 orders，生成新方案。",run_ids=[rid],parent_flow_id=old["id"])
    assert review(s,narrow)["status"]=="completed"
    narrow_id=s.a.selected_run(sid)
    replacement=s.start(sid,"指标改为 visitors，窗口保持不变，提交新方案。",run_ids=[narrow_id],parent_flow_id=narrow["id"])
    assert replacement["status"]=="awaiting_review"
    before=narrow["request"]["analysis_scope"]
    after=replacement["request"]["analysis_scope"]
    assert (after.get("date"),after.get("start"),after.get("end"))==(before["date"],before["start"],before["end"])
    assert review(s,replacement)["status"]=="completed"
    run=s.a.ex.load(s.a.selected_run(sid))
    assert run["summary"]["row_count"]==4
    assert len(s.a.completed_runs(sid))==3
