"""Read the selected plan's target; preparing a change never grants execution authority."""
from dataclasses import dataclass
from causalops.application.onboarding import BASIC_QUESTION
from causalops.application.plan_scope import requested_scope
from causalops.general.service import DesignError


@dataclass(frozen=True)
class ReportTarget:
    outcome: str
    version: int | None
    flow_id: str | None
    run_id: str | None
    pending: bool
    stale: bool
    window_start: str | None
    window_end: str | None


def report_target(service, sid, flow):
    latest = service.contracts.latest(sid)
    if flow and flow["session_id"] != sid:
        raise DesignError("当前方案与研究任务不一致。")
    plan_flow = service.flow(flow["id"]) if flow else None
    runs = service.a.completed_runs(sid)
    if not (plan_flow and plan_flow.get("plan_id")) and runs:
        selected = service.a.selected_run(sid)
        run = next((r for r in runs if r["run_id"] == selected), None)
        if run:
            plan_flow = next((f for f in service.flows(sid) if f["plan_id"] == run["plan_id"]), flow)
    has_plan = bool(plan_flow and plan_flow.get("plan_id"))
    contract = service.contracts.bound(plan_flow) if has_plan else latest
    body = (contract or {}).get("body", {})
    req = plan_flow["request"] if has_plan else {}
    scope = req.get("analysis_scope") or {}
    plan_id = plan_flow["plan_id"] if has_plan else None
    report = next((r for r in runs if r["plan_id"] == plan_id), None)
    return ReportTarget(body.get("outcome") or "", service.a.get_plan(plan_id)["version"] if has_plan else None,
                        plan_flow["id"] if has_plan else None, report["run_id"] if report else None,
                        has_plan and plan_flow["status"] == "awaiting_review",
                        has_plan and req.get("contract_ref") != service.contracts.ref(sid),
                        scope.get("start"), scope.get("end"))


def report_request(service, sid, target, field, frame):
    if target.pending or target.stale:
        raise DesignError("请先核对待审方案或已更新的数据口径。")
    if field and field not in frame:
        raise DesignError("所选指标已不在当前数据中，请重新选择。")
    if field and not target.run_id and field != target.outcome:
        raise DesignError("请在“已有明确问题”中确认首个研究指标，再制定计划。")
    if not field:
        return BASIC_QUESTION
    question = f"将描述统计的目标指标改为 {field}，制定新方案，待我核对后再执行。"
    if target.window_start and target.window_end:
        question += f"沿用 {target.window_start} 至 {target.window_end} 的观察窗口。"
    if field != target.outcome or target.window_start:
        contract = service.contracts.latest(sid)
        body = dict((contract or {}).get("body", {}), outcome=target.outcome)
        parsed = requested_scope(question, body, frame) or {}
        if parsed.get("outcome") != field or parsed.get("error"):
            raise DesignError(parsed.get("error") or "无法唯一确定新指标，请在研究问题中补充字段及口径。")
    return question
