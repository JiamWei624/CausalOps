from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DomainName(str, Enum):
    GENERIC = "generic"
    UGC = "ugc"
    EXPERIMENT = "experiment"
    ECOMMERCE = "ecommerce"
    SAAS = "saas"
    CREATOR_INCENTIVE = "creator_incentive"


class CausalMethod(str, Enum):
    AB_TEST = "ab_test"
    CUPED = "cuped"
    REGRESSION_ADJUSTMENT = "regression_adjustment"
    PSM = "psm"
    IPW = "ipw"
    AIPW = "aipw"
    DID = "did"
    EVENT_STUDY = "event_study"
    FIXED_EFFECTS = "fixed_effects"
    DOUBLE_ML = "double_ml"
    DESCRIPTIVE = "descriptive"


class ClaimLevel(str, Enum):
    DESCRIPTIVE = "descriptive"
    ASSOCIATIONAL = "associational"
    REDUCED_FORM = "reduced_form"
    IDENTIFIED_CAUSAL = "identified_causal"


class AssignmentMechanism(str, Enum):
    UNKNOWN = "unknown"
    RANDOMIZED = "randomized"
    AS_IF_RANDOM = "as_if_random"
    OBSERVATIONAL = "observational"


class DataStructure(str, Enum):
    UNKNOWN = "unknown"
    CROSS_SECTION = "cross_section"
    PANEL = "panel"
    REPEATED_CROSS_SECTION = "repeated_cross_section"


class GateStatus(str, Enum):
    PASS = "pass"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"


class CausalSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=8)
    domain: DomainName = DomainName.GENERIC
    analysis_unit: str = Field(min_length=1)
    treatment: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    time_column: str | None = None
    entity_id_column: str | None = None
    treatment_time_column: str | None = None
    covariates: list[str] = Field(default_factory=list)
    candidate_methods: list[CausalMethod] = Field(default_factory=list)
    identification_assumptions: list[str] = Field(default_factory=list)
    pre_period_days: int | None = Field(default=None, ge=1)
    post_period_days: int | None = Field(default=None, ge=1)
    cluster_column: str | None = None
    source_tables: list[str] = Field(default_factory=list)
    assignment_mechanism: AssignmentMechanism = AssignmentMechanism.UNKNOWN
    data_structure: DataStructure = DataStructure.UNKNOWN
    has_pre_treatment_outcome: bool = False
    positivity_plausible: bool | None = None
    no_interference_plausible: bool | None = None
    parallel_trends_plausible: bool | None = None

    @model_validator(mode="after")
    def validate_design(self) -> "CausalSpec":
        if self.treatment == self.outcome:
            raise ValueError("treatment and outcome must be different variables")
        if len(set(self.covariates)) != len(self.covariates):
            raise ValueError("covariates must not contain duplicates")
        forbidden = {self.treatment, self.outcome}.intersection(self.covariates)
        if forbidden:
            raise ValueError(f"covariates must not repeat treatment/outcome: {sorted(forbidden)}")
        if any(method in {CausalMethod.DID, CausalMethod.EVENT_STUDY} for method in self.candidate_methods):
            required = [self.time_column, self.entity_id_column, self.treatment_time_column]
            if not all(required):
                raise ValueError("DID/event-study requires time, entity ID, and treatment-time columns")
        return self


class IdentificationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: GateStatus
    message: str
    blocking: bool = False


class IdentificationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_method: CausalMethod
    status: GateStatus
    claim_ceiling: ClaimLevel
    checks: list[IdentificationCheck] = Field(default_factory=list)
    candidate_methods_considered: list[CausalMethod] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    requires_human_approval: bool = True


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: CausalSpec
    selected_method: CausalMethod
    sql: str
    diagnostics: list[str] = Field(default_factory=list)
    robustness_checks: list[str] = Field(default_factory=list)
    claim_ceiling: ClaimLevel
    requires_human_approval: bool = True


class DiagnosticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    value: float | str | bool | None = None
    threshold: float | str | None = None
    message: str
    claim_blocking: bool = True


class EstimateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimand: str
    estimate: float
    standard_error: float | None = Field(default=None, ge=0)
    confidence_interval: tuple[float, float] | None = None
    p_value: float | None = Field(default=None, ge=0, le=1)
    sample_size: int = Field(ge=1)


class ResultBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    spec: CausalSpec
    plan: AnalysisPlan
    estimate: EstimateResult | None = None
    diagnostics: list[DiagnosticResult] = Field(default_factory=list)
    claim_level: ClaimLevel
    warnings: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)

