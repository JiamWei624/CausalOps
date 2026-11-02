"""Numerical claims supported by an unadjusted binary A/B comparison."""
from math import isclose, isfinite


def rate_contrast(bundle):
    inputs = bundle.evidence.get("interpretation_inputs", {})
    definition = inputs.get("metric_definition") or {}
    if (bundle.plan.selected_method.value != "ab_test" or not bundle.estimate
            or not inputs.get("outcome_binary_observed")
            or definition.get("kind") in {"continuous", "count"}
            or inputs.get("baseline_scope") != "same_complete_case_raw_groups"):
        return None
    rows = inputs.get("raw_group_summary") or []
    if len(rows) != 2 or sum(row["n"] for row in rows) != bundle.estimate.sample_size:
        return None
    groups = {row["treatment"]: row["outcome_mean"] for row in rows}
    if any(not isfinite(rate) or not 0 <= rate <= 1 for rate in groups.values()):
        return None
    delta = bundle.estimate.estimate
    if set(groups) != {0, 1} or not isclose(groups[1] - groups[0], delta, abs_tol=1e-10):
        return None
    interval = bundle.estimate.confidence_interval
    return {
        "estimand": "risk_difference", "outcome": bundle.spec.outcome, "raw_unit": "probability",
        "raw": delta, "control_rate": groups[0], "treated_rate": groups[1],
        "pp": 100 * delta, "ci_pp": [100*x for x in interval] if interval else None,
        "relative_pct": 100 * delta / groups[0] if groups[0] > 0 else None,
        "formulas": {"pp": "100 * raw", "ci_pp": "100 * each raw interval bound",
                     "relative_pct": "100 * raw / control_rate (positive control_rate only)"},
    }


RATE_LABELS = {"raw": "概率差", "pp": "绝对差（百分点）", "ci_pp": "绝对差置信区间（百分点）",
               "control_rate": "对照组事件概率", "treated_rate": "处理组事件概率",
               "relative_pct": "相对对照组变化（%）"}
