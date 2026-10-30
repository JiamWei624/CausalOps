from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.linear_model import LinearRegression

from causalops.schemas import CausalSpec, DiagnosticResult, EstimateResult

from .base import EstimatorOutput


def _validate_randomized(frame: pd.DataFrame, spec: CausalSpec) -> pd.DataFrame:
    required = [spec.treatment, spec.outcome, *spec.covariates]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"Randomized analysis is missing columns: {missing}")
    data = frame[required].dropna().reset_index(drop=True).copy()
    if not set(data[spec.treatment].unique()).issubset({0, 1, False, True}):
        raise ValueError("Randomized treatment must be binary")
    data[spec.treatment] = data[spec.treatment].astype(int)
    if data[spec.treatment].nunique() != 2:
        raise ValueError("Randomized analysis requires treatment and control groups")
    for column in [spec.outcome, *spec.covariates]:
        if not pd.api.types.is_numeric_dtype(data[column]):
            raise ValueError(f"Randomized analysis requires numeric fields: {column}")
    return data


def _difference_in_means(
    data: pd.DataFrame, treatment: str, outcome: str, estimand: str
) -> EstimateResult:
    treated = data.loc[data[treatment] == 1, outcome].to_numpy(dtype=float)
    control = data.loc[data[treatment] == 0, outcome].to_numpy(dtype=float)
    estimate = float(treated.mean() - control.mean())
    standard_error = float(
        math.sqrt(treated.var(ddof=1) / len(treated) + control.var(ddof=1) / len(control))
    )
    z_score = estimate / standard_error if standard_error > 0 else math.inf
    p_value = float(2 * norm.sf(abs(z_score))) if math.isfinite(z_score) else 0.0
    return EstimateResult(
        estimand=estimand,
        estimate=estimate,
        standard_error=standard_error,
        confidence_interval=(estimate - 1.96 * standard_error, estimate + 1.96 * standard_error),
        p_value=p_value,
        sample_size=len(data),
    )


def _covariate_balance(data: pd.DataFrame, spec: CausalSpec) -> tuple[dict[str, float], float]:
    treated = data.loc[data[spec.treatment] == 1]
    control = data.loc[data[spec.treatment] == 0]
    smd: dict[str, float] = {}
    for column in spec.covariates:
        pooled = math.sqrt((treated[column].var(ddof=1) + control[column].var(ddof=1)) / 2)
        smd[column] = (
            0.0 if pooled == 0 or not math.isfinite(pooled)
            else float((treated[column].mean() - control[column].mean()) / pooled)
        )
    return smd, max((abs(value) for value in smd.values()), default=0.0)


def estimate_ab_test(frame: pd.DataFrame, spec: CausalSpec) -> EstimatorOutput:
    data = _validate_randomized(frame, spec)
    estimate = _difference_in_means(
        data, spec.treatment, spec.outcome, "Intent-to-treat difference in means"
    )
    smd, max_smd = _covariate_balance(data, spec)
    diagnostics = [
        DiagnosticResult(
            name="randomized_group_sizes",
            passed=True,
            value=(
                f"treated={(data[spec.treatment] == 1).sum()}, "
                f"control={(data[spec.treatment] == 0).sum()}"
            ),
            message="Both randomized groups are represented.",
        ),
        DiagnosticResult(
            name="maximum_absolute_covariate_smd",
            passed=max_smd <= 0.10,
            value=max_smd,
            threshold="<= 0.10",
            message="Randomization balance check; imbalance is a warning, not automatic proof of invalid randomization.",
            claim_blocking=False,
        ),
    ]
    warnings = [] if max_smd <= 0.10 else ["Observed baseline imbalance exceeds the conventional 0.10 SMD threshold."]
    if not smd:
        diagnostics[-1] = DiagnosticResult(name="baseline_balance_not_assessed", passed=False, value=None,
              message="未指定基线协变量，本次未实施协变量平衡检查；不能将缺少检查解释为完全平衡。",claim_blocking=False)
        warnings.append("未指定基线协变量，本次未实施协变量平衡检查。")
    return EstimatorOutput(
        estimate=estimate,
        diagnostics=diagnostics,
        evidence={"baseline_smd": smd, "maximum_absolute_smd": max_smd if smd else None},
        warnings=warnings,
    )


def estimate_cuped(frame: pd.DataFrame, spec: CausalSpec) -> EstimatorOutput:
    data = _validate_randomized(frame, spec)
    if not spec.covariates:
        raise ValueError("CUPED requires at least one pre-treatment covariate")
    features = data[spec.covariates].to_numpy(dtype=float)
    outcome = data[spec.outcome].to_numpy(dtype=float)
    centered = features - features.mean(axis=0, keepdims=True)
    treatment = data[[spec.treatment]].to_numpy(dtype=float)
    design = np.column_stack([treatment, centered])
    regression = LinearRegression(fit_intercept=True).fit(design, outcome)
    cuped_coefficients = regression.coef_[1:]
    adjusted_outcome = outcome - centered @ cuped_coefficients
    adjusted_name = "__cuped_adjusted_outcome"
    adjusted = data.copy()
    adjusted[adjusted_name] = adjusted_outcome
    estimate = _difference_in_means(
        adjusted,
        spec.treatment,
        adjusted_name,
        "CUPED-adjusted intent-to-treat difference in means",
    )
    original_variance = float(np.var(outcome, ddof=1))
    adjusted_variance = float(np.var(adjusted_outcome, ddof=1))
    reduction = 1 - adjusted_variance / original_variance if original_variance > 0 else 0.0
    smd, max_smd = _covariate_balance(data, spec)
    diagnostics = [
        DiagnosticResult(
            name="cuped_variance_reduction",
            passed=reduction >= 0,
            value=reduction,
            threshold=">= 0",
            message="Relative outcome variance reduction after adjustment with pre-treatment covariates.",
            claim_blocking=False,
        ),
        DiagnosticResult(
            name="maximum_absolute_covariate_smd",
            passed=max_smd <= 0.10,
            value=max_smd,
            threshold="<= 0.10",
            message="Baseline balance of CUPED covariates.",
            claim_blocking=False,
        ),
    ]
    warnings = []
    if reduction < 0:
        warnings.append("CUPED increased variance; prefer the unadjusted A/B estimate.")
    return EstimatorOutput(
        estimate=estimate,
        diagnostics=diagnostics,
        evidence={
            "cuped_covariates": spec.covariates,
            "cuped_coefficients": cuped_coefficients.astype(float).tolist(),
            "original_outcome_variance": original_variance,
            "adjusted_outcome_variance": adjusted_variance,
            "variance_reduction": reduction,
            "baseline_smd": smd,
        },
        warnings=warnings,
    )
