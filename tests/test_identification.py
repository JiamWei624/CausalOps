from causalops.identification import route_identification
from causalops.schemas import (
    AssignmentMechanism,
    CausalMethod,
    CausalSpec,
    ClaimLevel,
    DataStructure,
    DomainName,
    GateStatus,
)


def test_randomized_experiment_routes_to_ab_test() -> None:
    spec = CausalSpec(
        question="Does the randomized entry point increase seven-day retention?",
        domain=DomainName.EXPERIMENT,
        analysis_unit="user",
        treatment="assignment",
        outcome="retention_7d",
        entity_id_column="user_id",
        assignment_mechanism=AssignmentMechanism.RANDOMIZED,
        candidate_methods=[CausalMethod.AB_TEST],
    )
    decision = route_identification(spec)
    assert decision.status == GateStatus.PASS
    assert decision.selected_method == CausalMethod.AB_TEST
    assert decision.claim_ceiling == ClaimLevel.IDENTIFIED_CAUSAL


def test_did_without_parallel_trends_requires_review_and_downgrades_claim() -> None:
    spec = CausalSpec(
        question="Does an AI reply increase subsequent user interactions?",
        domain=DomainName.UGC,
        analysis_unit="user_day",
        treatment="ai_reply_received",
        outcome="total_interactions",
        time_column="event_date",
        entity_id_column="user_id",
        treatment_time_column="first_ai_reply_date",
        candidate_methods=[CausalMethod.DID],
        pre_period_days=28,
        post_period_days=28,
        data_structure=DataStructure.PANEL,
    )
    decision = route_identification(spec)
    assert decision.status == GateStatus.NEEDS_REVIEW
    assert decision.selected_method == CausalMethod.DID
    assert decision.claim_ceiling == ClaimLevel.ASSOCIATIONAL
    assert any(check.name == "parallel_trends" for check in decision.checks)


def test_observational_psm_routes_only_after_structured_assumptions() -> None:
    spec = CausalSpec(
        question="Does an AI reply increase subsequent user interactions?",
        domain=DomainName.UGC,
        analysis_unit="user",
        treatment="ai_reply_received",
        outcome="total_interactions",
        entity_id_column="user_id",
        covariates=["baseline_activity"],
        candidate_methods=[CausalMethod.PSM],
        assignment_mechanism=AssignmentMechanism.OBSERVATIONAL,
        positivity_plausible=True,
        identification_assumptions=["conditional exchangeability given baseline activity"],
    )
    decision = route_identification(spec)
    assert decision.status == GateStatus.PASS
    assert decision.selected_method == CausalMethod.PSM
    assert decision.claim_ceiling == ClaimLevel.REDUCED_FORM


def test_invalid_domain_metric_blocks_causal_routing() -> None:
    spec = CausalSpec(
        question="Does an AI reply change an undefined business metric?",
        domain=DomainName.UGC,
        analysis_unit="user",
        treatment="ai_reply_received",
        outcome="unknown_metric",
        entity_id_column="user_id",
        covariates=["baseline_activity"],
        candidate_methods=[CausalMethod.REGRESSION_ADJUSTMENT],
    )
    decision = route_identification(spec)
    assert decision.status == GateStatus.BLOCKED
    assert decision.selected_method == CausalMethod.DESCRIPTIVE
    assert decision.claim_ceiling == ClaimLevel.DESCRIPTIVE
