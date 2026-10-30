from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from causalops.schemas import CausalSpec, DiagnosticResult, EstimateResult

from .base import EstimatorOutput


def _standardized_mean_difference(
    treated: pd.DataFrame, control: pd.DataFrame, covariates: list[str]
) -> dict[str, float]:
    values: dict[str, float] = {}
    for column in covariates:
        pooled = math.sqrt((treated[column].var(ddof=1) + control[column].var(ddof=1)) / 2)
        difference = float(treated[column].mean() - control[column].mean())
        values[column] = 0.0 if pooled == 0 or not math.isfinite(pooled) else difference / pooled
    return values


def estimate_psm_att(frame: pd.DataFrame, spec: CausalSpec, seed: int = 20261027) -> EstimatorOutput:
    """Estimate an ATT using deterministic 1:1 nearest-neighbour PSM without replacement."""

    required = [spec.treatment, spec.outcome, *spec.covariates]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"PSM input is missing columns: {missing}")
    if not spec.covariates:
        raise ValueError("PSM requires pre-treatment covariates")
    data = frame[required].dropna().reset_index(drop=True).copy()
    if not set(data[spec.treatment].unique()).issubset({0, 1, False, True}):
        raise ValueError("PSM treatment must be binary")
    data[spec.treatment] = data[spec.treatment].astype(int)
    if data[spec.treatment].nunique() != 2:
        raise ValueError("PSM requires treated and control observations")
    for column in [spec.outcome, *spec.covariates]:
        if not pd.api.types.is_numeric_dtype(data[column]):
            raise ValueError(f"PSM requires numeric outcome/covariates: {column}")

    propensity_model = Pipeline(
        [
            ("scale", StandardScaler()),
            ("logit", LogisticRegression(max_iter=2_000, random_state=seed)),
        ]
    )
    propensity_model.fit(data[spec.covariates], data[spec.treatment])
    data["propensity_score"] = np.clip(
        propensity_model.predict_proba(data[spec.covariates])[:, 1], 1e-6, 1 - 1e-6
    )
    treated = data.loc[data[spec.treatment] == 1].copy()
    control = data.loc[data[spec.treatment] == 0].copy()
    support_lower = max(treated["propensity_score"].min(), control["propensity_score"].min())
    support_upper = min(treated["propensity_score"].max(), control["propensity_score"].max())
    in_support = data["propensity_score"].between(support_lower, support_upper)
    supported = data.loc[in_support].copy()
    treated_supported = supported.loc[supported[spec.treatment] == 1].copy()
    control_supported = supported.loc[supported[spec.treatment] == 0].copy()
    treated_support_rate = len(treated_supported) / len(treated)

    logits = logit(data["propensity_score"].to_numpy())
    caliper = 0.2 * float(np.std(logits, ddof=1))
    if not math.isfinite(caliper) or caliper <= 0:
        raise ValueError("PSM caliper is not estimable because propensity scores have no variation")

    available_controls = set(control_supported.index.tolist())
    pairs: list[tuple[int, int, float]] = []
    for treated_index in treated_supported.sort_values("propensity_score").index:
        if not available_controls:
            break
        treated_logit = float(logit(data.at[treated_index, "propensity_score"]))
        candidates = np.array(sorted(available_controls), dtype=int)
        candidate_logits = logit(data.loc[candidates, "propensity_score"].to_numpy())
        distances = np.abs(candidate_logits - treated_logit)
        position = int(np.argmin(distances))
        if float(distances[position]) <= caliper:
            control_index = int(candidates[position])
            pairs.append((int(treated_index), control_index, float(distances[position])))
            available_controls.remove(control_index)
    if len(pairs) < 2:
        raise ValueError("PSM produced fewer than two matched pairs")

    treated_indices = [pair[0] for pair in pairs]
    control_indices = [pair[1] for pair in pairs]
    matched_treated = data.loc[treated_indices]
    matched_control = data.loc[control_indices]
    outcome_differences = (
        matched_treated[spec.outcome].to_numpy(dtype=float)
        - matched_control[spec.outcome].to_numpy(dtype=float)
    )
    estimate = float(np.mean(outcome_differences))
    standard_error = float(np.std(outcome_differences, ddof=1) / math.sqrt(len(pairs)))
    z_score = estimate / standard_error if standard_error > 0 else math.inf
    p_value = float(2 * norm.sf(abs(z_score))) if math.isfinite(z_score) else 0.0
    ci = (estimate - 1.96 * standard_error, estimate + 1.96 * standard_error)

    balance_before = _standardized_mean_difference(treated, control, spec.covariates)
    balance_after = _standardized_mean_difference(matched_treated, matched_control, spec.covariates)
    max_before = max(abs(value) for value in balance_before.values())
    max_after = max(abs(value) for value in balance_after.values())
    match_rate = len(pairs) / len(treated)
    diagnostics = [
        DiagnosticResult(
            name="common_support",
            passed=treated_support_rate >= 0.80,
            value=treated_support_rate,
            threshold=">= 0.80 of treated observations",
            message="Share of treated observations inside the empirical common-support interval.",
        ),
        DiagnosticResult(
            name="treated_match_rate",
            passed=match_rate >= 0.50,
            value=match_rate,
            threshold=">= 0.50",
            message="Share of treated observations retained in 1:1 matching.",
        ),
        DiagnosticResult(
            name="maximum_absolute_smd_after_matching",
            passed=max_after <= 0.10,
            value=max_after,
            threshold="<= 0.10",
            message="Maximum absolute standardized mean difference after matching.",
        ),
    ]
    warnings = [
        "PSM adjusts only for observed pre-treatment covariates; unmeasured confounding remains possible.",
        "The paired-difference standard error is conditional on the estimated match and does not account "
        "for propensity-score estimation; use design-appropriate matching inference for confirmatory claims.",
    ]
    if any(not diagnostic.passed for diagnostic in diagnostics):
        warnings.append("At least one PSM quality diagnostic failed; do not make a causal claim.")
    return EstimatorOutput(
        estimate=EstimateResult(
            estimand="ATT among 1:1 propensity-score matched treated observations",
            estimate=estimate,
            standard_error=standard_error,
            confidence_interval=(float(ci[0]), float(ci[1])),
            p_value=p_value,
            sample_size=2 * len(pairs),
        ),
        diagnostics=diagnostics,
        evidence={
            "input_rows_after_complete_case_filter": len(data),
            "treated_count": len(treated),
            "control_count": len(control),
            "matched_pairs": len(pairs),
            "caliper_logit_sd_units": 0.2,
            "caliper_value": caliper,
            "support_interval": [float(support_lower), float(support_upper)],
            "balance_smd_before": balance_before,
            "balance_smd_after": balance_after,
            "maximum_absolute_smd_before": max_before,
            "maximum_absolute_smd_after": max_after,
            "mean_match_distance": float(np.mean([pair[2] for pair in pairs])),
        },
        warnings=warnings,
    )
