from causalops.domain_packs import UGCPack
from causalops.schemas import CausalMethod, CausalSpec, DomainName


def test_ugc_pack_accepts_followup_window_interactions_for_user_level_psm() -> None:
    spec = CausalSpec(
        question="Does receiving an AI reply change later interactions?",
        domain=DomainName.UGC,
        analysis_unit="user",
        treatment="treated",
        outcome="post_total_interactions",
        entity_id_column="user_id",
        covariates=["pre_total_interactions"],
        candidate_methods=[CausalMethod.PSM],
        positivity_plausible=True,
        identification_assumptions=["conditional exchangeability given pre-treatment activity"],
    )
    assert UGCPack().validate_spec(spec) == []
