"""Model-free three-layer report service over immutable native evidence."""
from pathlib import Path
import json
from causalops.assistant.service import digest, now
from causalops.general.service import DesignError
from .service import DiagnosticService
from .report_contracts import (
    REPORT_SCHEMA, SUGGESTION_VERSION, STATE_LABELS,
    ResearchResults, EvidenceQuality, ResearchRequestDraft,
)
from .report_repository import ReportRepository
from .suggestions import build_suggestions

class DiagnosticReportService:
    def __init__(self, service):
        self.s = service
        self.diagnostics = DiagnosticService(service)
        self.repo = ReportRepository(service.ws)

    @staticmethod
    def capabilities():
        return {"model_enabled": False, "statistics_execution": False,
                "schema": REPORT_SCHEMA, "generation": "explicit_read_only_request",
                "drafts": "explicit_user_save_only"}

    def preflight(self, session_id, *, requested_window=None):
        a = self.diagnostics.preflight(session_id, requested_window=requested_window)
        return self.generate(a.assessment_id, session_id=session_id)

    def post_run(self, task_id, *, session_id, requested_window=None):
        a = self.diagnostics.assess(task_id, session_id=session_id, requested_window=requested_window)
        return self.generate(a.assessment_id, session_id=session_id)

    def _collection(self, assessment):
        ctx = assessment.context
        sid = ctx.task_ref.session_id
        window = assessment.input_manifest["native_inputs"]["requested_window"]
        source_sha = ctx.provenance.diagnostic_source_sha
        if ctx.phase == "preflight":
            return self.diagnostics.reader.preflight(sid, window, source_sha)
        return self.diagnostics.reader.post_run(ctx.task_ref.task_id, sid, window, source_sha)

    def _verify_inputs(self, assessment):
        # Reuse the recorded read-mode identity when reading an older assessment.
        expected = digest(assessment.input_manifest["native_inputs"])
        first = self._collection(assessment)
        second = self._collection(assessment)
        if digest(first.manifest) != expected or digest(second.manifest) != expected:
            raise DesignError("原生证据已变化，请生成新的诊断快照；旧报告仍可只读查看。")
        for finding in assessment.findings:
            self.diagnostics.evidence(assessment.assessment_id, finding.finding_id,
                                      session_id=assessment.context.task_ref.session_id)
        return second

    def generate(self, assessment_id, *, session_id):
        a = self.diagnostics.get(assessment_id, session_id=session_id)
        c = self._verify_inputs(a)
        fields = ["report_contracts.py", "suggestions.py", "reports.py", "report_repository.py"]
        generator = digest({name: Path(__file__).with_name(name).read_text(encoding="utf8")
                            for name in fields})
        results = self._results(a, c)
        quality = EvidenceQuality(
            findings=a.findings, status_labels=STATE_LABELS,
            implemented_rules=a.coverage.implemented,
            unimplemented_rules=a.coverage.not_implemented,
            conclusion_policy=a.conclusion_policy, limitations=a.limitations,
        )
        body = {
            "schema_version": REPORT_SCHEMA, "assessment_id": a.assessment_id,
            "assessment_sha": digest(a.model_dump(mode="json")),
            "context": a.context.model_dump(mode="json"),
            "rule_pack": a.rule_pack, "rule_pack_version": a.rule_pack_version,
            "suggestion_version": SUGGESTION_VERSION, "generator_sha": generator,
            "results": results.model_dump(mode="json"), "quality": quality.model_dump(mode="json"),
            "suggestions": [x.model_dump(mode="json") for x in build_suggestions(a)],
            "generation_source": "explicit_read_only_request",
        }
        body["report_id"] = digest(body)
        body["created_at"] = now()
        return self.repo.save_report(body)

    def _results(self, a, c):
        states = {f.rule.id: f.status for f in a.findings}
        available = (a.context.phase == "post_run" and a.conclusion_policy != "hide_integrated_estimate"
                     and all(states[r] == "verified" for r in ("PD-01","PD-06","PD-07","PD-09","PD-14")))
        status = ("not_run" if a.context.phase == "preflight" else
                  "restricted" if a.conclusion_policy == "hide_integrated_estimate" else
                  "available" if available else "partial")
        receipt = None
        if c.task:
            with self.s.ws.connection() as db:
                row = db.execute("SELECT id,body,sha,revoked FROM automation_v2_approvals WHERE task_id=?",
                                 (c.task["id"],)).fetchone()
            # Advertise original approval only when identity checks accepted it.
            if row and states["PD-01"] == "verified":
                receipt = {"id": row[0], "sha": row[2], "plan_version": a.context.plan_ref.version,
                           "revoked": bool(row[3]), "execution_permission": "not_granted_by_report"}
        result = dict(
            status=status, objective=c.task["plan"]["objective"] if c.task else None,
            scope=a.context.scope.model_dump(mode="json"), approval=receipt,
            runs=tuple(x.model_dump(mode="json") for x in a.context.run_refs),
            design_observations=a.observations["data"],
            limitations=("历史回执只描述原批准；新计算仍需原服务核验。",
                         "来源登记一致不能证明所有识别假设；当前对象和窗口不能外推其他指标、人群或长期收益。",
                         "如涉及A/B，原工具采用独立组均值差与1.96正态近似区间；小样本或稀少事件时近似可能不充分，不等于精确随机化检验。"),
        )
        if available:
            bundle = c.bundles["S04"]
            manifest = c.evidence["S05"]["body"]
            reference = next(r for r in c.inputs
                             if r["artifact_kind"] == "step_evidence" and r["artifact_id"].endswith(":S05"))
            result.update(
                original_manifest={"id": reference["artifact_id"], "sha": reference["sha"],
                                   "kind": "saved_S05_ReportManifest"},
                method=bundle.plan.selected_method.value,
                estimate=bundle.estimate.model_dump(mode="json"),
                effect=manifest["effect"],
                group_summary=tuple(bundle.evidence["interpretation_inputs"]["raw_group_summary"]),
                sample_size=bundle.estimate.sample_size,
            )
        if (not available and status=="partial" and not c.errors and c.task and "S01" in c.evidence and "S02" in c.evidence
            and states["PD-01"]=="verified" and states["PD-06"]=="verified"):
            from causalops.application.configurable_report import descriptive_summary
            result["descriptive"]=descriptive_summary(c.task,c.evidence["S02"],c.evidence["S01"])
        return ResearchResults(**result)

    def get(self, report_id, *, session_id):
        report = self.repo.get(report_id, session_id)
        a = self.diagnostics.get(report.assessment_id, session_id=session_id)
        if (digest(a.model_dump(mode="json")) != report.assessment_sha
                or report.quality.findings != a.findings
                or report.context != a.context):
            raise DesignError("报告与诊断来源不一致。")
        return report

    def save_draft(self, report_id, suggestion_id, *, session_id, user_intent,
                   request_id, human_confirmed=False):
        if human_confirmed is not True:
            raise DesignError("保存研究需求需要明确的用户操作。")
        for value, limit in ((user_intent, 2000), (request_id, 128)):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise DesignError("研究需求和请求标识必须明确且有界。")
        report = self.get(report_id, session_id=session_id)
        a = self.diagnostics.get(report.assessment_id, session_id=session_id)
        self._verify_inputs(a)
        suggestion = next((s for s in report.suggestions if s.suggestion_id == suggestion_id), None)
        if suggestion is None:
            raise DesignError("该建议不属于当前报告。")
        body = dict(
            report_id=report_id, session_id=session_id, suggestion_id=suggestion_id,
            assessment_id=report.assessment_id, diagnostic_id=suggestion.diagnostic_id,
            user_intent=user_intent, proposed_action=suggestion.action,
            required_evidence=suggestion.required_evidence, related_refs=suggestion.related_refs,
            new_scope=suggestion.new_scope,
        )
        body["draft_id"] = digest({"draft": body, "user_request": request_id})
        return self.repo.save_draft(ResearchRequestDraft(**body, created_at=now()), request_id)

    def get_draft(self, draft_id, *, session_id):
        return self.repo.get(draft_id, session_id, draft=True)

