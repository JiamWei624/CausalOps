from pathlib import Path

import numpy as np
import pandas as pd

from causalops.execution import execute_analysis
from causalops.estimators.preprocessing import prepare_estimator_input
from causalops.metadata import build_field_catalog, sanitize_defaults
from causalops.schemas import CausalMethod, CausalSpec


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "user_id": ["u1", "u2", "u3", "u4"],
            "treated": [0, 1, 0, 1],
            "outcome": [1.0, 3.0, 2.0, 4.0],
            "gender": ["female", "male", "female", "male"],
            "verified": pd.Series([True, False, False, True], dtype="bool"),
            "event_date": pd.to_datetime(["2026-01-01"] * 4),
        }
    )


def test_catalog_keeps_gender_and_verified_as_reviewable_covariates() -> None:
    catalog = build_field_catalog(_frame())
    assert catalog["gender"].can_be_covariate is True
    assert catalog["gender"].requires_encoding is True
    assert catalog["verified"].can_be_covariate is True
    assert catalog["user_id"].can_be_covariate is False
    assert catalog["event_date"].can_be_time is True
    assert catalog["outcome"].can_be_outcome is True


def test_invalid_defaults_are_reported_instead_of_silently_used() -> None:
    valid, invalid = sanitize_defaults(
        ["gender", "deleted_column", "verified"], ["gender", "verified"]
    )
    assert valid == ["gender", "verified"]
    assert invalid == ["deleted_column"]


def test_controlled_preprocessing_encodes_categorical_and_boolean_covariates() -> None:
    frame = _frame()
    spec = CausalSpec(
        question="Estimate the treatment effect with pre-treatment controls.",
        analysis_unit="user",
        treatment="treated",
        outcome="outcome",
        covariates=["gender", "verified"],
        candidate_methods=[CausalMethod.PSM],
    )
    prepared = prepare_estimator_input(frame, spec)
    assert prepared.spec.covariates == ["gender__male", "verified"]
    assert prepared.frame["gender__male"].tolist() == [0.0, 1.0, 0.0, 1.0]
    assert prepared.frame["verified"].tolist() == [1.0, 0.0, 0.0, 1.0]
    assert prepared.evidence["covariate_mapping"] == {
        "gender": ["gender__male"],
        "verified": ["verified"],
    }


def test_psm_executes_with_categorical_and_boolean_covariates(tmp_path: Path) -> None:
    rng = np.random.default_rng(20261027)
    rows = 160
    gender = np.where(np.arange(rows) % 2 == 0, "female", "male")
    verified = rng.binomial(1, 0.35, rows).astype(bool)
    baseline = rng.normal(size=rows)
    propensity = 1 / (
        1
        + np.exp(
            -(
                -0.15
                + 0.25 * (gender == "male")
                + 0.20 * verified.astype(float)
                + 0.20 * baseline
            )
        )
    )
    treated = rng.binomial(1, propensity)
    outcome = 0.60 * treated + 0.35 * baseline + rng.normal(scale=0.6, size=rows)
    frame = pd.DataFrame(
        {
            "treated": treated,
            "outcome": outcome,
            "gender": gender,
            "verified": verified,
            "baseline": baseline,
        }
    )
    spec = CausalSpec(
        question="Estimate the treatment effect with observed pre-treatment confounders.",
        analysis_unit="user",
        treatment="treated",
        outcome="outcome",
        covariates=["gender", "verified", "baseline"],
        candidate_methods=[CausalMethod.PSM],
        identification_assumptions=[
            "conditional exchangeability given observed pre-treatment covariates"
        ],
        positivity_plausible=True,
    )

    bundle = execute_analysis(frame, spec, tmp_path)
    assert bundle.estimate is not None
    assert bundle.plan.selected_method == CausalMethod.PSM
    assert bundle.evidence["preprocessing"]["covariate_mapping"]["gender"] == [
        "gender__male"
    ]
    assert bundle.evidence["preprocessing"]["covariate_mapping"]["verified"] == [
        "verified"
    ]
