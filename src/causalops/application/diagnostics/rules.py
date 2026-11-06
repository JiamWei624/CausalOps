"""Six registered checks over saved facts. No estimators, free expressions or model judgments."""
from __future__ import annotations
from dataclasses import dataclass, field
import math
from causalops.results.rate_units import rate_contrast
from causalops.sample_data.hillstrom import SOURCE

IMPLEMENTED=("PD-01","PD-02","PD-06","PD-07","PD-09","PD-14")
NOT_IMPLEMENTED=tuple(f"PD-{i:02}" for i in range(1,15) if f"PD-{i:02}" not in IMPLEMENTED)
RULES={
    "PD-01":("binding","native_identity_and_artifact_verification"),
    "PD-02":("design","registered_source_attestation_not_randomization_proof"),
    "PD-06":("metric","bound_observation_window_comparison"),
    "PD-07":("binding","saved_gate_and_two_run_sample_comparison"),
    "PD-09":("metric","saved_metric_and_deterministic_rate_units"),
    "PD-14":("execution","saved_step_and_report_manifest_comparison"),
}

@dataclass(frozen=True)
class Decision:
    status:str
    reason:str
    explanation:str
    observed:dict=field(default_factory=dict)
    expected:dict=field(default_factory=dict)
    missing:tuple=()
    required:tuple=()
    severity:str="information"
    claim:str="unchanged"
    origin:str="program_fact"
    mechanism:str="deterministic_rule"

def unchecked(reason="upstream_evidence_unavailable"):
    return Decision("not_checked",reason,"未读取不完整或未获核验的上游产物，不能将本项显示为通过。",claim="show_limitation")

def _identity(c,window):
    if c.errors:
        invalid=any(not e["missing"] for e in c.errors)
        return Decision("issue" if invalid else "unknown","native_evidence_conflict" if invalid else "native_evidence_missing",
            "原生数据、批准或步骤工件无法完整关联；停止引用联合结论，不从其他任务补数。",
            observed={"checks":c.errors},missing=() if invalid else ("原生数据或持久化步骤证据",),
            required=("核对本任务的数据、批准和工件来源，不重算替代缺失证据。",),
            severity="critical" if invalid else "major",claim="hide_integrated_estimate")
    return Decision("verified","native_identity_verified","已核验当前引用的归属及保存指纹；这不授予执行权限。",
        observed={"verified_run_count":len(c.context["run_refs"]),"phase":c.context["phase"]})

def _design(c,window):
    body=c.contract
    if not body:
        return Decision("unknown","design_contract_missing","没有已登记的研究合同，无法确认分配机制。",
            missing=("DataContract","可核对的研究设计来源"),required=("登记研究事实和设计来源。",),
            severity="major",claim="conditional_causal_only",origin="human_declaration",mechanism="declaration_record_check")
    if body["purpose"]!="causal":
        return Decision("not_applicable","noncausal_request","当前合同为描述/关联或预测目的，不把随机化当作本任务的必需条件。",
            origin="human_declaration",mechanism="declaration_record_check")
    assignment=body.get("method_facts",{}).get("ab_test",{}).get("assignment","unknown")
    if assignment=="observational":
        return Decision("issue","declared_nonrandom_assignment","合同声明为观察性分配，不能当作已确认随机实验。",
            observed={"assignment":assignment},severity="major",claim="conditional_causal_only",
            required=("核对可支持的研究设计；不能把两组存在当成随机分配。",),
            origin="human_declaration",mechanism="declaration_record_check")
    if c.task:
        s=c.task["source"];a=c.evidence.get("S01",{}).get("body")
        confirmed=(assignment=="randomized" and s.get("human_source_confirmed") is True
            and s.get("source_url")==SOURCE and body["research"]["provenance"]==SOURCE)
        if a is not None:
            confirmed=confirmed and a.get("assignment")=="randomized" and a.get("assignment_evidence")==SOURCE and a.get("assignment_evidence_type")=="source_and_human_confirmed_not_inferred_from_groups"
        if confirmed:
            return Decision("verified","legacy_source_attestation_consistent",
                "公开包身份、来源登记和人工声明一致；本项核对来源记录，不是程序证明随机分配真实发生。",
                observed={"assignment_declaration":"randomized","evidence_type":"legacy_source_attestation"},
                origin="human_declaration",mechanism="declaration_record_check")
    return Decision("unknown","randomization_source_unconfirmed",
        "存在处理组和对照组不能确认随机分配；当前缺少可核对的分配设计依据。",
        observed={"declared_assignment":assignment},missing=("可核对的随机分配设计来源及其适用范围",),
        required=("提供设计来源并明确人工核对；不自动改合同或创建统计计划。",),
        severity="major",claim="conditional_causal_only",origin="human_declaration",mechanism="declaration_record_check")

