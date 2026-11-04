"""Regression boundaries for real, persisted research flows. No model or scoring harness."""
import numpy as np
import pandas as pd
import pytest

from causalops.application.research_service import ResearchService
from causalops.application.task_conclusions import source_dictionary
from causalops.assistant.service import AssistantWorkspace
from causalops.general.service import DesignError, GeneralWorkspace


def reopen(root):
    return ResearchService(AssistantWorkspace(GeneralWorkspace(root)))


@pytest.fixture
def study(tmp_path):
    n = 28
    frame = pd.DataFrame({
        "day": pd.date_range("2026-03-01", periods=n).strftime("%Y-%m-%d"),
        "orders": 1 + np.arange(n) // 2,
        "visitors": 110 + (np.arange(n) * 3) % 11,
    })
    service = reopen(tmp_path)
    sid = service.create_task(payload=frame.to_csv(index=False).encode(), name="daily.csv")
    service.contracts.save(sid, {
        "analysis_unit": "门店日", "time": "day", "outcome": "orders",
        "predictors": ["visitors"], "metric_kind": "count", "metric_label": "每日订单数",
        "metric_unit": "单", "metric_window": "完整的28天",
        "method_facts": {"ols": {"independent_rows_reviewed": True}},
    }, expected_sha=None, human_confirmed=True)
    return service, sid, frame


def review(service, flow, **kwargs):
    plan = service.a.get_plan(flow["plan_id"])
    return service.review(flow["id"], accept=True, human_confirmed=True,
                          expected_plan_id=plan["id"], expected_plan_sha=plan["sha"],
                          expected_data_sha=flow["request"]["data"]["frame_sha"],
                          use_contract_facts=True, **kwargs)


def completed_orders(service, sid):
    flow = service.start(sid, "请描述每日订单数 orders 的样本分布。", mode="plan")
    assert flow["status"] == "awaiting_review"
    assert review(service, flow)["status"] == "completed"
    run, = service.a.completed_runs(sid)
    return flow, run["run_id"]


def mean_for(service, sid, run_id, field):
    facts, _ = service.a.facts(sid, run_ids=[run_id])
    value, = [v["value"] for v in facts.values() if v["text"] == f"{field} / mean"]
    return value


def revise_visitors(service, sid, old_flow):
    return service.start(sid, "保留原订单数报告。改为每日访客数 visitors，给我一份新方案重新审核。",
                         parent_flow_id=old_flow["id"])


def test_metric_change_binds_new_dictionary_without_relabelling_old_report(study):
    service, sid, frame = study
    old_flow, old_id = completed_orders(service, sid)
    original_dictionary, _ = source_dictionary(service.a, sid, old_id)
    revision = revise_visitors(service, sid, old_flow)
    assert revision["status"] == "awaiting_review"
    assert [r["run_id"] for r in service.a.completed_runs(sid)] == [old_id]
    assert source_dictionary(service.a, sid, old_id)[0] == original_dictionary
    new_bound = service.contracts.bound(revision)
    assert new_bound and new_bound["body"]["outcome"] == "visitors"
    assert new_bound["body"]["metric_unit"] != original_dictionary["metric_unit"]
    assert review(service, revision)["status"] == "completed"
    new_id, = [r["run_id"] for r in service.a.completed_runs(sid) if r["run_id"] != old_id]
    assert source_dictionary(service.a, sid, new_id)[0]["outcome"] == "visitors"
    assert mean_for(service, sid, new_id, "visitors") == pytest.approx(frame.visitors.mean())
    assert mean_for(service, sid, old_id, "orders") == pytest.approx(frame.orders.mean())


def test_unapproved_revision_cannot_dispatch_through_either_entry(study):
    service, sid, _ = study
    old_flow, old_id = completed_orders(service, sid)
    # Explicit page plan mode isolates the gateway from the auto-router regression.
    original = service.contracts.latest(sid)
    service.contracts.save(sid, dict(original["body"], outcome="visitors", predictors=[],
                                     metric_label="每日访客数", metric_unit="人"),
                           expected_sha=original["sha"], human_confirmed=True)
    revision = service.start(sid, "请制定每日访客数 visitors 的分布分析计划。", mode="plan",
                             parent_flow_id=old_flow["id"])
    assert revision["status"] == "awaiting_review"
    with pytest.raises(DesignError):
        service.gateway.execute(revision["id"])
    with pytest.raises(DesignError):
        service.a.execute(revision["plan_id"], permit=True)
    assert [r["run_id"] for r in service.a.completed_runs(sid)] == [old_id]


