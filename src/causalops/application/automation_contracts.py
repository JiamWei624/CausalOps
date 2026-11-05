"""Stage-one fixed Hillstrom plan. No expressions, model code or general DAG."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from causalops.general.exploration import ExplorationDesign
from causalops.general.service import GeneralDesign
from causalops.results.interpretation import MetricDefinition
from causalops.sample_data.hillstrom import QUESTION, SOURCE


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    producer: Literal["S01","S02","S03","S04"]
    evidence_type: Literal["AuditEvidence","DescriptiveRun","GateEvidence","EffectRun"]


class StepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    step_id: Literal["S01","S02","S03","S04","S05"]
    kind: Literal["audit","statistical","gate","report"]
    tool: Literal["audit","exploration","gate","research","report"]
    config: dict
    depends_on: tuple[str, ...]
    inputs: tuple[EvidenceRef, ...]
    output_type: Literal["AuditEvidence","DescriptiveRun","GateEvidence","EffectRun","ReportManifest"]
    preconditions: tuple[Literal["approved_binding","upstream_success","cohort_consistency"], ...]
    authorization: Literal["whole_plan_and_step_recheck"] = "whole_plan_and_step_recheck"
    failure_policy: Literal["stop_descendants_no_automatic_retry"] = "stop_descendants_no_automatic_retry"


def fixed_steps():
    desc = ExplorationDesign(question="核对两组客户的两周访问指标及有效样本分布", method="descriptive",
                             numeric=["visit"], categorical=["assigned"], group="assigned").model_dump(mode="json")
    effect = GeneralDesign(question=QUESTION, analysis_unit="客户", method="ab_test",
                           treatment="assigned", control_value="0", treated_value="1",
                           outcome="visit", entity="entity_id",
                           metric=MetricDefinition(label="两周访问率", unit="概率", kind="binary",
                                                   direction="higher_is_better", ratio_scale=True,
                                                   window="分配后两周", source=SOURCE)).model_dump(mode="json")
    # Only the separately human-confirmed contract can supply this design fact.
    effect.pop("assignment")
    rows = [
        ("S01","audit","audit",{"strict_missing":True},(),(),"AuditEvidence"),
        ("S02","statistical","exploration",desc,("S01",),(("S01","AuditEvidence"),),"DescriptiveRun"),
        ("S03","gate","gate",{"rule":"strict_binary_two_arm_v1"},("S01","S02"),
         (("S01","AuditEvidence"),("S02","DescriptiveRun")),"GateEvidence"),
        ("S04","statistical","research",effect,("S03",),(("S03","GateEvidence"),),"EffectRun"),
        ("S05","report","report",{"model_calls":0},("S01","S02","S03","S04"),
         (("S01","AuditEvidence"),("S02","DescriptiveRun"),("S03","GateEvidence"),("S04","EffectRun")),"ReportManifest"),
    ]
    return tuple(StepSpec(step_id=i,kind=k,tool=t,config=c,depends_on=d,
                          inputs=tuple(EvidenceRef(producer=p,evidence_type=e) for p,e in refs),
                          output_type=o,preconditions=("approved_binding",)+(("upstream_success",) if d else ())
                          +(("cohort_consistency",) if i=="S04" else ()))
                 for i,k,t,c,d,refs,o in rows)


class PlanV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["automation-v2-stage1"] = "automation-v2-stage1"
    plan_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    version: Literal[1] = 1
    objective: Literal[QUESTION] = QUESTION
    data: dict
    contract_ref: dict
    scope: dict
    source_sha: str
    steps: tuple[StepSpec, ...]
    model_requests: Literal[0] = 0

    @model_validator(mode="after")
    def fixed_chain(self):
        if self.steps != fixed_steps():
            raise ValueError("第一阶段只支持已登记的固定五步链，不能更改工具、配置或依赖。")
        if self.scope != scope():
            raise ValueError("当前原型不支持更改指标、组别、窗口或纳入规则。")
        return self


def scope():
    return dict(analysis_unit="客户",entity="entity_id",outcome="visit",metric="两周访问率",
                unit="概率",window="分配后两周",treatment="assigned",
                groups={"0":"未发邮件","1":"男装邮件"},
                inclusion=["Mens E-Mail","No E-Mail"],missing_policy="stop",
                assignment_source=SOURCE)
