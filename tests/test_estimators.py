from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from causalops.estimators import estimate_psm_att, estimate_twfe_did
from causalops.execution import execute_analysis
from causalops.schemas import (
    AssignmentMechanism,
    CausalMethod,
    CausalSpec,
    ClaimLevel,
    DataStructure,
    DomainName,
)


def _did_data(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    entities = 160
    periods = 14
    dates = pd.date_range("2025-01-01", periods=periods, freq="D")
    treated_entities = set(range(entities // 2))
    treatment_date = dates[7]
    entity_effect = rng.normal(0, 1, entities)
    rows = []
    for entity in range(entities):
        for period, date in enumerate(dates):
            treated = entity in treated_entities
            post = treated and date >= treatment_date
            rows.append(
                {
                    "user_id": f"u{entity:04d}",
                    "event_date": date,
                    "first_ai_reply_date": treatment_date if treated else pd.NaT,
                    "ai_reply_received": int(post),
                    "baseline_activity": entity_effect[entity],
                    "total_interactions": entity_effect[entity]
                    + 0.08 * period
                    + 2.0 * int(post)
                    + rng.normal(0, 0.20),
                }
            )
    return pd.DataFrame(rows)


def _did_spec() -> CausalSpec:
    return CausalSpec(
        question="Does an AI reply increase subsequent user interactions?",
        domain=DomainName.UGC,
        analysis_unit="user_day",
        treatment="ai_reply_received",
        outcome="total_interactions",
        time_column="event_date",
        entity_id_column="user_id",
        treatment_time_column="first_ai_reply_date",
        covariates=["baseline_activity"],
        candidate_methods=[CausalMethod.DID],
        identification_assumptions=["parallel_trends", "no_anticipation"],
        pre_period_days=7,
        post_period_days=6,
        cluster_column="user_id",
        data_structure=DataStructure.PANEL,
        assignment_mechanism=AssignmentMechanism.OBSERVATIONAL,
        parallel_trends_plausible=True,
    )


def test_twfe_did_recovers_known_effect_and_runs_pretrend_test() -> None:
    output = estimate_twfe_did(_did_data(), _did_spec())
    assert 1.85 < output.estimate.estimate < 2.15
    assert output.estimate.standard_error is not None
    assert any(item.name == "parallel_trends_joint_test" for item in output.diagnostics)
    assert "baseline_activity" in output.evidence["covariates_absorbed_by_entity_effects"]


def test_event_study_matches_independent_group_mean_contrasts() -> None:
    frame = _did_data()
    spec = _did_spec()
    output = estimate_twfe_did(frame, spec)
    first = frame["first_ai_reply_date"].min()
    window = frame["event_date"].between(first - pd.Timedelta(days=7), first + pd.Timedelta(days=5))
    selected = frame.loc[window].copy()
    selected["group"] = selected["first_ai_reply_date"].notna()
    means = selected.groupby(["event_date", "group"])["total_interactions"].mean().unstack()
    group_difference = means[True] - means[False]
    base = group_difference.loc[first - pd.Timedelta(days=1)]
    coefficients = output.evidence["event_study_coefficients"]
    assert output.estimate.sample_size == 160 * 13
    assert "event_m7" in coefficients and "event_m6" in coefficients
    assert "event_p6" not in coefficients
    for day in list(range(-7, -1)) + list(range(0, 6)):
        name = f"event_m{abs(day)}" if day < 0 else f"event_p{day}"
        expected = group_difference.loc[first + pd.Timedelta(days=day)] - base
        assert coefficients[name] == pytest.approx(expected, abs=1e-9)


def test_pretrend_test_is_invariant_to_post_treatment_effect_magnitude() -> None:
    frame = _did_data()
    base = estimate_twfe_did(frame, _did_spec())
    changed = frame.copy()
    changed.loc[changed["ai_reply_received"] == 1, "total_interactions"] += 18.0
    shifted = estimate_twfe_did(changed, _did_spec())
    assert shifted.estimate.estimate == pytest.approx(base.estimate.estimate + 18, abs=1e-9)
    assert shifted.diagnostics[0].value == pytest.approx(base.diagnostics[0].value, abs=1e-9)


def test_pretrend_diagnostic_still_rejects_actual_differential_trends() -> None:
    frame = _did_data()
    treated = frame["first_ai_reply_date"].notna()
    calendar_day = (frame["event_date"] - frame["event_date"].min()).dt.days
    frame.loc[treated, "total_interactions"] += 0.4 * calendar_day[treated]
    output = estimate_twfe_did(frame, _did_spec())
    diagnostic = output.diagnostics[0]
    assert not diagnostic.passed
    assert diagnostic.value < 0.001


def test_psm_improves_observed_covariate_balance() -> None:
    rng = np.random.default_rng(29)
    rows = 800
    x1 = rng.normal(size=rows)
    x2 = rng.normal(size=rows)
    propensity = 1 / (1 + np.exp(-0.8 * x1 + 0.4 * x2))
    treatment = rng.binomial(1, propensity)
    outcome = 1.5 * treatment + 0.8 * x1 - 0.3 * x2 + rng.normal(0, 0.7, rows)
    frame = pd.DataFrame({"treatment": treatment, "outcome": outcome, "x1": x1, "x2": x2})
    spec = CausalSpec(
        question="Does an observational intervention change the measured outcome?",
        domain=DomainName.GENERIC,
        analysis_unit="user",
        treatment="treatment",
        outcome="outcome",
        covariates=["x1", "x2"],
        candidate_methods=[CausalMethod.PSM],
        assignment_mechanism=AssignmentMechanism.OBSERVATIONAL,
        positivity_plausible=True,
        identification_assumptions=["conditional exchangeability given x1 and x2"],
    )
    output = estimate_psm_att(frame, spec)
    assert 0.9 < output.estimate.estimate < 2.1
    assert output.evidence["maximum_absolute_smd_after"] < output.evidence["maximum_absolute_smd_before"]
    assert output.evidence["matched_pairs"] > 100


def test_execution_writes_auditable_result_bundle(tmp_path: Path) -> None:
    bundle = execute_analysis(_did_data(), _did_spec(), tmp_path)
    assert bundle.plan.selected_method == CausalMethod.DID
    assert bundle.claim_level in {ClaimLevel.REDUCED_FORM, ClaimLevel.ASSOCIATIONAL}
    assert len(bundle.evidence["data"]["fingerprint_sha256"]) == 64
    files = list(tmp_path.glob("run-*.json"))
    assert len(files) == 1
    assert bundle.run_id in files[0].name
