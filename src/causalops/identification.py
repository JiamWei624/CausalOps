from __future__ import annotations

from dataclasses import dataclass

from causalops.domain_packs import ExperimentPack, UGCPack
from causalops.schemas import (
    AssignmentMechanism,
    CausalMethod,
    CausalSpec,
    ClaimLevel,
    DataStructure,
    DomainName,
    GateStatus,
    IdentificationCheck,
    IdentificationDecision,
)


@dataclass(frozen=True)
class _MethodAssessment:
    method: CausalMethod
    status: GateStatus
    claim_ceiling: ClaimLevel
    checks: list[IdentificationCheck]


def _check(
    name: str,
    condition: bool | None,
    passed: str,
    missing: str,
    *,
    false_is_blocking: bool = True,
) -> IdentificationCheck:
    if condition is True:
        return IdentificationCheck(name=name, status=GateStatus.PASS, message=passed)
    if condition is None:
        return IdentificationCheck(
            name=name, status=GateStatus.NEEDS_REVIEW, message=missing, blocking=False
        )
    return IdentificationCheck(
        name=name,
        status=GateStatus.BLOCKED if false_is_blocking else GateStatus.NEEDS_REVIEW,
        message=missing,
        blocking=false_is_blocking,
    )


def _has_assumption(spec: CausalSpec, *terms: str) -> bool:
    text = " ".join(spec.identification_assumptions).lower()
    return any(term.lower() in text for term in terms)


def _summarize_status(checks: list[IdentificationCheck]) -> GateStatus:
    if any(check.blocking and check.status == GateStatus.BLOCKED for check in checks):
        return GateStatus.BLOCKED
    if any(check.status == GateStatus.NEEDS_REVIEW for check in checks):
        return GateStatus.NEEDS_REVIEW
    return GateStatus.PASS


def _assess_method(spec: CausalSpec, method: CausalMethod) -> _MethodAssessment:
    checks: list[IdentificationCheck] = []
    ceiling = ClaimLevel.REDUCED_FORM

    if method == CausalMethod.DESCRIPTIVE:
        checks.append(_check("descriptive_fallback", True, "Descriptive analysis is available.", ""))
        return _MethodAssessment(method, GateStatus.PASS, ClaimLevel.DESCRIPTIVE, checks)

    if method in {CausalMethod.AB_TEST, CausalMethod.CUPED}:
        checks.extend(
            [
                _check(
                    "randomized_assignment",
                    spec.assignment_mechanism == AssignmentMechanism.RANDOMIZED,
                    "Treatment assignment is declared randomized.",
                    "Verified randomized assignment is required.",
                ),
                _check(
                    "randomization_unit",
                    bool(spec.entity_id_column),
                    "Randomization-unit identifier is present.",
                    "Provide the randomization-unit identifier.",
                ),
            ]
        )
        if method == CausalMethod.CUPED:
            checks.append(
                _check(
                    "pre_treatment_outcome",
                    spec.has_pre_treatment_outcome and bool(spec.covariates),
                    "A pre-treatment outcome/covariate is available for CUPED.",
                    "CUPED requires a pre-treatment outcome or valid pre-period covariate.",
                )
            )
        ceiling = ClaimLevel.IDENTIFIED_CAUSAL

    elif method in {CausalMethod.DID, CausalMethod.EVENT_STUDY}:
        inferred_panel = spec.data_structure in {
            DataStructure.PANEL,
            DataStructure.REPEATED_CROSS_SECTION,
        } or bool(spec.entity_id_column and spec.time_column)
        checks.extend(
            [
                _check(
                    "panel_structure",
                    inferred_panel,
                    "Longitudinal structure and identifiers are available.",
                    "DID requires panel or repeated-cross-section data with time identifiers.",
                ),
                _check(
                    "treatment_timing",
                    bool(spec.treatment_time_column),
                    "Treatment timing is explicitly represented.",
                    "Provide a treatment-time column.",
                ),
                _check(
                    "pre_post_windows",
                    bool(spec.pre_period_days and spec.post_period_days),
                    "Pre- and post-treatment windows are defined.",
                    "Define non-empty pre- and post-treatment windows.",
                ),
                _check(
                    "parallel_trends",
                    spec.parallel_trends_plausible,
                    "Parallel trends is declared plausible and still requires empirical diagnostics.",
                    "Parallel trends has not been justified; run pre-trend/event-study diagnostics.",
                ),
            ]
        )

    elif method == CausalMethod.FIXED_EFFECTS:
        checks.extend(
            [
                _check(
                    "panel_identifiers",
                    bool(spec.entity_id_column and spec.time_column),
                    "Entity and time identifiers are present.",
                    "Fixed effects requires entity and time identifiers.",
                ),
                _check(
                    "strict_exogeneity",
                    True if _has_assumption(spec, "strict exogeneity", "严格外生") else None,
                    "Strict exogeneity is explicitly stated for later review.",
                    "Document and assess the strict-exogeneity assumption.",
                ),
            ]
        )

    elif method in {
        CausalMethod.REGRESSION_ADJUSTMENT,
        CausalMethod.PSM,
        CausalMethod.IPW,
        CausalMethod.DOUBLE_ML,
        CausalMethod.AIPW,
    }:
        checks.extend(
            [
                _check(
                    "pre_treatment_covariates",
                    bool(spec.covariates),
                    "At least one declared pre-treatment covariate is available.",
                    "Provide defensible pre-treatment confounders; post-treatment controls are forbidden.",
                ),
                _check(
                    "conditional_exchangeability",
                    True
                    if _has_assumption(
                        spec,
                        "conditional exchangeability",
                        "ignorability",
                        "no unmeasured confounding",
                        "无未观测混杂",
                    )
                    else None,
                    "Conditional exchangeability is explicitly stated for later review.",
                    "Explain why important treatment-outcome confounders are observed.",
                ),
            ]
        )
        if method in {CausalMethod.PSM, CausalMethod.IPW, CausalMethod.DOUBLE_ML, CausalMethod.AIPW}:
            checks.append(
                _check(
                    "positivity_overlap",
                    spec.positivity_plausible,
                    "Overlap/positivity is declared plausible and still requires diagnostics.",
                    "Overlap is unverified; run propensity-support and weight diagnostics.",
                )
            )

    status = _summarize_status(checks)
    if status == GateStatus.NEEDS_REVIEW:
        ceiling = ClaimLevel.ASSOCIATIONAL
    elif status == GateStatus.BLOCKED:
        ceiling = ClaimLevel.DESCRIPTIVE
    return _MethodAssessment(method, status, ceiling, checks)