def _window(c,window):
    declared=(c.contract or {}).get("metric_window")
    if not declared:
        return Decision("unknown","window_definition_missing","未登记目标指标的观察窗口。",
            missing=("目标指标观察窗口",),required=("确认窗口含义与适用范围。",),severity="major",claim="show_limitation")
    found={"contract":declared}
    if c.task:
        found["plan"]=c.task["plan"]["scope"]["window"]
        found["tool_config"]=c.task["plan"]["steps"][3]["config"]["metric"]["window"]
        if "S04" in c.bundles:
            found["actual_run"]=c.bundles["S04"].evidence.get("interpretation_inputs",{}).get("metric_definition",{}).get("window")
        if "S05" in c.evidence:found["report"]=c.evidence["S05"]["body"].get("scope",{}).get("window")
    if window is not None:found["requested"]=window
    if any(v!=declared for v in found.values()):
        return Decision("issue","observation_window_conflict","请求或已保存报告的窗口不匹配；当前结果不能回答该窗口问题。",
            observed=found,expected={"same_registered_window":declared},severity="major",claim="hide_integrated_estimate",
            required=("核对窗口与可用数据；当前两周访问字段不提供逐日七天结果。",))
    return Decision("verified","observation_window_bound","已核对登记窗口；未根据相似文字或日期重解释口径。",observed=found)

def _runs(c,window):
    if not all(k in c.evidence for k in ("S01","S02","S03","S04")):return unchecked("statistical_steps_not_executed")
    audit=c.evidence["S01"]["body"];desc=c.evidence["S02"]["body"]["grouped"]
    gate=c.evidence["S03"]["body"];bundle=c.bundles["S04"]
    try:
        if gate!=c.co._gate(c.task):raise ValueError("saved gate differs from actual upstream facts")
        groups={str(r["treatment"]):r for r in bundle.evidence["interpretation_inputs"]["raw_group_summary"]}
        if set(groups)!={"0","1"} or len(desc)!=2:raise ValueError("groups")
        for r in desc:
            g=groups[r["group_value"]]
            if (r["field"]!=c.task["plan"]["scope"]["outcome"] or r["rows"]!=r["finite_n"]
                or r["rows"]!=g["n"] or r["rows"]!=audit["group_counts"][r["group_value"]]
                or not math.isclose(r["mean"],g["outcome_mean"],rel_tol=0,abs_tol=1e-10)):
                raise ValueError("sample")
        if bundle.estimate.sample_size!=audit["rows"] or sum(g["n"] for g in groups.values())!=audit["rows"]:raise ValueError("total")
    except (ValueError,KeyError,TypeError,AttributeError):
        return Decision("issue","upstream_or_two_run_sample_conflict","实际描述统计、保存门禁或A/B样本不一致，不能合并。",
            severity="critical",claim="hide_integrated_estimate",required=("核对原始步骤证据，保留已存运行，不自动重算。",))
    return Decision("verified","two_runs_and_gate_consistent","已从真实描述Run、S03与A/B Run核对分组、样本和均值。",
        observed={"sample_size":audit["rows"],"group_counts":audit["group_counts"],"significance_used":False},
        mechanism="engine_adapter")

