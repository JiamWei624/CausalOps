from pathlib import Path

import numpy as np
import pandas as pd

from causalops.agent import CausalOpsAgent
from causalops.estimators import (
    estimate_ab_test,
    estimate_cuped,
    estimate_double_ml_plr,
    estimate_ipw_ate,
)
from causalops.schemas import (
    AssignmentMechanism,
    CausalMethod,
    CausalSpec,
    DomainName,
)


def _randomized_data(seed: int = 41, rows: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pre = rng.normal(size=rows)
    treatment = rng.binomial(1, 0.5, rows)
    outcome = 1.2 * treatment + 0.9 * pre + rng.normal(0, 0.8, rows)
    return pd.DataFrame(
        {
            "user_id": [f"u{index:05d}" for index in range(rows)],
            "assignment": treatment,
            "retention_7d": outcome,
            "pre_metric": pre,
        }
    )


def _experiment_spec(method: CausalMethod) -> CausalSpec:
    return CausalSpec(
        question="Does randomized assignment change seven-day retention?",
        domain=DomainName.EXPERIMENT,
        analysis_unit="user",
        treatment="assignment",
        outcome="retention_7d",
        entity_id_column="user_id",
        covariates=["pre_metric"],
        candidate_methods=[method],
        assignment_mechanism=AssignmentMechanism.RANDOMIZED,
        has_pre_treatment_outcome=True,
    )


def _observational_data(seed: int = 43, rows: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=rows)
    x2 = rng.normal(size=rows)
    propensity = 1 / (1 + np.exp(-0.7 * x1 + 0.35 * x2))
    treatment = rng.binomial(1, propensity)
    outcome = 1.7 * treatment + 0.8 * x1 - 0.35 * x2 + rng.normal(0, 0.7, rows)
    return pd.DataFrame({"treatment": treatment, "outcome": outcome, "x1": x1, "x2": x2})


def _observational_spec(method: CausalMethod) -> CausalSpec:
    return CausalSpec(
        question="Does observational treatment change the measured outcome?",
        domain=DomainName.GENERIC,
        analysis_unit="user",
        treatment="treatment",
        outcome="outcome",
        covariates=["x1", "x2"],
        candidate_methods=[method],
        assignment_mechanism=AssignmentMechanism.OBSERVATIONAL,
        positivity_plausible=True,
        identification_assumptions=["conditional exchangeability given x1 and x2"],
    )


def test_ab_and_cuped_recover_effect_and_cuped_reduces_variance() -> None:
    frame = _randomized_data()
    ab = estimate_ab_test(frame, _experiment_spec(CausalMethod.AB_TEST))
    cuped = estimate_cuped(frame, _experiment_spec(CausalMethod.CUPED))
    assert 1.0 < ab.estimate.estimate < 1.4
    assert 1.0 < cuped.estimate.estimate < 1.4
    assert cuped.evidence["variance_reduction"] > 0.35
    assert cuped.estimate.standard_error < ab.estimate.standard_error


def test_ipw_and_doubleml_recover_known_observational_effect() -> None:
    frame = _observational_data()
    ipw = estimate_ipw_ate(frame, _observational_spec(CausalMethod.IPW), bootstrap_samples=100)
    dml = estimate_double_ml_plr(frame, _observational_spec(CausalMethod.DOUBLE_ML), n_folds=3)
    assert 1.3 < ipw.estimate.estimate < 2.1
    assert 1.3 < dml.estimate.estimate < 2.1
    assert ipw.evidence["bootstrap_samples_used"] >= 50
    assert dml.evidence["n_folds"] == 3


def test_agent_uses_allowlisted_tools_and_writes_report_and_trace(tmp_path: Path) -> None:
    frame = _randomized_data(rows=600)
    result = CausalOpsAgent().run(frame, _experiment_spec(CausalMethod.CUPED), tmp_path)
    assert result.report_path.is_file()
    assert result.trace_path.is_file()
    assert "CausalOps 自动分析报告" in result.report_path.read_text(encoding="utf-8")
    trace = result.trace_path.read_text(encoding="utf-8")
    assert "deterministic_allowlisted_tool_agent" in trace
    assert "execute_analysis" in trace
