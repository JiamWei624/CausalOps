"""Finite mappings for the six implemented rules. No natural-language routing."""
from causalops.assistant.service import digest
from causalops.general.service import DesignError
from .rules import IMPLEMENTED
from .report_contracts import ResearchSuggestion, SUGGESTION_VERSION

ACTIONS = {
    "PD-01": "核对本任务数据、合同、批准与运行工件的归属及指纹，恢复可核对的原生引用。",
    "PD-02": "补充可核对的分配设计来源、适用人群和期间，并由使用者核对。",
    "PD-06": "核对请求窗口与登记指标窗口；若目标已改变，先补充对应数据。",
    "PD-07": "核对描述统计与效果运行的样本、分组和上游门禁记录。",
    "PD-09": "核对指标定义、单位及概率差与百分点的转换来源。",
    "PD-14": "核对报告引用的运行、计划版本和原批准，暂停使用冲突的联合结论。",
}

def build_suggestions(assessment):
    suggestions = []
    for finding in assessment.findings:
        if finding.rule.id not in IMPLEMENTED:
            raise DesignError("不能为未实现规则生成建议")
        if finding.status not in ("issue", "unknown"):
            continue
        refs = {
            "task": assessment.context.task_ref.model_dump(mode="json"),
            "data": assessment.context.data_ref.model_dump(mode="json") if assessment.context.data_ref else None,
            "plan": assessment.context.plan_ref.model_dump(mode="json") if assessment.context.plan_ref else None,
            "runs": [r.model_dump(mode="json") for r in assessment.context.run_refs],
            "evidence": [r.model_dump(mode="json") for r in finding.evidence_refs],
        }
        suggestions.append(ResearchSuggestion(
            suggestion_id=digest({"finding": finding.finding_id, "mapping": SUGGESTION_VERSION}),
            diagnostic_id=finding.finding_id, assessment_id=assessment.assessment_id,
            rule_id=finding.rule.id, rule_version=finding.rule.version,
            context_fingerprint=assessment.context_fingerprint, related_refs=refs,
            action=ACTIONS[finding.rule.id], reason_code=finding.result.reason_code,
            reason=finding.impact.explanation,
            required_evidence=finding.result.missing_items or finding.result.required_work or
                ("与本规则冲突对应的原生口径、运行和来源记录",),
            limitations=("建议只登记核查事项；不会修改合同或批准。",
                         "正式数据、口径或方法变化须另行请求待审方案。"),
        ))
    # Keep the report small while retaining every finding in the quality layer.
    priority = {f.finding_id: (0 if f.status == "issue" else 1) for f in assessment.findings}
    suggestions.sort(key=lambda a: (priority[a.diagnostic_id], a.rule_id))
    return tuple(suggestions[:3])

