from causalops.evaluation.v13.calibration import (
    _resume_verified, acceptable_alternative, method_rule, normalize_method
)


def test_exact_method_families_and_required_evidence():
    for alias in ("descriptive_statistics", "描述性统计"):
        assert normalize_method(alias) == "descriptive"
    for alias in ("PEARSON-CORRELATION", "spearman_correlation"):
        assert normalize_method(alias) == "correlation"
    assert method_rule("distribution", {"action":"execute","methods":["distribution_fitting"]})["status"] == "fail"
    assert method_rule("sample_correlation", {"action":"execute","methods":["ols"]})["status"] == "needs_evidence"
    assert method_rule("distribution", {"action":"clarify","methods":[]})["status"] == "not_applicable"


def test_revision_or_clarification_requires_specific_support():
    advice = {"action":"revise","methods":["pearson_correlation"],
              "reasoning":"描述样本内关联，无法识别干预收益。"}
    assert acceptable_alternative("C09", advice)
    assert not acceptable_alternative("C09", dict(advice, methods=["OLS"]))
    assert acceptable_alternative("C06", {"action":"revise","reasoning":"没有阈值，须先补齐。"})
    assert not acceptable_alternative("C06", {"action":"revise","reasoning":"拟合断点模型。"})
    assert not acceptable_alternative("C10", {"action":"clarify","reasoning":"请确认访客数。"})
    assert acceptable_alternative("C10", {"action":"clarify","reasoning":"撤回原方案，访客口径先核对，不执行。"})


def test_resume_cannot_be_inferred_from_completed_run():
    flow = {"id":"f", "sha":"h", "plan":"p", "events":[]}
    run = {"plan_sha":"h", "plan_id":"p", "data":"d", "run_id":"r"}
    receipt = {"flow_id":"f","plan_sha":"h","plan_id":"p","data":{"frame_sha":"d"},"approved_at":"2"}
    obs = {"probes":{"stop":"FlowCancelled","stopped_runs":0},"runs":[run],"receipts":[receipt]}
    assert not _resume_verified(obs, flow)
    flow["events"] = [{"node":n,"status":s,"seq":i,"created":str(i),"body":{"plan_id":"p"}}
                      for i,(n,s) in enumerate([("cancel","requested"),("await_review","started"),
                                                ("review","approved"),("execute_plan","started")])]
    assert _resume_verified(obs, flow)
    receipt["plan_sha"] = "other"
    assert not _resume_verified(obs, flow)



def test_opening_field_alias_requires_evidence_of_missing_treatment():
    from causalops.evaluation.v13.calibration import opening_proxy_rejected
    assert opening_proxy_rejected("opening_day 缺乏促销实施记录")
    assert not opening_proxy_rejected("以 opening_day 估计促销效果")
