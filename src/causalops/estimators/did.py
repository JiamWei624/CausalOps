from __future__ import annotations

import math

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

from causalops.schemas import CausalSpec, DiagnosticResult, EstimateResult

from .base import EstimatorOutput


def _required_columns(spec: CausalSpec) -> list[str]:
    columns = [
        spec.entity_id_column,
        spec.time_column,
        spec.treatment_time_column,
        spec.outcome,
        *spec.covariates,
    ]
    return [column for column in columns if column]


def _prepare_panel(frame: pd.DataFrame, spec: CausalSpec) -> tuple[pd.DataFrame, list[str]]:
    missing = sorted(set(_required_columns(spec)) - set(frame.columns))
    if missing:
        raise ValueError(f"DID input is missing columns: {missing}")
    entity = str(spec.entity_id_column)
    time = str(spec.time_column)
    treatment_time = str(spec.treatment_time_column)

    data = frame[_required_columns(spec)].copy()
    data[time] = pd.to_datetime(data[time], errors="raise")
    data[treatment_time] = pd.to_datetime(data[treatment_time], errors="coerce")
    if data[[entity, time, spec.outcome]].isna().any().any():
        raise ValueError("DID entity, time, and outcome columns must not contain missing values")
    if data.duplicated([entity, time]).any():
        raise ValueError("DID requires one row per entity-time pair")
    if not pd.api.types.is_numeric_dtype(data[spec.outcome]):
        raise ValueError("DID outcome must be numeric")

    observed_treatment_times = data[treatment_time].dropna()
    if observed_treatment_times.empty:
        raise ValueError("DID requires at least one observed treatment time")
    calendar_start = observed_treatment_times.min() - pd.Timedelta(days=int(spec.pre_period_days or 1))
    # The post window includes day zero: six days means 0..5, as in the audit.
    calendar_end = observed_treatment_times.max() + pd.Timedelta(days=int(spec.post_period_days or 1) - 1)
    data = data.loc[data[time].between(calendar_start, calendar_end)].copy()

    data["ever_treated"] = data[treatment_time].notna().astype(np.int8)
    data["post_treatment"] = (
        data[treatment_time].notna() & (data[time] >= data[treatment_time])
    ).astype(np.int8)
    if data["ever_treated"].nunique() != 2:
        raise ValueError("DID requires both treated and never-treated entities")
    if data.loc[data["ever_treated"] == 1, "post_treatment"].nunique() != 2:
        raise ValueError("Treated entities must have both pre- and post-treatment observations")

    varying_covariates: list[str] = []
    dropped_covariates: list[str] = []
    for covariate in spec.covariates:
        if not pd.api.types.is_numeric_dtype(data[covariate]):
            raise ValueError(f"DID covariate must be numeric: {covariate}")
        if data.groupby(entity)[covariate].nunique(dropna=False).max() > 1:
            varying_covariates.append(covariate)
        else:
            dropped_covariates.append(covariate)
    return data, dropped_covariates


def _fit_panel(
    data: pd.DataFrame, spec: CausalSpec, exogenous: list[str]
):
    entity = str(spec.entity_id_column)
    time = str(spec.time_column)
    panel = data.set_index([entity, time]).sort_index()
    model = PanelOLS(
        dependent=panel[spec.outcome].astype(float),
        exog=panel[exogenous].astype(float),
        entity_effects=True,
        time_effects=True,
        drop_absorbed=True,
        check_rank=True,
    )
    return model.fit(cov_type="clustered", cluster_entity=True)


