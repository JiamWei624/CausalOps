import pytest
from pydantic import ValidationError

from causalops.schemas import CausalMethod, CausalSpec, DomainName


def valid_did_payload() -> dict:
    return {
        "question": "Does an AI reply increase subsequent user interactions?",
        "domain": DomainName.UGC,
        "analysis_unit": "user_day",
        "treatment": "ai_reply_received",
        "outcome": "total_interactions",
        "time_column": "event_date",
        "entity_id_column": "user_id",
        "treatment_time_column": "first_ai_reply_date",
        "covariates": ["baseline_activity"],
        "candidate_methods": [CausalMethod.DID],
        "pre_period_days": 30,
        "post_period_days": 30,
    }


def test_valid_did_spec() -> None:
    spec = CausalSpec.model_validate(valid_did_payload())
    assert spec.domain == DomainName.UGC
    assert spec.candidate_methods == [CausalMethod.DID]


def test_did_requires_time_and_entity_columns() -> None:
    payload = valid_did_payload()
    payload["treatment_time_column"] = None
    with pytest.raises(ValidationError, match="DID/event-study requires"):
        CausalSpec.model_validate(payload)


def test_treatment_must_not_be_covariate() -> None:
    payload = valid_did_payload()
    payload["covariates"] = ["ai_reply_received"]
    with pytest.raises(ValidationError, match="must not repeat"):
        CausalSpec.model_validate(payload)

