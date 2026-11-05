"""Reliability checks use independent toy data, never sealed task answers."""
import pytest
def readonly_consultation(q):
 from causalops.application.research_semantics import readonly_consultation as fn
 return fn(q)
def _check(name,*args):
 from importlib import import_module
 return getattr(import_module('causalops.application.answer_checks'),name)(*args)
def convert(*a):return _check('convert',*a)
def unit_guidance(*a):return _check('unit_guidance',*a)
def design_checked(*a):return _check('design_checked',*a)
from causalops.application.saved_answers import saved_answer
from causalops.general.service import DesignError
from test_v21_flow_boundaries import study, completed_orders, review, reopen

@pytest.mark.parametrize("q",[
 "能用断点回归回答效果吗？", "应先补什么时间和比较组信息？",
 "请先区分覆盖面与效果这两个任务。", "如何理解普通回归的适用条件？",
 "看看这种方法能否识别效果，先说明理由。"])
def test_readonly_consultation(q):
 assert readonly_consultation(q)

@pytest.mark.parametrize("q",[
 "请生成回归分析计划。", "先解释均值，再创建新方案。",
 "用这张表计算分布，审核后运行。", "请分析检测值的均值和分布。"])
def test_new_calculation_not_readonly(q):
 assert not readonly_consultation(q)

@pytest.mark.parametrize("q",["能用断点回归回答效果吗？","请先区分覆盖面与效果这两个任务。"])
def test_readonly_does_not_create_plan(tmp_path,q):
 s=reopen(tmp_path); sid=s.create_task(payload=b"value\n2\n4\n",name="sample.csv")
 f=s.start(sid,q)
 assert not f.get("plan_id") and not s.a.completed_runs(sid)
 assert s.output(f["id"],"answer") or s.output(f["id"],"route")

def test_metadata_method_name_not_action(tmp_path):
 s=reopen(tmp_path); sid=s.create_task(payload=b"value\n2\n4\n",name="sample.csv")
 s.contracts.save(sid,{"outcome":"value","research":{"population":"背景资料介绍回归与效果估计。"}},human_confirmed=True)
 f=s.start(sid,"背景资料介绍回归与效果估计。\n请说明还缺什么研究条件？")
 assert not f.get("plan_id")

@pytest.mark.parametrize("v,a,b,expected",[(2500,"毫克/升","克/升","2.500"),(-3,"千克","克","-3000"),(2,"MWh","kWh","2000"),(0,"克","千克","0")])
def test_fixed_scale(v,a,b,expected):
 from decimal import Decimal
 assert convert(v,a,b)==Decimal(expected)

@pytest.mark.parametrize("a,b",[("千克","升"),("kWh","吨"),("百分比","百分点"),("未登记","克")])
def test_incompatible_units(a,b):
 with pytest.raises(ValueError): convert(1,a,b)

def test_emissions_need_factor_and_baseline():
 text=unit_guidance("把用电量换算成减少的二氧化碳吨数，需要什么？",{"metric_unit":"千瓦时"})
 assert "排放因子" in text and "基线" in text and "1000000" in text and "1000" in text
 assert "不能" in text and "CO2e" in text

def test_volume_mass_need_density():
 text=unit_guidance("将质量换算成体积，还缺什么？",{"metric_unit":"千克"})
 assert "密度" in text and "不能" in text

def test_randomization_is_not_inferred():
 text,issues=design_checked("随机化发生在医院层面，而患者不能作为独立单位。",{})
 assert issues and "未确认" in text and "随机化发生在医院" not in text

def test_supported_randomization_preserved():
 body={"method_facts":{"ab_test":{"assignment":"randomized"}}}
 text,issues=design_checked("本研究按医院随机分配。",body)
 assert not issues and "按医院随机分配" in text

@pytest.mark.parametrize("text",["若按医院随机分配，仍需处理组内依赖。","不能从两组存在推断随机分配。"])
def test_conditional_or_negative_design_is_preserved(text):
 assert design_checked(text,{})==(text,[])