def _units(c,window):
    if "S04" not in c.evidence:return unchecked("effect_run_not_executed")
    body=c.contract;scope=c.task["plan"]["scope"];bundle=c.bundles["S04"]
    metric=bundle.evidence.get("interpretation_inputs",{}).get("metric_definition",{})
    cfg=c.task["plan"]["steps"][3]["config"]
    rates=rate_contrast(bundle)
    if (body["outcome"]!=scope["outcome"] or bundle.spec.outcome!=scope["outcome"]
        or body["metric_unit"]!=scope["unit"] or metric.get("unit")!=scope["unit"]
        or body["metric_label"]!=scope["metric"] or metric.get("label")!=scope["metric"]
        or {body["control_value"]:body["control_label"],body["treated_value"]:body["treated_label"]}!=scope["groups"]
        or cfg["metric"]["kind"]!="binary" or rates is None):
        return Decision("issue","metric_group_or_unit_conflict","指标、比较对象或单位不匹配，不能以其他口径替代。",
            severity="critical",claim="hide_integrated_estimate")
    if "S05" in c.evidence and c.evidence["S05"]["body"].get("effect")!=rates:
        return Decision("issue","report_numeric_conversion_conflict","报告中的概率差、百分点或区间链与原工具结果不一致。",
            severity="critical",claim="hide_integrated_estimate")
    return Decision("verified","metric_and_rate_units_bound","指标和组别已绑定，概率差与百分点由原确定性函数核对；不把相对变化当百分点。",
        observed={"outcome":body["outcome"],"unit":scope["unit"],"statistic_type":"risk_difference",
            "percentage_point_conversion":"100 * raw probability difference"},mechanism="engine_adapter")

def _report(c,window):
    if not c.task:return Decision("not_applicable","preflight_has_no_report","预诊断没有正式研究计划或统计报告，不虚构运行。")
    if "S05" not in c.evidence:return unchecked("report_step_not_completed")
    r=c.evidence["S05"]["body"];p=c.task["plan"]
    expected=[c.evidence[k]["body"]["run_id"] for k in ("S02","S04")]
    approval=c.evidence["S04"]["approval_id"]
    try:
        b=c.bundles["S04"]
        _,record=c.co.ws.bundle(expected[1])
        if (r.get("source_runs")!=expected or r.get("scope")!=p["scope"]
            or r.get("objective")!=p["objective"] or r.get("approval_id")!=approval
            or r.get("plan_version")!=p["version"] or r.get("status")!="complete"
            or r.get("sample_size")!=b.estimate.sample_size or r.get("method")!="ab_test"
            or r.get("design_source")!=SOURCE or r.get("domain_revision_id")!=record.revision_id
            or r.get("group_summary")!=b.evidence["interpretation_inputs"]["raw_group_summary"]):
            raise ValueError("manifest")
    except (ValueError,KeyError,TypeError,AttributeError):
        return Decision("issue","report_manifest_identity_conflict","报告引用、指标范围或批准版本与真实步骤不一致；停止整合引用。",
            severity="critical",claim="hide_integrated_estimate")
    return Decision("verified","report_sources_verified","已验证S05引用两个独立Run及原批准；只读诊断不改写原报告。",
        observed={"statistical_runs":2,"plan_version":p["version"]})

CHECKS={"PD-01":_identity,"PD-02":_design,"PD-06":_window,"PD-07":_runs,"PD-09":_units,"PD-14":_report}

def evaluate(collection,requested_window=None):
    decisions={"PD-01":_identity(collection,requested_window)}
    for rid in IMPLEMENTED[1:]:
        decisions[rid]=unchecked() if collection.errors else CHECKS[rid](collection,requested_window)
    return decisions
