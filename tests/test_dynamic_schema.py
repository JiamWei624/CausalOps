import pytest

from causalops.llm import build_dynamic_causal_spec_schema


def test_dynamic_schema_restricts_all_column_references() -> None:
    schema = build_dynamic_causal_spec_schema(
        ["user_id", "treated", "outcome", "pre_posts"],
        allowed_source_tables=["user_cohort"],
    )
    props = schema["properties"]
    assert props["treatment"]["enum"] == ["outcome", "pre_posts", "treated", "user_id"]
    assert props["covariates"]["items"]["enum"] == props["treatment"]["enum"]
    assert props["time_column"]["anyOf"][1] == {"type": "null"}
    assert props["source_tables"]["items"]["enum"] == ["user_cohort"]
    assert props["candidate_methods"]["maxItems"] == 3
    assert props["candidate_methods"]["uniqueItems"] is True
    assert schema["additionalProperties"] is False


def test_dynamic_schema_reserves_identification_evidence_for_review() -> None:
    props = build_dynamic_causal_spec_schema(["x", "y"])["properties"]
    assert props["assignment_mechanism"]["const"] == "unknown"
    assert props["identification_assumptions"]["maxItems"] == 0
    assert props["has_pre_treatment_outcome"]["const"] is False
    assert props["positivity_plausible"]["type"] == "null"


def test_dynamic_schema_rejects_empty_or_excessively_wide_schema() -> None:
    with pytest.raises(ValueError, match="At least one"):
        build_dynamic_causal_spec_schema([])
    with pytest.raises(ValueError, match="500 columns"):
        build_dynamic_causal_spec_schema([f"x{i}" for i in range(501)])
