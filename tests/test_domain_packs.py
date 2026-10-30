from causalops.domain_packs import ExperimentPack, UGCPack
from causalops.schemas import CausalMethod, CausalSpec, DomainName


def test_ugc_pack_accepts_supported_user_metric() -> None:
    spec = CausalSpec(
        question="Does an AI reply increase later user interactions?",
        domain=DomainName.UGC,
        analysis_unit="user_day",
        treatment="ai_reply_received",
        outcome="total_interactions",
        time_column="event_date",
        entity_id_column="user_id",
        treatment_time_column="first_ai_reply_date",
        candidate_methods=[CausalMethod.DID],
    )
    assert UGCPack().validate_spec(spec) == []


def test_experiment_pack_rejects_non_experimental_method() -> None:
    spec = CausalSpec(
        question="Does the new entry point increase seven-day retention?",
        domain=DomainName.EXPERIMENT,
        analysis_unit="user",
        treatment="assignment",
        outcome="retention_7d",
        entity_id_column="user_id",
        candidate_methods=[CausalMethod.PSM],
    )
    errors = ExperimentPack().validate_spec(spec)
    assert any("only A/B testing and CUPED" in error for error in errors)

