from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from causalops.agent import CausalOpsAgent
from causalops.schemas import AssignmentMechanism, CausalMethod, CausalSpec, DomainName


def _randomized_benchmark(seed: int, rows: int, effect: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pre_metric = rng.normal(size=rows)
    assignment = rng.binomial(1, 0.5, rows)
    outcome = effect * assignment + 0.9 * pre_metric + rng.normal(0, 0.8, rows)
    return pd.DataFrame(
        {
            "user_id": [f"r{index:06d}" for index in range(rows)],
            "assignment": assignment,
            "retention_7d": outcome,
            "pre_metric": pre_metric,
        }
    )


def _observational_benchmark(seed: int, rows: int, effect: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=rows)
    x2 = rng.normal(size=rows)
    propensity = 1 / (1 + np.exp(-0.7 * x1 + 0.35 * x2))
    treatment = rng.binomial(1, propensity)
    outcome = effect * treatment + 0.8 * x1 - 0.35 * x2 + rng.normal(0, 0.7, rows)
    return pd.DataFrame({"treatment": treatment, "outcome": outcome, "x1": x1, "x2": x2})


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


def run_gold_standard_benchmarks(
    output_dir: Path,
    *,
    seed: int = 20261027,
    rows: int = 900,
) -> Path:
    """Execute four estimators on reproducible data with known treatment effects."""

    output_dir = output_dir.resolve()
    randomized_effect = 1.2
    observational_effect = 1.7
    randomized = _randomized_benchmark(seed, rows, randomized_effect)
    observational = _observational_benchmark(seed + 1, rows, observational_effect)
    jobs = [
        ("ab_test", randomized, _experiment_spec(CausalMethod.AB_TEST), randomized_effect),
        ("cuped", randomized, _experiment_spec(CausalMethod.CUPED), randomized_effect),
        ("ipw", observational, _observational_spec(CausalMethod.IPW), observational_effect),
        ("double_ml", observational, _observational_spec(CausalMethod.DOUBLE_ML), observational_effect),
    ]
    summaries: list[dict[str, object]] = []
    for name, frame, spec, truth in jobs:
        result = CausalOpsAgent().run(frame, spec, output_dir / name)
        estimate = result.bundle.estimate
        if estimate is None:
            raise RuntimeError(f"Benchmark did not produce an estimate: {name}")
        summaries.append(
            {
                "method": name,
                "true_effect": truth,
                "estimate": estimate.estimate,
                "absolute_error": abs(estimate.estimate - truth),
                "standard_error": estimate.standard_error,
                "p_value": estimate.p_value,
                "claim_level": result.bundle.claim_level.value,
                "run_id": result.bundle.run_id,
                "report_path": str(result.report_path),
                "trace_path": str(result.trace_path),
            }
        )
    target = output_dir / "benchmark-summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