def test_window_change_filters_seven_actual_days_or_explains_block(study):
    service, sid, frame = study
    old_flow, old_id = completed_orders(service, sid)
    change = service.start(sid, "不要沿用整月结果。我只看截至2026-03-28的最近七个自然日"
                           "（2026-03-22到2026-03-28）的订单数均值。保留旧报告，先提交新方案。",
                           parent_flow_id=old_flow["id"])
    assert [r["run_id"] for r in service.a.completed_runs(sid)] == [old_id]
    if change["status"] in {"needs_clarification", "blocked", "completed"}:
        reply = service.output(change["id"], "answer") or {}
        readiness = service.output(change["id"], "readiness") or {}
        explanation = reply.get("text", "") + " ".join(readiness.get("errors", []))
        assert any(word in explanation for word in ("窗口", "时间范围", "日期范围", "筛选", "七天", "七个自然日"))
        assert any(word in explanation for word in ("缺少", "未登记", "不能", "不足", "尚未", "无法", "需要确认", "请确认"))
        assert [r["run_id"] for r in service.a.completed_runs(sid)] == [old_id]
        return
    assert change["status"] == "awaiting_review"
    assert review(service, change)["status"] == "completed"
    new_id, = [r["run_id"] for r in service.a.completed_runs(sid) if r["run_id"] != old_id]
    assert mean_for(service, sid, new_id, "orders") == pytest.approx(frame.orders.tail(7).mean())
    assert mean_for(service, sid, old_id, "orders") == pytest.approx(frame.orders.mean())


def test_reload_keeps_both_reports_and_explicitly_selected_old_evidence(study, tmp_path):
    service, sid, frame = study
    _, old_id = completed_orders(service, sid)
    original = service.contracts.latest(sid)
    new_body = dict(original["body"], outcome="visitors", predictors=[], metric_label="每日访客数", metric_unit="人")
    service.contracts.save(sid, new_body, expected_sha=original["sha"], human_confirmed=True)
    new_flow = service.start(sid, "请描述每日访客数 visitors 的样本分布。", mode="plan")
    assert review(service, new_flow)["status"] == "completed"
    prior_runs = {r["run_id"] for r in service.a.completed_runs(sid)}
    new_id, = prior_runs - {old_id}
    service.a.select_run(sid, old_id)
    fresh = reopen(tmp_path)
    assert fresh.a.selected_run(sid) == old_id
    for rid, field in ((old_id, "orders"), (new_id, "visitors")):
        assert source_dictionary(fresh.a, sid, rid)[0]["outcome"] == field
        followup = fresh.start(sid, "请说明所选报告的均值及样本范围。", mode="results", run_ids=[rid])
        answer = fresh.output(followup["id"], "answer")
        assert answer["run_ids"] == [rid]
        assert answer["facts"] and all(f["run_id"] == rid for f in answer["facts"])
        assert mean_for(fresh, sid, rid, field) == pytest.approx(frame[field].mean())
    assert {r["run_id"] for r in fresh.a.completed_runs(sid)} == prior_runs


def test_mixed_description_then_ols_requires_one_approval_for_both_steps(study):
    service, sid, _ = study
    flow = service.start(sid, "先描述 orders 的分布，然后用 OLS 回归研究订单数 orders 与"
                         "访客数 visitors 的关联，两步放在同一份方案里，审核后再运行。", mode="plan")
    assert flow["status"] == "awaiting_review"
    plan = service.a.get_plan(flow["plan_id"])
    configs = [step["config"] for step in plan["plan"]["steps"]]
    assert [c["method"] for c in configs] == ["descriptive", "ols"]
    assert configs[1]["outcome"] == "orders" and configs[1]["predictors"] == ["visitors"]
    with pytest.raises(DesignError):
        service.gateway.execute(flow["id"])
    assert not service.a.completed_runs(sid)
    assert review(service, flow)["status"] == "completed"
    runs = sorted(service.a.completed_runs(sid), key=lambda run: run["ordinal"])
    assert [r["method"] for r in runs] == ["descriptive", "ols"]
    assert all(r["plan_sha"] == plan["sha"] for r in runs)
    assert len({r["run_id"] for r in runs}) == 2
    assert len([e for e in service.events(flow["id"]) if e["node"] == "review" and e["status"] == "approved"]) == 1

def test_explicit_plan_revision_must_not_run_visitors_with_an_orders_dictionary(study):
    service, sid, _ = study
    old_flow, old_id = completed_orders(service, sid)
    revised = service.start(sid, "现在改看每日访客数 visitors。制定新描述方案，保留原订单报告。",
                            mode="plan", parent_flow_id=old_flow["id"])
    assert revised["status"] in {"awaiting_review", "needs_clarification", "blocked"}
    if revised["status"] == "awaiting_review":
        bound = service.contracts.bound(revised)
        if bound["body"]["outcome"] != "visitors":
            with pytest.raises(DesignError):
                review(service, revised)
            assert [r["run_id"] for r in service.a.completed_runs(sid)] == [old_id]
    assert source_dictionary(service.a, sid, old_id)[0]["outcome"] == "orders"


def test_window_follows_selected_revised_metric(study):
    service, sid, frame=study
    original, old=completed_orders(service,sid)
    revision=revise_visitors(service,sid,original)
    review(service,revision)
    follow=service.start(sid,'保留刚才的访客报告，改为只看最近五个自然日，请提交新方案。',parent_flow_id=revision['id'])
    assert follow['status']=='awaiting_review'
    assert review(service,follow)['status']=='completed'
    newest=service.a.selected_run(sid)
    dictionary,ref=source_dictionary(service.a,sid,newest)
    assert dictionary['outcome']=='visitors'
    assert ref['scope_sha']
    assert mean_for(service,sid,newest,'visitors')==pytest.approx(frame.visitors.tail(5).mean())
    reply=service.output(follow['id'],'answer')
    assert newest in reply['text'] and 'visitors' in reply['text'] and '5' in reply['text']
    assert source_dictionary(service.a,sid,old)[0]['outcome']=='orders'
