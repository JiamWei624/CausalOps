"""User decisions are immutable historical records, never research facts or grants."""
from datetime import datetime
from typing import Literal
from pydantic import Field,model_validator,field_validator
from .contracts import FrozenModel,Hash,DiagnosticContext,EvidenceReference,RuleReference,Status
from causalops.assistant.service import digest,now

TYPE_LABELS={"accepted":"采纳建议","deferred":"暂缓处理","rejected":"拒绝建议","note":"自主研究决定"}

class ResearchDecision(FrozenModel):
    schema_version:Literal["research-decision-v1"]="research-decision-v1"
    decision_id:Hash
    context:DiagnosticContext
    report_id:Hash
    report_version:int=Field(ge=1)
    report_sha:Hash
    assessment_id:Hash
    assessment_sha:Hash
    suggestion_id:Hash|None=None
    diagnostic_id:Hash|None=None
    rule:RuleReference|None=None
    finding_status:Status|None=None
    finding_result:dict|None=None
    suggestion_action:str|None=None
    decision_type:Literal["accepted","deferred","rejected","note"]
    reason:str=Field(max_length=2000)
    evidence_refs:tuple[EvidenceReference,...]=Field(min_length=1)
    comparison_key:dict
    supersedes_id:Hash|None=None
    actor:Literal["explicit_user_submit"]="explicit_user_submit"
    execution_authorized:Literal[False]=False
    created_at:str
    source_checked_at:str

    @field_validator("created_at","source_checked_at")
    @classmethod
    def timezone_required(cls,value):
        if datetime.fromisoformat(value).tzinfo is None:raise ValueError("决策时间必须包含时区")
        return value

    @model_validator(mode="after")
    def decision_is_not_evidence(self):
        linked=(self.suggestion_id,self.diagnostic_id,self.rule,self.finding_status,self.finding_result,self.suggestion_action)
        if self.decision_type=="note":
            if any(v is not None for v in linked) or not self.reason.strip():
                raise ValueError("自主研究决定须有备注，不能伪装为建议决定")
        elif any(v is None for v in linked):
            raise ValueError("建议决定必须绑定真实建议及诊断")
        return self

def decision_content(value):
    return value.model_dump(mode="json",exclude={"decision_id","created_at","source_checked_at"})

def make_decision(fields):
    timestamp=now()
    value=ResearchDecision(decision_id="0"*64,created_at=timestamp,source_checked_at=timestamp,**fields)
    return value.model_copy(update={"decision_id":digest({"research_decision_v1":decision_content(value)})})
