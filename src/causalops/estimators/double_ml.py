from __future__ import annotations

import numpy as np
import pandas as pd
from doubleml import DoubleMLData, DoubleMLPLR
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from causalops.schemas import CausalSpec, DiagnosticResult, EstimateResult

from .base import EstimatorOutput


def estimate_double_ml_plr(
    frame: pd.DataFrame, spec: CausalSpec, *, seed: int = 20261027, n_folds: int = 5
) -> EstimatorOutput:
    required = [spec.treatment, spec.outcome, *spec.covariates]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"DoubleML input is missing columns: {missing}")
    if not spec.covariates:
        raise ValueError("DoubleML requires pre-treatment covariates")
    data = frame[required].dropna().reset_index(drop=True).copy()
    data[spec.treatment] = data[spec.treatment].astype(int)
    if set(data[spec.treatment].unique()) != {0, 1}:
        raise ValueError("DoubleML treatment must contain binary treatment and control observations")
    minimum_group = int(data[spec.treatment].value_counts().min())
    folds = min(n_folds, minimum_group)
    if folds < 2:
        raise ValueError("DoubleML requires at least two observations in each treatment group")

    outcome_learner = HistGradientBoostingRegressor(max_iter=120, learning_rate=0.05, random_state=seed)
    treatment_learner = HistGradientBoostingClassifier(max_iter=120, learning_rate=0.05, random_state=seed)
    dml_data = DoubleMLData(
        data,
        y_col=spec.outcome,
        d_cols=spec.treatment,
        x_cols=spec.covariates,
    )
    model = DoubleMLPLR(
        dml_data,
        ml_l=outcome_learner,
        ml_m=treatment_learner,
        n_folds=folds,
        n_rep=1,
        score="partialling out",
    )
    model.fit(store_predictions=True)
    confidence_interval = model.confint(level=0.95).iloc[0].to_numpy(dtype=float)

    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    propensity = cross_val_predict(
        treatment_learner,
        data[spec.covariates],
        data[spec.treatment],
        cv=splitter,
        method="predict_proba",
        n_jobs=1,
    )[:, 1]
    overlap_rate = float(np.mean((propensity >= 0.05) & (propensity <= 0.95)))
    diagnostics = [
        DiagnosticResult(
            name="cross_fitting_folds",
            passed=folds >= 2,
            value=folds,
            threshold=">= 2",
            message="Number of cross-fitting folds used by DoubleML.",
        ),
        DiagnosticResult(
            name="out_of_fold_propensity_overlap_005_095",
            passed=overlap_rate >= 0.90,
            value=overlap_rate,
            threshold=">= 0.90",
            message="Overlap measured using out-of-fold treatment probabilities.",
        ),
    ]
    warnings = [
        "DoubleML reduces regularization bias through cross-fitting but still requires valid confounder selection, overlap, and no unmeasured confounding."
    ]
    if any(not item.passed for item in diagnostics):
        warnings.append("DoubleML overlap diagnostics failed; do not make a causal claim.")
    return EstimatorOutput(
        estimate=EstimateResult(
            estimand="DoubleML partially linear regression coefficient",
            estimate=float(model.coef[0]),
            standard_error=float(model.se[0]),
            confidence_interval=(float(confidence_interval[0]), float(confidence_interval[1])),
            p_value=float(model.pval[0]),
            sample_size=len(data),
        ),
        diagnostics=diagnostics,
        evidence={
            "n_folds": folds,
            "out_of_fold_propensity_min": float(propensity.min()),
            "out_of_fold_propensity_max": float(propensity.max()),
            "out_of_fold_overlap_rate": overlap_rate,
            "outcome_learner": type(outcome_learner).__name__,
            "treatment_learner": type(treatment_learner).__name__,
        },
        warnings=warnings,
    )
