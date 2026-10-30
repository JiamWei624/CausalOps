from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from causalops.schemas import CausalSpec, DiagnosticResult, EstimateResult

from .base import EstimatorOutput


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sum(values * weights) / np.sum(weights))


def _effective_sample_size(weights: np.ndarray) -> float:
    return float(np.sum(weights) ** 2 / np.sum(weights**2))


def _weighted_smd(
    data: pd.DataFrame, spec: CausalSpec, treated_weights: np.ndarray, control_weights: np.ndarray
) -> dict[str, float]:
    treated = data[spec.treatment].to_numpy() == 1
    control = ~treated
    values: dict[str, float] = {}
    for column in spec.covariates:
        x = data[column].to_numpy(dtype=float)
        mean_t = _weighted_mean(x[treated], treated_weights)
        mean_c = _weighted_mean(x[control], control_weights)
        var_t = _weighted_mean((x[treated] - mean_t) ** 2, treated_weights)
        var_c = _weighted_mean((x[control] - mean_c) ** 2, control_weights)
        pooled = math.sqrt((var_t + var_c) / 2)
        values[column] = 0.0 if pooled == 0 else (mean_t - mean_c) / pooled
    return values


def estimate_ipw_ate(
    frame: pd.DataFrame, spec: CausalSpec, *, seed: int = 20261027, bootstrap_samples: int = 300
) -> EstimatorOutput:
    required = [spec.treatment, spec.outcome, *spec.covariates]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"IPW input is missing columns: {missing}")
    if not spec.covariates:
        raise ValueError("IPW requires pre-treatment covariates")
    data = frame[required].dropna().reset_index(drop=True).copy()
    data[spec.treatment] = data[spec.treatment].astype(int)
    if set(data[spec.treatment].unique()) != {0, 1}:
        raise ValueError("IPW treatment must contain binary treatment and control observations")

    model = Pipeline(
        [("scale", StandardScaler()), ("logit", LogisticRegression(max_iter=2_000, random_state=seed))]
    )
    model.fit(data[spec.covariates], data[spec.treatment])
    propensity = np.clip(model.predict_proba(data[spec.covariates])[:, 1], 1e-3, 1 - 1e-3)
    treatment = data[spec.treatment].to_numpy(dtype=int)
    outcome = data[spec.outcome].to_numpy(dtype=float)
    treated = treatment == 1
    control = ~treated
    weights_t = 1 / propensity[treated]
    weights_c = 1 / (1 - propensity[control])
    estimate = _weighted_mean(outcome[treated], weights_t) - _weighted_mean(outcome[control], weights_c)

    rng = np.random.default_rng(seed)
    bootstrap: list[float] = []
    for _ in range(bootstrap_samples):
        sample = rng.integers(0, len(data), len(data))
        t_b = treatment[sample]
        if len(np.unique(t_b)) < 2:
            continue
        y_b = outcome[sample]
        x_b = data.iloc[sample][spec.covariates]
        bootstrap_model = clone(model)
        bootstrap_model.fit(x_b, t_b)
        p_b = np.clip(bootstrap_model.predict_proba(x_b)[:, 1], 1e-3, 1 - 1e-3)
        treated_b = t_b == 1
        bootstrap.append(
            _weighted_mean(y_b[treated_b], 1 / p_b[treated_b])
            - _weighted_mean(y_b[~treated_b], 1 / (1 - p_b[~treated_b]))
        )
    if len(bootstrap) < 50:
        raise ValueError("Too few valid bootstrap samples for IPW uncertainty")
    standard_error = float(np.std(bootstrap, ddof=1))
    z_score = estimate / standard_error if standard_error > 0 else math.inf
    p_value = float(2 * norm.sf(abs(z_score))) if math.isfinite(z_score) else 0.0
    overlap_rate = float(np.mean((propensity >= 0.05) & (propensity <= 0.95)))
    balance = _weighted_smd(data, spec, weights_t, weights_c)
    max_smd = max(abs(value) for value in balance.values())
    max_weight = float(max(weights_t.max(), weights_c.max()))
    diagnostics = [
        DiagnosticResult(
            name="propensity_overlap_005_095",
            passed=overlap_rate >= 0.90,
            value=overlap_rate,
            threshold=">= 0.90",
            message="Share of observations with propensity scores between 0.05 and 0.95.",
        ),
        DiagnosticResult(
            name="maximum_absolute_weighted_smd",
            passed=max_smd <= 0.10,
            value=max_smd,
            threshold="<= 0.10",
            message="Maximum absolute weighted standardized mean difference.",
        ),
        DiagnosticResult(
            name="maximum_inverse_probability_weight",
            passed=max_weight <= 20,
            value=max_weight,
            threshold="<= 20",
            message="Large inverse-probability weights indicate practical positivity problems.",
        ),
    ]
    warnings = ["IPW relies on correct propensity specification and no unmeasured confounding."]
    if any(not item.passed for item in diagnostics):
        warnings.append("At least one IPW diagnostic failed; do not make a causal claim.")
    return EstimatorOutput(
        estimate=EstimateResult(
            estimand="Hájek-normalized inverse-probability-weighted ATE",
            estimate=float(estimate),
            standard_error=standard_error,
            confidence_interval=(estimate - 1.96 * standard_error, estimate + 1.96 * standard_error),
            p_value=p_value,
            sample_size=len(data),
        ),
        diagnostics=diagnostics,
        evidence={
            "bootstrap_samples_requested": bootstrap_samples,
            "bootstrap_samples_used": len(bootstrap),
            "bootstrap_refits_propensity_model": True,
            "propensity_min": float(propensity.min()),
            "propensity_max": float(propensity.max()),
            "maximum_weight": max_weight,
            "treated_effective_sample_size": _effective_sample_size(weights_t),
            "control_effective_sample_size": _effective_sample_size(weights_c),
            "weighted_smd": balance,
        },
        warnings=warnings,
    )