def _parallel_trends_diagnostic(
    data: pd.DataFrame, spec: CausalSpec
) -> tuple[DiagnosticResult, dict[str, float], list[dict[str, object]]]:
    time = str(spec.time_column)
    treatment_time = str(spec.treatment_time_column)
    event_day = (data[time] - data[treatment_time]).dt.days
    event_columns: list[str] = []
    lead_columns: list[str] = []
    # Cover every observed treated period and omit only -1. Omitting distant
    # leads/lags without binning them contaminates the reference with post effects.
    observed_event_days = sorted(int(day) for day in event_day.dropna().unique())
    for relative_day in observed_event_days:
        if relative_day == -1:
            continue
        name = f"event_m{abs(relative_day)}" if relative_day < 0 else f"event_p{relative_day}"
        data[name] = (event_day == relative_day).astype(np.int8)
        if data[name].sum() > 0:
            event_columns.append(name)
            if relative_day <= -2:
                lead_columns.append(name)

    if not lead_columns:
        return (
            DiagnosticResult(
                name="parallel_trends_joint_test",
                passed=False,
                value="not_estimable",
                threshold="p >= 0.05",
                message="No estimable pre-treatment event-time indicators were available.",
            ),
            {},
            [],
        )
    if not bool((event_day == -1).any()):
        return (
            DiagnosticResult(
                name="parallel_trends_joint_test", passed=False, value="not_estimable",
                threshold="p >= 0.05",
                message="No estimable pre-treatment event-time indicators were available.",
            ),
            {},
            [],
        )
    result = _fit_panel(data, spec, event_columns)
    available_leads = [name for name in lead_columns if name in result.params.index]
    if not available_leads:
        return (
            DiagnosticResult(
                name="parallel_trends_joint_test",
                passed=False,
                value="absorbed",
                threshold="p >= 0.05",
                message="Pre-treatment indicators were absorbed by the fixed effects.",
            ),
            {},
            [],
        )
    covariance = result.cov.loc[available_leads, available_leads].to_numpy(dtype=float)
    if not np.isfinite(covariance).all() or np.linalg.matrix_rank(covariance) < len(available_leads):
        return (
            DiagnosticResult(
                name="parallel_trends_joint_test", passed=False, value="not_estimable",
                threshold="p >= 0.05",
                message="Pre-treatment coefficient covariance is singular; the joint test is not estimable.",
            ),
            {},
            [],
        )
    # Use the library's clustered-covariance Wald test rather than a silent
    # pseudo-inverse with potentially incorrect degrees of freedom.
    restriction = np.zeros((len(available_leads), len(result.params)))
    for row, name in enumerate(available_leads):
        restriction[row, result.params.index.get_loc(name)] = 1.0
    joint_test = result.wald_test(restriction=restriction, value=np.zeros(len(available_leads)))
    p_value = float(joint_test.pval)
    coefficients = {name: float(result.params[name]) for name in event_columns if name in result.params}
    intervals = result.conf_int(level=0.95)
    table = []
    for day in observed_event_days:
        if day == -1:
            # The reference is normalized to zero, not an estimated zero effect.
            table.append({"relative_day": -1, "estimate": 0.0, "standard_error": None,
                          "ci_lower": None, "ci_upper": None, "is_reference": True})
            continue
        name = f"event_m{abs(day)}" if day < 0 else f"event_p{day}"
        if name in result.params:
            table.append({
                "relative_day": day, "estimate": float(result.params[name]),
                "standard_error": float(result.std_errors[name]),
                "ci_lower": float(intervals.loc[name, "lower"]),
                "ci_upper": float(intervals.loc[name, "upper"]), "is_reference": False,
                "degrees_of_freedom": int(result.df_resid), "confidence_level": 0.95,
            })
    return (
        DiagnosticResult(
            name="parallel_trends_joint_test",
            passed=p_value >= 0.05,
            value=p_value,
            threshold="p >= 0.05",
            message=(
                "Failed to reject jointly zero pre-treatment coefficients; this supports but does not prove "
                "parallel trends."
                if p_value >= 0.05
                else "Pre-treatment coefficients are jointly significant; causal DID interpretation is blocked."
            ),
        ),
        coefficients,
        table,
    )


