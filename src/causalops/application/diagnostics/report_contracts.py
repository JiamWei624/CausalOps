"""Three-layer snapshots and bounded user-request drafts; no statistical authority."""
from typing import Literal
from pydantic import Field, model_validator
from .contracts import FrozenModel, DiagnosticContext, DiagnosticFinding, Hash

REPORT_SCHEMA = "diagnostic-report-v1"
SUGGESTION_VERSION = "six-rule-suggestions-v1"
STATE_LABELS = {
    "verified": "已核验满足", "issue": "已发现问题", "unknown": "条件未知或证据不足",
    "not_applicable": "不适用", "not_checked": "尚未检查",
}

class ResearchResults(FrozenModel):
    status: Literal["not_run", "partial", "available", "restricted"]
    objective: str | None
    scope: dict
    approval: dict | None = None
    runs: tuple[dict, ...] = ()
    original_manifest: dict | None = None
    method: str | None = None
    estimate: dict | None = None
    effect: dict | None = None
    group_summary: tuple[dict, ...] = ()
    sample_size: int | None = None
    design_observations: dict
    limitations: tuple[str, ...]
    @model_validator(mode="after")
    def no_unsupported_results(self):
        if self.status != "available" and any(
            x is not None for x in (self.estimate, self.effect, self.sample_size)
        ):
            raise ValueError("不完整或受限报告不能交付联合统计结论")
        if self.status == "available" and (
            len(self.runs) != 2 or not self.original_manifest or not self.estimate or not self.effect
        ):
            raise ValueError("完整报告必须有两个原生运行及有效报告来源")
        return self

class EvidenceQuality(FrozenModel):
    findings: tuple[DiagnosticFinding, ...]
    status_labels: dict
    implemented_rules: tuple[str, ...]
    unimplemented_rules: tuple[str, ...]
    conclusion_policy: str
    limitations: tuple[str, ...]

class ResearchSuggestion(FrozenModel):
    suggestion_id: Hash
    diagnostic_id: Hash
    assessment_id: Hash
    rule_id: str
    rule_version: str
    template_version: Literal["six-rule-suggestions-v1"] = SUGGESTION_VERSION
    context_fingerprint: Hash
    related_refs: dict
    action: str
    reason_code: str
    reason: str
    required_evidence: tuple[str, ...]
    new_scope: Literal["not_proposed", "requires_separate_request"] = "requires_separate_request"
    human_review_required: Literal[True] = True
    status: Literal["needs_information"] = "needs_information"
    limitations: tuple[str, ...]
    source: Literal["deterministic_rule_mapping"] = "deterministic_rule_mapping"
    execution_authorized: Literal[False] = False

class DiagnosticReportManifest(FrozenModel):
    schema_version: Literal["diagnostic-report-v1"] = REPORT_SCHEMA
    report_id: Hash
    version: int = Field(ge=1)
    assessment_id: Hash
    assessment_sha: Hash
    context: DiagnosticContext
    rule_pack: str
    rule_pack_version: str
    suggestion_version: str
    generator_sha: Hash
    results: ResearchResults
    quality: EvidenceQuality
    suggestions: tuple[ResearchSuggestion, ...] = Field(max_length=3)
    generation_source: Literal["explicit_read_only_request"] = "explicit_read_only_request"
    snapshot_semantics: Literal["immutable_at_generation_time"] = "immutable_at_generation_time"
    model_requests: Literal[0] = 0
    execution_authorized: Literal[False] = False
    created_at: str

    @model_validator(mode="after")
    def bound_layers(self):
        if any(f.assessment_id != self.assessment_id or f.context != self.context
               for f in self.quality.findings):
            raise ValueError("报告只能引用同一诊断上下文")
        findings = {f.finding_id: f for f in self.quality.findings}
        if len({s.suggestion_id for s in self.suggestions}) != len(self.suggestions):
            raise ValueError("建议不能重复")
        for s in self.suggestions:
            f = findings.get(s.diagnostic_id)
            if (f is None or f.status not in ("issue", "unknown")
                    or s.assessment_id != self.assessment_id or s.rule_id != f.rule.id
                    or s.rule_version != f.rule.version
                    or s.reason_code != f.result.reason_code
                    or s.context_fingerprint != self.context.fingerprint
                    or s.related_refs["evidence"] != [r.model_dump(mode="json") for r in f.evidence_refs]):
                raise ValueError("建议缺少同源诊断依据")
        if (self.quality.conclusion_policy == "hide_integrated_estimate"
                and self.results.status not in ("restricted", "not_run")):
            raise ValueError("冲突报告不能交付完整联合结论")
        return self

class ResearchRequestDraft(FrozenModel):
    schema_version: Literal["research-request-draft-v1"] = "research-request-draft-v1"
    draft_id: Hash
    report_id: Hash
    session_id: str
    suggestion_id: Hash
    diagnostic_id: Hash
    assessment_id: Hash
    user_intent: str = Field(min_length=1, max_length=2000)
    proposed_action: str
    required_evidence: tuple[str, ...]
    related_refs: dict
    new_scope: str
    status: Literal["needs_information"] = "needs_information"
    actor: Literal["explicit_user_save"] = "explicit_user_save"
    human_review_required: Literal[True] = True
    execution_authorized: Literal[False] = False
    created_at: str