def test_mean_value_and_meaning_bound_to_same_run():
 facts={"a":{"run_id":"chosen","text":"signal / mean","path":"summary.numeric[0].mean","value":4.5},
        "b":{"run_id":"other","text":"signal / mean","path":"summary.numeric[0].mean","value":100}}
 a=saved_answer(facts,{"run_id":"chosen","method":"descriptive"},{"outcome":"signal","metric_unit":"毫克/升","analysis_unit":"一次测量"},
                "解释样本均值并引用本次报告。")
 assert "4.5" in a["text"] and "按记录" in a["text"] and "重复" in a["text"]
 assert all(x["run_id"]=="chosen" for x in a["facts"])

def test_saved_mean_conversion():
 f={"a":{"run_id":"r","text":"signal / mean","path":"summary.numeric[0].mean","value":2400}}
 a=saved_answer(f,{"run_id":"r","method":"descriptive"},{"outcome":"signal","metric_unit":"毫克/升"},"样本均值换算成克/升是多少？")
 assert "2.4克/升" in a["text"] and a["facts"][0]["value"]==2400

def test_plan_approval_and_old_report_remain(study):
 s,sid,_=study; old,rid=completed_orders(s,sid)
 f=s.start(sid,"请说明这个方法的适用条件。",run_ids=[rid])
 assert not f.get("plan_id") and len(s.a.completed_runs(sid))==1
 new=s.start(sid,"改按 visitors 生成新计划",run_ids=[rid],parent_flow_id=old["id"])
 assert new["status"]=="awaiting_review"
 with pytest.raises(DesignError):s.gateway.execute(new["id"])
 assert len(s.a.completed_runs(sid))==1

def test_later_qualification_cannot_mask_earlier_assertion():
 text,issues=design_checked("随机化发生在学校层面，若按测评次数计算会有偏差。",{})
 assert issues and "随机化发生在学校" not in text

def test_conversion_does_not_change_statistical_scale():
 with pytest.raises(ValueError):convert(3,"百分点","百分比")

def test_mean_explanation_does_not_invent_repetition_counts():
 from causalops.application.answer_checks import mean_explanation
 text=mean_explanation("解释均值",{})
 assert "若" in text and "记录较多" in text
 assert not any(c.isdigit() for c in text)

@pytest.mark.parametrize("target",["毫克/千克","kg/m3","克每升","千克米"])
def test_unknown_composite_unit_not_truncated(target):
 from causalops.application.answer_checks import converted_value
 answer=converted_value(2,"千克","换算成"+target+"是多少？")
 assert "不能" in answer and "2000000" not in answer

def test_negative_conversion_request():
 from causalops.application.answer_checks import converted_value
 assert converted_value(2,"千克","不要换算成克，保留千克")==''

def test_same_dimension_not_density_problem():
 assert unit_guidance("把质量从千克换算成克的依据",{"metric_unit":"千克"})==''

@pytest.mark.parametrize("text",["本研究没有随机分配。","This study was not randomized."])
def test_negative_randomization_statement(text):
 assert design_checked(text,{})==(text,[])

def test_randomized_trial_assertion_requires_contract():
 assert design_checked("本研究采用随机对照试验。",{})[1]

def test_randomization_uses_legal_contract(tmp_path):
 s=reopen(tmp_path);sid=s.create_task(payload=b"value,group\n2,0\n4,1\n",name="experiment.csv")
 row=s.contracts.save(sid,{"outcome":"value","treatment":"group","method_facts":{"ab_test":{"assignment":"randomized"}}},human_confirmed=True)
 assert design_checked("本研究已登记随机分配。",row["body"])[1]==[]

@pytest.mark.parametrize("q",["请解释如何计算样本分布和均值。","说明回归分析的适用条件。"])
def test_calculation_description_is_not_calculation(q):
 assert readonly_consultation(q)

@pytest.mark.parametrize("q",["分析分布的适用条件是什么？","请解释如何描述均值，不要生成计划。"])
def test_readonly_conditions_not_new_plan(tmp_path,q):
 s=reopen(tmp_path);sid=s.create_task(payload=b"signal\n2\n4\n",name="measure.csv")
 assert not s.start(sid,q).get("plan_id")

def test_random_assertion_not_qualified_by_later_requirement():
 assert design_checked("本研究随机分配且需要检查失访。",{})[1]

def test_conditional_scope_survives_comma():
 text=" 如果按医院随机分配，随机化单位是医院。"
 assert design_checked(text,{})==(text,[])
