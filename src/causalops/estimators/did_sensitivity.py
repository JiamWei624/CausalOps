"""Predeclared, shorter-window diagnostics; never select the most significant result."""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

from causalops.audits import AuditStatus, audit_did_panel
from causalops.schemas import CausalSpec

from .base import EstimatorOutput
from .did import estimate_twfe_did


def analyze_did_windows(
    frame: pd.DataFrame, spec: CausalSpec, primary: EstimatorOutput
) -> dict[str, Any]:
    """Compare a fixed grid inside the approved window and preserve the primary spec.

    These are secondary, exploratory estimates rather than replacement approvals.
    All variants, including failures, are recorded; the primary claim is not upgraded.
    """
    pre, post = int(spec.pre_period_days or 0), int(spec.post_period_days or 0)
    digest = hashlib.sha256(spec.model_dump_json().encode("utf-8")).hexdigest()
    result: dict[str, Any] = {
        "version": "did_window_sensitivity_v1", "primary_spec_sha256": digest,
        "selection_rule": "fixed_shorter_windows_no_significance_selection",
        "changes_approved_spec": False, "adjusts_for_multiple_testing": False,
        "rows": [],
        "limitations": [
            "本表是预设缩短窗口的探索性比较，不依据显著性筛选结果，不改变主分析。",
            "置信区间为逐项区间，未作多重比较校正；同号不能单独证明稳健或因果。",
            "窗口改变也可能改变样本构成和目标时间尺度，需同时核对样本量。",
        ],
    }
    if primary.evidence.get("distinct_treatment_dates") != 1:
        result.update(status="not_applicable", reason="当前存在交错处理时点，需先采用合适的交错处理估计器。")
        return result
    candidates = [(pre, post)]
    shorter_pre, shorter_post = max(2, pre - 2), max(1, post - 2)
    for window in [(shorter_pre, post), (pre, shorter_post), (shorter_pre, shorter_post)]:
        if window[0] <= pre and window[1] <= post and window not in candidates:
            candidates.append(window)
    for variant_pre, variant_post in candidates:
        variant = CausalSpec.model_validate({
            **spec.model_dump(mode="json"),
            "pre_period_days": variant_pre, "post_period_days": variant_post,
        })
        row: dict[str, Any] = {
            "pre_days": variant_pre, "post_days": variant_post,
            "is_primary": (variant_pre, variant_post) == (pre, post),
            "variant_spec_sha256": hashlib.sha256(variant.model_dump_json().encode("utf-8")).hexdigest(),
            "variant_spec": variant.model_dump(mode="json"),
        }
        audit = audit_did_panel(frame, variant)
        row.update(complete_pre_users=audit.complete_pre_window_users,
                   complete_post_users=audit.complete_post_window_users)
        if audit.overall_status == AuditStatus.BLOCK:
            row.update(status="not_estimable", reason="；".join(
                check.summary for check in audit.checks if check.status == AuditStatus.BLOCK))
            result["rows"].append(row)
            continue
        try:
            output = primary if row["is_primary"] else estimate_twfe_did(frame, variant)
            estimate = output.estimate
            pretrend = next(d for d in output.diagnostics if d.name == "parallel_trends_joint_test")
            row.update(
                status="estimated", estimate=estimate.estimate, standard_error=estimate.standard_error,
                ci_lower=estimate.confidence_interval[0] if estimate.confidence_interval else None,
                ci_upper=estimate.confidence_interval[1] if estimate.confidence_interval else None,
                p_value=estimate.p_value, sample_size=estimate.sample_size,
                pretrend_p_value=pretrend.value, pretrend_passed=pretrend.passed,
                treated_users=output.evidence["treated_entity_count"],
                control_users=output.evidence["control_entity_count"],
            )
        except (ValueError, np.linalg.LinAlgError) as exc:
            row.update(status="not_estimable", reason=f"该窗口无法估计：{type(exc).__name__}: {exc}")
        result["rows"].append(row)
    result["status"] = "completed"
    return result
