from __future__ import annotations

import hashlib
import json
import platform
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from causalops.estimators.aipw import estimate_aipw_ate
from causalops.capabilities import get_method_capability
from causalops.estimators import (
    estimate_ab_test,
    estimate_cuped,
    estimate_double_ml_plr,
    estimate_ipw_ate,
    estimate_psm_att,
    estimate_twfe_did,
)
from causalops.identification import route_identification
from causalops.estimators.preprocessing import prepare_estimator_input
from causalops.estimators.did_sensitivity import analyze_did_windows
from causalops.estimators.regression import estimate_clustered_regression
from causalops.estimators.preprocessing import PreparedEstimatorInput
from causalops.schemas import (
    AnalysisPlan,
    CausalMethod,
    CausalSpec,
    ClaimLevel,
    GateStatus,
    ResultBundle,
)


class UnsupportedMethodExecutionError(RuntimeError):
    """Raised when a routed method intentionally has no production executor."""


_ESTIMATOR_REGISTRY = {
    "did": estimate_twfe_did,
    "psm": estimate_psm_att,
    "ab_test": estimate_ab_test,
    "cuped": estimate_cuped,
    "ipw": estimate_ipw_ate,
    "aipw": estimate_aipw_ate,
    "double_ml": estimate_double_ml_plr,
    "regression_adjustment": estimate_clustered_regression,
}


def _data_fingerprint(frame: pd.DataFrame) -> str:
    ordered_columns = sorted(frame.columns)
    hashed = pd.util.hash_pandas_object(frame[ordered_columns], index=True).to_numpy()
    digest = hashlib.sha256()
    digest.update("|".join(ordered_columns).encode("utf-8"))
    digest.update(hashed.tobytes())
    return digest.hexdigest()


def execute_analysis(
    frame: pd.DataFrame,
    spec: CausalSpec,
    output_dir: Path,
    *,
    source_sql: str = "-- DataFrame supplied by caller; no SQL executed by CausalOps.",
    data_kind: str = "unspecified",
    execution_scope: str = "approved",
    study_context: dict | None = None,
) -> ResultBundle:
    """Run an identified estimator only after the deterministic gate passes."""

    if data_kind not in {"synthetic", "user_provided", "unspecified"}:
        raise ValueError("Unsupported data provenance category")
    decision = route_identification(spec)
    association_only = execution_scope == "association_only"
    if execution_scope not in {"approved", "association_only"}:
        raise ValueError("未知执行权限范围。")
    if association_only and (decision.selected_method != CausalMethod.REGRESSION_ADJUSTMENT
                             or decision.status == GateStatus.BLOCKED
                             or spec.assignment_mechanism.value != 'observational'):
        raise ValueError("关联分析授权仅适用于未被结构门控阻断的观察性回归调整。")
    if decision.status != GateStatus.PASS and not association_only:
        raise ValueError(
            f"Identification gate did not pass ({decision.status.value}): {decision.required_actions}"
        )
    capability = get_method_capability(decision.selected_method)
    if not capability.executable:
        raise UnsupportedMethodExecutionError(
            capability.unavailable_reason
            or f"{capability.label_zh}尚未开放执行；当前仅支持研究设计。"
        )
    estimator = _ESTIMATOR_REGISTRY.get(str(capability.executor_name))
    if estimator is None:
        raise RuntimeError(
            f"Method capability configuration is incomplete: {decision.selected_method.value}"
        )
    prepared = (PreparedEstimatorInput(frame, spec, {'applied':False,'categorical_effects_handled_by':'AbsorbingLS'})
                if decision.selected_method == CausalMethod.REGRESSION_ADJUSTMENT
                else prepare_estimator_input(frame, spec))
    estimator_output = estimator(prepared.frame, prepared.spec)
    sensitivity = (
        analyze_did_windows(prepared.frame, prepared.spec, estimator_output)
        if decision.selected_method == CausalMethod.DID else None
    )

    failed_diagnostics = [item.name for item in estimator_output.diagnostics if not item.passed]
    failed_claim_blocking_diagnostics = [
        item.name for item in estimator_output.diagnostics if not item.passed and item.claim_blocking
    ]
    claim_level = ClaimLevel.ASSOCIATIONAL if association_only else decision.claim_ceiling
    if decision.selected_method == CausalMethod.REGRESSION_ADJUSTMENT:
        claim_level = ClaimLevel.ASSOCIATIONAL
    if failed_claim_blocking_diagnostics:
        claim_level = ClaimLevel.ASSOCIATIONAL
    plan = AnalysisPlan(
        spec=spec,
        selected_method=decision.selected_method,
        sql=source_sql,
        diagnostics=[item.name for item in estimator_output.diagnostics],
        robustness_checks=["predeclared_shorter_window_sensitivity"] if sensitivity else [],
        claim_ceiling=claim_level if association_only else decision.claim_ceiling,
        requires_human_approval=True,
    )
    run_id = uuid.uuid4().hex
    bundle = ResultBundle(
        run_id=run_id,
        spec=spec,
        plan=plan,
        estimate=estimator_output.estimate,
        diagnostics=estimator_output.diagnostics,
        claim_level=claim_level,
        warnings=estimator_output.warnings,
        evidence={
            "study_context": study_context or {},
            "execution_authorization": {"scope":execution_scope,"unverified_assumptions_retained":association_only},
            "data": {
                "kind": data_kind,
                "row_count": len(frame),
                "column_count": len(frame.columns),
                "columns": sorted(frame.columns),
                "fingerprint_sha256": _data_fingerprint(frame),
            },
            "runtime": {
                "python": platform.python_version(),
                "pandas": pd.__version__,
                "numpy": np.__version__,
            },
            "identification_decision": decision.model_dump(mode="json"),
            "estimator": estimator_output.evidence,
            "window_sensitivity": sensitivity,
            "preprocessing": prepared.evidence,
            "failed_diagnostics": failed_diagnostics,
            "failed_claim_blocking_diagnostics": failed_claim_blocking_diagnostics,
        },
    )
    from causalops.results.interpretation import collect_interpretation_inputs
    bundle.evidence['interpretation_inputs'] = collect_interpretation_inputs(frame, spec, study_context)
    from causalops.results.rate_units import rate_contrast
    units = rate_contrast(bundle)
    if units:
        bundle.evidence['rate_contrast'] = units
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"run-{run_id}.json"
    temporary = output_dir / f".{target.name}.tmp"
    temporary.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(target)
    return bundle
