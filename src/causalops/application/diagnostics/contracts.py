"""Versioned read-only diagnostic facts. No execution authority is represented."""
from __future__ import annotations
from typing import Literal, Annotated
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

Status = Literal["verified","issue","unknown","not_applicable","not_checked"]
RuleId = Literal["PD-01","PD-02","PD-06","PD-07","PD-09","PD-14"]
SCHEMA_VERSION = "diagnostic-assessment-v1.1"

class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

class EvidenceReference(FrozenModel):
    artifact_kind: Literal["data_contract","source_record","step_evidence","run_bundle","validation_observation"]
    artifact_id: str = Field(min_length=1,max_length=128)
    sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    json_pointer: str = Field(default="",pattern=r"^(?:/.*)?$")
    availability: Literal["valid"] = "valid"


Hash = Annotated[str,Field(pattern=r"^[0-9a-f]{64}$")]
NativeId = Annotated[str,Field(min_length=1,max_length=128)]

class NativeReference(FrozenModel):
    def __getitem__(self,key):
        return getattr(self,key)

class TaskReference(NativeReference):
    kind: Literal["automation_v2","research_session"]
    task_id: NativeId
    session_id: NativeId

class PlanReference(NativeReference):
    id: NativeId
    version: int = Field(ge=1)
    sha: Hash

class DataReference(NativeReference):
    upload_id: NativeId
    frame_sha: Hash

class ContractReference(PlanReference):
    data_sha: Hash

class RunReference(NativeReference):
    run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    kind: Literal["exploration","research"]
    plan_id: NativeId
    result_fingerprint: Hash

class DiagnosticScope(FrozenModel):
    analysis_unit: str | None
    outcome_field: str | None
    metric_label: str | None
    statistic_type: str | None
    unit: str | None
    observation_window: str | None
    group_labels: tuple[str,...]
    numerator: str | None
    denominator: str | None
    aggregation: str | None

class DiagnosticProvenance(FrozenModel):
    recorded_execution_source_sha: Hash | None
    diagnostic_source_sha: Hash
    reading_mode: Literal["preflight","historical_read_only","current_execution"]

class DiagnosticContext(FrozenModel):
    task_ref: TaskReference
    plan_ref: PlanReference | None
    no_plan_reason: str | None
    data_ref: DataReference | None
    contract_ref: ContractReference | None
    run_refs: tuple[RunReference,...] = ()
    scope: DiagnosticScope
    fingerprint: Hash
    phase: Literal["preflight","post_run","partial_run"]
    provenance: DiagnosticProvenance

    @model_validator(mode="after")
    def coherent_references(self):
        if self.plan_ref is None and not self.no_plan_reason:
            raise ValueError("无正式计划必须说明原因")
        if self.phase=="preflight" and (self.plan_ref is not None or self.run_refs):
            raise ValueError("预诊断不能借用统计运行")
        if len({r.run_id for r in self.run_refs})!=len(self.run_refs) or len(self.run_refs)>2:
            raise ValueError("本阶段最多接受两个独立运行")
        if self.run_refs and any(r.plan_id!=self.plan_ref.id for r in self.run_refs):
            raise ValueError("运行必须属于当前明确计划")
        return self

class RuleReference(FrozenModel):
    id: RuleId
    version: str
    pack: str
    check_method: str

class CheckResult(FrozenModel):
    observed: dict
    expected: dict
    reason_code: str
    missing_items: tuple[str,...] = ()
    required_work: tuple[str,...] = ()

class Impact(FrozenModel):
    claim_effect: Literal["unchanged","conditional_causal_only","show_limitation","hide_integrated_estimate"]
    explanation: str
    execution_authority: Literal["original_service_only"] = "original_service_only"

class Severity(FrozenModel):
    level: Literal["critical","major","moderate","information"]
    policy_id: str
    reason_code: str

class FindingSource(FrozenModel):
    mechanism: Literal["deterministic_rule","engine_adapter","declaration_record_check"]
    origin: Literal["program_fact","human_declaration","mixed"]
    generator_version: str

class DiagnosticFinding(FrozenModel):
    schema_version: Literal["diagnostic-finding-v1.1"] = "diagnostic-finding-v1.1"
    finding_id: str
    assessment_id: str
    context: DiagnosticContext
    rule: RuleReference
    diagnostic_type: Literal["binding","design","metric","execution"]
    applicability: Literal["applicable","not_applicable","unknown"] = "applicable"
    check_performed: bool
    status: Status
    result: CheckResult
    evidence_refs: tuple[EvidenceReference,...]
    impact: Impact
    severity: Severity
    human_confirmation_required: bool
    eligible_action_ids: tuple[str,...] = ()
    generated_at: str

    @field_validator("generated_at")
    @classmethod
    def timestamp(cls,value):
        if datetime.fromisoformat(value).tzinfo is None:
            raise ValueError("诊断时间必须包含时区")
        return value
    source: FindingSource

    @model_validator(mode="after")
    def states_are_not_severity(self):
        if self.applicability=="not_applicable" and self.status!="not_applicable":
            raise ValueError("不适用不能伪装为检查通过")
        if self.check_performed != (self.status in ("verified","issue","unknown")):
            raise ValueError("五态与实际检查标志不一致")
        if self.status=="not_applicable" and self.applicability!="not_applicable":
            raise ValueError("不适用必须有明确的适用性判断")
        if self.status=="unknown" and not self.result.missing_items:
            raise ValueError("未知必须说明缺少的证据")
        if self.status=="verified" and not self.evidence_refs:
            raise ValueError("通过必须有可追溯的证据")
        if not self.result.reason_code:
            raise ValueError("所有状态必须有原因")
        return self

class RuleCoverage(FrozenModel):
    implemented: tuple[RuleId,...]
    not_implemented: tuple[str,...]
    evaluated: tuple[RuleId,...]

class DiagnosticAssessment(FrozenModel):
    schema_version: Literal["diagnostic-assessment-v1.1"] = SCHEMA_VERSION
    assessment_id: str
    context: DiagnosticContext
    context_fingerprint: str
    rule_pack: str
    rule_pack_version: str
    coverage: RuleCoverage
    status: Literal["ready","partial","unavailable"]
    snapshot_semantics: Literal["immutable_at_assessment_time"] = "immutable_at_assessment_time"
    findings: tuple[DiagnosticFinding,...]
    observations: dict
    input_manifest: dict
    limitations: tuple[str,...]
    conclusion_policy: Literal["unchanged","conditional_causal_only","show_limitation","hide_integrated_estimate"]
    model_requests: Literal[0] = 0
    execution_authorized: Literal[False] = False
    created_at: str
