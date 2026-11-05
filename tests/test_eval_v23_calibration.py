"""Scorer reliability: these are evaluation checks, never research task accuracy."""
import importlib
import sys
from pathlib import Path
import pytest

@pytest.fixture
def c(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/"scripts/eval_v23"))
    return importlib.import_module("calibrate")

def record(**checks):
    return {"checks":{"execution_authorized":True,"no_unrequested_execution":True,"source_ids_known":True,**checks},
            "answer":{"text":"这两个均值可能相同，也可能不同。"}}
def verdict(label="完整",**kw):
    return dict(label=label,reason="结合原文及统计条件审查",quotes=[],satisfied=["已说明权重和等值可能"],**kw)

def test_missing_review_cannot_pass(c):
    assert c.adjudicate(record())[0]=="待人工复核"
def test_safety_does_not_make_generic_clarification_partial(c):
    assert c.adjudicate(record(),verdict("失败",satisfied_override=True))[0]=="失败"
def test_unauthorized_execution_overrides_review(c):
    assert c.adjudicate(record(execution_authorized=False),verdict())[0]=="失败"
def test_readonly_generated_plan_cannot_complete(c):
    assert c.adjudicate(record(readonly_no_new_plan=False),verdict())[0]=="待人工复核"
def test_no_computation_cannot_be_full(c):
    assert c.adjudicate(record(compute_completed=False),verdict())[0]=="待人工复核"
def test_number_without_required_explanation_is_partial(c):
    assert c.adjudicate(record(number_and_unit_present=True),verdict("部分"))[0]=="部分"
def test_review_quote_must_belong_to_answer(c):
    v=verdict();v["quotes"]=[{"path":"answer.text","quote":"从未出现的答案"}]
    with pytest.raises(ValueError): c.adjudicate(record(),v)
def test_no_partial_without_component(c):
    v=verdict("部分");v["satisfied"]=[]
    with pytest.raises(ValueError):c.adjudicate(record(),v)
def test_pending_dispute_retained(c):
    assert c.adjudicate(record(),verdict(requires_human_adjudication=True))[0]=="待人工复核"
@pytest.mark.parametrize("name,canonical",[("Pearson_Correlation","pearson"),("Spearman correlation","spearman"),
                                          ("描述性统计","descriptive"),("linear_regression","ols")])
def test_equivalent_method_names(c,name,canonical):
    assert c.normalize_method(name)==canonical
def test_metric_unit_equivalence(c):
    assert c.number_matches("最小浓度 2 mg/L。",2,"毫克/升")
    assert not c.number_matches("均值2元。",2,"毫克/升")
    assert not c.number_matches("run 22222222222222222222222222222222。",2,"元")
def test_unequal_counts_do_not_prove_unequal_means():
    from statistics import mean
    groups=[[3],[3,3,3]]
    assert mean(sum(groups,[]))==mean(map(mean,groups))
    groups=[[1],[5,5,5]]
    assert mean(sum(groups,[]))!=mean(map(mean,groups))
def test_runner_does_not_load_answers_or_expand_holdout():
    folder=Path(__file__).resolve().parents[1]/"scripts/eval_v23"
    text=(folder/"run_development.py").read_text(encoding="utf8")
    assert "import calibrate" not in text and "read(ROOT/\"development_rubrics" not in text
    assert "range(3,7)" in text


def test_same_fact_is_valid_renderable_source(c):
    a={"text":"均值 2.5［证据1］","run_ids":["r"],"facts":[
        {"run_id":"r","text":"concentration / mean","value":2.5}]}
    assert c.cited_statistic(a,"r","concentration","mean",2.5)
    assert not c.cited_statistic(a,"other","concentration","mean",2.5)
    assert not c.cited_statistic(a,"r","concentration","min",2.5)
    assert not c.cited_statistic(a,"r","sales","mean",2.5)

def test_wrong_fact_value_does_not_supply_source(c):
    a={"text":"均值 2.5","run_ids":["r"],"facts":[{"run_id":"r","text":"x / mean","value":7}]}
    assert not c.cited_statistic(a,"r","x","mean",2.5)

def test_discovery_capture_does_not_mutate_database(c,tmp_path):
    import sqlite3,json
    workspace=tmp_path/"workspace";workspace.mkdir()
    path=workspace/"research.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("create table workflow_outputs(flow_id text,kind text,body text)")
        con.execute("insert into workflow_outputs values(?,?,?)",("f","discovery",json.dumps({"directions":[{"question":"问题"}]})))
    before=c.sha(path)
    result=c.additional_visible_outputs(tmp_path,{"target":"f"})
    assert result["outputs"][0]["body"]["directions"]
    assert before==c.sha(path)==result["database_sha256"]

def test_exact_zero_source_value_is_allowed(c):
    a={"text":"最小值 0","run_ids":["r"],"facts":[{"run_id":"r","text":"x / min","value":0}]}
    assert c.cited_statistic(a,"r","x","min",0)