def estimate_twfe_did(frame: pd.DataFrame, spec: CausalSpec) -> EstimatorOutput:
    """Estimate a two-way-fixed-effects DID with entity-clustered uncertainty."""

    data, dropped_covariates = _prepare_panel(frame, spec)
    entity = str(spec.entity_id_column)
    treatment_time = str(spec.treatment_time_column)
    varying_covariates = [column for column in spec.covariates if column not in dropped_covariates]
    result = _fit_panel(data, spec, ["post_treatment", *varying_covariates])
    coefficient = float(result.params["post_treatment"])
    standard_error = float(result.std_errors["post_treatment"])
    p_value = float(result.pvalues["post_treatment"])
    confidence_interval = result.conf_int().loc["post_treatment"].to_numpy(dtype=float)
    parallel_diagnostic, event_coefficients, event_table = _parallel_trends_diagnostic(data, spec)

    treatment_dates = data.loc[data["ever_treated"] == 1, treatment_time].dropna().nunique()
    trajectories = []
    if treatment_dates == 1:
        anchor = data[treatment_time].dropna().iloc[0]
        for (date, group), rows in data.groupby([str(spec.time_column), "ever_treated"], sort=True):
            trajectories.append({
                "relative_day": int((date - anchor).days),
                "calendar_date": str(date.date()), "group": "treated" if group else "never_treated",
                "mean_outcome": float(rows[spec.outcome].mean()),
                "observations": int(len(rows)), "users": int(rows[entity].nunique()),
            })
    warnings = [
        "Failure to reject pre-trends is not proof of parallel trends; substantive justification is still required."
    ]
    if treatment_dates > 1:
        warnings.append(
            "Treatment timing is staggered. TWFE can be biased under heterogeneous treatment effects; "
            "use a staggered-adoption estimator before making a final causal claim."
        )
    if dropped_covariates:
        warnings.append(
            "Time-invariant covariates were absorbed by entity fixed effects and omitted: "
            + ", ".join(dropped_covariates)
        )
    if not parallel_diagnostic.passed:
        warnings.append("The pre-trend diagnostic failed; the effect must not be described as causal.")

    diagnostics = [
        parallel_diagnostic,
        DiagnosticResult(
            name="treated_and_control_entities",
            passed=True,
            value=(
                f"treated={data.loc[data['ever_treated'] == 1, entity].nunique()}, "
                f"control={data.loc[data['ever_treated'] == 0, entity].nunique()}"
            ),
            message="Both treated and never-treated entities are present.",
        ),
    ]
    if treatment_dates > 1:
        diagnostics.append(DiagnosticResult(
            name="common_treatment_timing", passed=False, value=int(treatment_dates), threshold="= 1",
            message="Multiple treatment dates require a staggered-adoption estimator before causal interpretation.",
        ))
    return EstimatorOutput(
        estimate=EstimateResult(
            estimand="TWFE DID coefficient on post-treatment exposure",
            estimate=coefficient,
            standard_error=standard_error,
            confidence_interval=(float(confidence_interval[0]), float(confidence_interval[1])),
            p_value=p_value,
            sample_size=len(data),
        ),
        diagnostics=diagnostics,
        evidence={
            "estimator_version": "twfe_did_v2_complete_event_reference",
            "event_study_reference_day": -1,
            "method_reference_urls": [
                "https://lost-stats.github.io/Model_Estimation/Research_Design/event_study.html",
                "https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.results.PanelResults.wald_test.html",
            ],
            "post_window_includes_day_zero": True,
            "post_window_last_day": int(spec.post_period_days or 1) - 1,
            "entity_count": int(data[entity].nunique()),
            "treated_entity_count": int(data.loc[data["ever_treated"] == 1, entity].nunique()),
            "control_entity_count": int(data.loc[data["ever_treated"] == 0, entity].nunique()),
            "distinct_treatment_dates": int(treatment_dates),
            "event_study_coefficients": event_coefficients,
            "event_study_table": event_table,
            "group_trajectories": trajectories,
            "event_study_inference": "entity_clustered_pointwise_95_percent",
            "diagnostic_charts_available": bool(treatment_dates == 1 and event_table),
            "covariates_absorbed_by_entity_effects": dropped_covariates,
            "rsquared_within": float(result.rsquared_within) if math.isfinite(result.rsquared_within) else None,
        },
        warnings=warnings,
    )
