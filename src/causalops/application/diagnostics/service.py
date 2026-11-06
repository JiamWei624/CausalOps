"""Explicit, model-free service entry points; no UI hook or automatic statistical work."""
from __future__ import annotations
import json
from causalops.assistant.service import digest,now
from causalops.assistant.runtime import execution_source_sha
from causalops.general.service import DesignError
from .contracts import (
    DiagnosticAssessment,DiagnosticContext,DiagnosticFinding,EvidenceReference,
    RuleReference,CheckResult,Impact,Severity,FindingSource,RuleCoverage,SCHEMA_VERSION,
)
from .evidence import NativeEvidenceReader
from .repository import DiagnosticRepository
from .rules import IMPLEMENTED,NOT_IMPLEMENTED,RULES,evaluate

RULE_PACK="hillstrom-diagnostics-stage1"
RULE_PACK_VERSION="1"
LIMITATIONS=(
    "本阶段仅实现六项证据规则；其余规则未实现，不统计为通过。",
    "来源与人工声明一致不代表程序证明随机分配真实发生。",
    "未新增基线平衡、功效、无干扰或长期利润检验，不能据此声称研究假设全部满足。",
    "诊断不授予执行权限；历史保存事实与当前执行授权分别核验。",
    "没有模型解释、完整建议、用户采纳、三层报告或长期决策记忆。",
)

class DiagnosticService:
    """Reads native sessions/automation tasks and writes only diagnostic-owned tables.

    Calls are explicit: this stage does not subscribe to completion events or alter
    an existing application's workflow. Re-assess before displaying current state;
    get() returns the immutable assessment at its recorded time.
    """
    def __init__(self,service):
        if service.model is not None:
            raise DesignError("诊断事实层只接受无模型服务；本阶段不进行模型调用。")
        self.s=service
        self.reader=NativeEvidenceReader(service)
        self.repo=DiagnosticRepository(service.ws)

    @staticmethod
    def capabilities():
        return {"implemented":list(IMPLEMENTED),"not_implemented":list(NOT_IMPLEMENTED),
                "model_enabled":False,"statistics_execution":False,"schema_version":SCHEMA_VERSION}

    def preflight(self,session_id,*,requested_window=None):
        """Read data/contract only. Never makes a Plan, Approval or statistical Run."""
        return self._assess("preflight",session_id,session_id,requested_window)

    def assess(self,task_id,*,session_id,requested_window=None):
        """Read saved five-step outputs; session identity is always explicit."""
        return self._assess("post_run",task_id,session_id,requested_window)

    def get(self,assessment_id,*,session_id):
        return self.repo.get(assessment_id,session_id)

    def evidence(self,assessment_id,finding_id,*,session_id):
        """Return the saved check receipt and native input references, not a new computation."""
        return self.repo.observation(assessment_id,finding_id,session_id)

    def _assess(self,mode,subject,sid,window):
        if window is not None and (not isinstance(window,str) or not window.strip() or len(window)>220):
            raise DesignError("请提供明确且有界的观察窗口定义。")
        source_sha=execution_source_sha()
        def collect():
            if mode=="preflight":return self.reader.preflight(sid,window,source_sha)
            return self.reader.post_run(subject,sid,window,source_sha)
        # Read twice, boundedly; never freeze a view assembled across competing changes.
        for _ in range(3):
            c=collect();after=collect()
            if digest(c.manifest)==digest(after.manifest):break
        else:raise DesignError("研究证据正在变化，未保存混合快照；请在稳定后重试只读诊断。")
        payload={"native_inputs":c.manifest,"rule_pack":RULE_PACK,"rule_version":RULE_PACK_VERSION,
                 "schema":SCHEMA_VERSION,"implemented":IMPLEMENTED,"diagnostic_source_sha":source_sha}
        fp=digest(payload);aid=digest({"diagnostic_assessment":fp})
        with self.s.ws.connection() as db:
            exists=db.execute("SELECT 1 FROM diagnostic_assessments WHERE id=?",(aid,)).fetchone()
        if exists:return self.repo.get(aid,sid)
        context_body=json.loads(json.dumps(c.context));context_body["fingerprint"]=fp
        context=DiagnosticContext.model_validate(context_body)
        decisions=evaluate(c,window);created=now();findings=[];observations=[]
        for rid in IMPLEMENTED:
            d=decisions[rid];fid=digest({"assessment":aid,"rule":rid})
            oid=digest({"finding":fid,"observation":1})
            observation={"rule_id":rid,"rule_version":"1","context_fingerprint":fp,
                "inputs":c.inputs,"input_manifest_sha":digest(c.manifest),
                "checks":{"status":d.status,"reason_code":d.reason,"observed":d.observed,
                          "expected":d.expected,"missing_items":list(d.missing)}}
            refs=[EvidenceReference(artifact_kind="validation_observation",artifact_id=oid,sha=digest(observation),json_pointer="/checks")]
            refs.extend(EvidenceReference(**item) for item in c.inputs)
            f=DiagnosticFinding(finding_id=fid,assessment_id=aid,context=context,
                rule=RuleReference(id=rid,version="1",pack=RULE_PACK+":"+RULE_PACK_VERSION,check_method=RULES[rid][1]),
                diagnostic_type=RULES[rid][0],applicability="not_applicable" if d.status=="not_applicable" else "applicable",
                check_performed=d.status in ("verified","issue","unknown"),status=d.status,
                result=CheckResult(observed=d.observed,expected=d.expected,reason_code=d.reason,
                    missing_items=d.missing,required_work=d.required),
                evidence_refs=tuple(refs),impact=Impact(claim_effect=d.claim,explanation=d.explanation),
                severity=Severity(level=d.severity,policy_id=RULE_PACK+":"+RULE_PACK_VERSION,reason_code=d.reason),
                human_confirmation_required=bool(d.required),generated_at=created,
                source=FindingSource(mechanism=d.mechanism,origin=d.origin,generator_version=source_sha))
            findings.append(f);observations.append((oid,fid,observation))
        rank={"unchanged":0,"show_limitation":1,"conditional_causal_only":2,"hide_integrated_estimate":3}
        policy=max((f.impact.claim_effect for f in findings),key=rank.get)
        state="unavailable" if c.errors else "partial" if any(f.status=="not_checked" for f in findings) else "ready"
        a=DiagnosticAssessment(assessment_id=aid,context=context,context_fingerprint=fp,
            rule_pack=RULE_PACK,rule_pack_version=RULE_PACK_VERSION,
            coverage=RuleCoverage(implemented=IMPLEMENTED,not_implemented=NOT_IMPLEMENTED,evaluated=IMPLEMENTED),
            status=state,findings=tuple(findings),observations={"data":c.data},input_manifest=payload,
            limitations=LIMITATIONS,conclusion_policy=policy,created_at=created)
        return self.repo.save(a,observations)