def _domain_errors(spec: CausalSpec) -> list[str]:
    if spec.domain == DomainName.UGC:
        return UGCPack().validate_spec(spec)
    if spec.domain == DomainName.EXPERIMENT:
        return ExperimentPack().validate_spec(spec)
    return []


def route_identification(spec: CausalSpec) -> IdentificationDecision:
    """Route a research question without overstating causal identification."""

    domain_errors = _domain_errors(spec)
    if domain_errors:
        checks = [
            IdentificationCheck(
                name="domain_pack",
                status=GateStatus.BLOCKED,
                message=message,
                blocking=True,
            )
            for message in domain_errors
        ]
        return IdentificationDecision(
            selected_method=CausalMethod.DESCRIPTIVE,
            status=GateStatus.BLOCKED,
            claim_ceiling=ClaimLevel.DESCRIPTIVE,
            checks=checks,
            candidate_methods_considered=spec.candidate_methods,
            required_actions=domain_errors,
        )

    candidates = list(dict.fromkeys(spec.candidate_methods)) or [CausalMethod.DESCRIPTIVE]
    assessments = [_assess_method(spec, method) for method in candidates]
    selected = next((item for item in assessments if item.status == GateStatus.PASS), None)
    if selected is None:
        selected = next((item for item in assessments if item.status == GateStatus.NEEDS_REVIEW), None)
    if selected is None:
        selected = _assess_method(spec, CausalMethod.DESCRIPTIVE)
        status = GateStatus.BLOCKED
        checks = [check for assessment in assessments for check in assessment.checks]
    else:
        status = selected.status
        checks = selected.checks

    actions = [
        check.message
        for check in checks
        if check.status in {GateStatus.NEEDS_REVIEW, GateStatus.BLOCKED}
    ]
    return IdentificationDecision(
        selected_method=selected.method,
        status=status,
        claim_ceiling=selected.claim_ceiling,
        checks=checks,
        candidate_methods_considered=candidates,
        required_actions=actions,
    )
