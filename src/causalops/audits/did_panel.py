from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from causalops.schemas import CausalSpec


class AuditStatus(str, Enum):
    PASS = "pass"
    REVIEW = "needs_review"
    BLOCK = "blocked"


@dataclass(frozen=True)
class AuditCheck:
    code: str
    label: str
    status: AuditStatus
    summary: str
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value


@dataclass(frozen=True)
class DidPanelAuditReport:
    audit_type: str
    overall_status: AuditStatus
    generated_at: str
    row_count: int
    user_count: int
    treated_user_count: int
    never_treated_user_count: int
    not_yet_treated_row_count: int
    treatment_date_count: int
    staggered_adoption: bool
    duplicate_user_time_rows: int
    complete_pre_window_users: int
    complete_post_window_users: int
    pre_outcome_complete_users: int
    relative_day_coverage: list[dict[str, Any]]
    checks: list[AuditCheck]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_type": self.audit_type,
            "overall_status": self.overall_status.value,
            "generated_at": self.generated_at,
            "row_count": self.row_count,
            "user_count": self.user_count,
            "treated_user_count": self.treated_user_count,
            "never_treated_user_count": self.never_treated_user_count,
            "not_yet_treated_row_count": self.not_yet_treated_row_count,
            "treatment_date_count": self.treatment_date_count,
            "staggered_adoption": self.staggered_adoption,
            "duplicate_user_time_rows": self.duplicate_user_time_rows,
            "complete_pre_window_users": self.complete_pre_window_users,
            "complete_post_window_users": self.complete_post_window_users,
            "pre_outcome_complete_users": self.pre_outcome_complete_users,
            "relative_day_coverage": self.relative_day_coverage,
            "checks": [item.to_dict() for item in self.checks],
            "limitations": self.limitations,
        }


def _overall_status(checks: list[AuditCheck]) -> AuditStatus:
    if any(item.status == AuditStatus.BLOCK for item in checks):
        return AuditStatus.BLOCK
    if any(item.status == AuditStatus.REVIEW for item in checks):
        return AuditStatus.REVIEW
    return AuditStatus.PASS


def _empty_report(frame: pd.DataFrame, checks: list[AuditCheck]) -> DidPanelAuditReport:
    return DidPanelAuditReport(
        audit_type="did_panel_pretrend_v1",
        overall_status=_overall_status(checks),
        generated_at=datetime.now(timezone.utc).isoformat(),
        row_count=len(frame),
        user_count=0,
        treated_user_count=0,
        never_treated_user_count=0,
        not_yet_treated_row_count=0,
        treatment_date_count=0,
        staggered_adoption=False,
        duplicate_user_time_rows=0,
        complete_pre_window_users=0,
        complete_post_window_users=0,
        pre_outcome_complete_users=0,
        relative_day_coverage=[],
        checks=checks,
        limitations=[
            "本报告只核验数据结构与可诊断性，不估计处理效应。",
            "本报告不能自动验证平行趋势、无预期效应、无干扰或可忽略性。",
        ],
    )


def audit_did_panel(frame: pd.DataFrame, spec: CausalSpec) -> DidPanelAuditReport:
    """Audit DID/event-study readiness without estimating any causal effect.

    The input frame and spec are never mutated. Human-governed identification fields
    are reported as limitations and are never changed by this function.
    """

    data = frame.copy(deep=True)
    checks: list[AuditCheck] = []
    entity = spec.entity_id_column
    time_col = spec.time_column
    treatment_time = spec.treatment_time_column
    required = [entity, time_col, treatment_time, spec.treatment, spec.outcome]
    missing = [name for name in required if not name or name not in data.columns]
    if missing:
        checks.append(
            AuditCheck(
                code="required_columns",
                label="必要字段",
                status=AuditStatus.BLOCK,
                summary="缺少DID/事件研究所需字段，不能继续数据审计。",
                evidence={"missing_columns": missing},
            )
        )
        return _empty_report(data, checks)

    assert entity is not None and time_col is not None and treatment_time is not None
    data[time_col] = pd.to_datetime(data[time_col], errors="coerce")
    data[treatment_time] = pd.to_datetime(data[treatment_time], errors="coerce")
    user_count = int(data[entity].nunique(dropna=True))
    invalid_entity = int(data[entity].isna().sum())
    invalid_time = int(data[time_col].isna().sum())
    invalid_outcome = int(data[spec.outcome].isna().sum())
    checks.append(
        AuditCheck(
            code="required_values",
            label="必要字段有效值",
            status=AuditStatus.BLOCK if invalid_entity or invalid_time else (
                AuditStatus.REVIEW if invalid_outcome else AuditStatus.PASS
            ),
            summary="核对实体、日期和结果变量的缺失或日期解析失败。",
            evidence={
                "missing_entity_rows": invalid_entity,
                "invalid_time_rows": invalid_time,
                "missing_outcome_rows": invalid_outcome,
            },
        )
    )

    duplicate_rows = int(data.duplicated([entity, time_col], keep=False).sum())
    checks.append(
        AuditCheck(
            code="user_time_uniqueness",
            label="用户—日期唯一性",
            status=AuditStatus.BLOCK if duplicate_rows else AuditStatus.PASS,
            summary=(
                "发现重复的用户—日期记录，必须先确定聚合或去重规则。"
                if duplicate_rows
                else "每个用户—日期组合唯一。"
            ),
            evidence={"duplicate_rows": duplicate_rows},
        )
    )

    treatment_dates_per_user = data.groupby(entity, dropna=False)[treatment_time].nunique(dropna=True)
    inconsistent_users = int((treatment_dates_per_user > 1).sum())
    checks.append(
        AuditCheck(
            code="treatment_time_consistency",
            label="首次处理日期一致性",
            status=AuditStatus.BLOCK if inconsistent_users else AuditStatus.PASS,
            summary=(
                "同一用户出现多个首次处理日期，必须先修正处理时点口径。"
                if inconsistent_users
                else "同一用户至多对应一个首次处理日期。"
            ),
            evidence={"users_with_multiple_treatment_dates": inconsistent_users},
        )
    )

    per_user_treatment = data.groupby(entity, dropna=False)[treatment_time].first()
    treated_users = per_user_treatment[per_user_treatment.notna()].index
    never_treated_users = per_user_treatment[per_user_treatment.isna()].index
    treated_count = int(len(treated_users))
    never_count = int(len(never_treated_users))
    treatment_date_count = int(per_user_treatment.dropna().nunique())
    staggered = treatment_date_count > 1
    checks.append(
        AuditCheck(
            code="comparison_groups",
            label="处理与对照结构",
            status=AuditStatus.BLOCK if treated_count == 0 or never_count == 0 else AuditStatus.REVIEW,
            summary=(
                "缺少处理用户或从未处理用户，当前对照结构不足。"
                if treated_count == 0 or never_count == 0
                else "同时存在处理用户与从未处理用户；仍需人工确认对照组是从未处理还是尚未处理。"
            ),
            evidence={
                "treated_users": treated_count,
                "never_treated_users": never_count,
                "distinct_treatment_dates": treatment_date_count,
                "staggered_adoption": staggered,
            },
        )
    )

    mapped_treatment_time = data[entity].map(per_user_treatment)
    data["__relative_day"] = (data[time_col] - mapped_treatment_time).dt.days
    not_yet_treated_rows = int((data["__relative_day"] < 0).sum())
    pre_days = list(range(-int(spec.pre_period_days or 0), 0))
    post_days = list(range(0, int(spec.post_period_days or 0)))
    expected_days = pre_days + post_days
    treated_rows = data[data[entity].isin(treated_users)].copy()

    coverage: list[dict[str, Any]] = []
    for day in expected_days:
        day_rows = treated_rows[treated_rows["__relative_day"] == day]
        observed_users = int(day_rows[entity].nunique(dropna=True))
        outcome_users = int(day_rows.loc[day_rows[spec.outcome].notna(), entity].nunique(dropna=True))
        coverage.append(
            {
                "relative_day": int(day),
                "expected_treated_users": treated_count,
                "observed_users": observed_users,
                "outcome_nonmissing_users": outcome_users,
                "row_coverage_rate": round(observed_users / treated_count, 6) if treated_count else 0.0,
                "outcome_coverage_rate": round(outcome_users / treated_count, 6) if treated_count else 0.0,
            }
        )

    def _complete_users(days: list[int], require_outcome: bool) -> int:
        if not days or treated_count == 0:
            return 0
        subset = treated_rows
        if require_outcome:
            subset = subset[subset[spec.outcome].notna()]
        observed = subset.groupby(entity)["__relative_day"].agg(lambda values: set(values.dropna().astype(int)))
        expected = set(days)
        return int(sum(expected.issubset(values) for values in observed))

    complete_pre = _complete_users(pre_days, require_outcome=False)
    complete_post = _complete_users(post_days, require_outcome=False)
    pre_outcome_complete = _complete_users(pre_days, require_outcome=True)
    pre_rate = pre_outcome_complete / treated_count if treated_count else 0.0
    checks.append(
        AuditCheck(
            code="relative_window_coverage",
            label="相对处理日窗口覆盖",
            status=(
                AuditStatus.BLOCK
                if treated_count and pre_outcome_complete == 0
                else AuditStatus.REVIEW
                if treated_count and (complete_pre < treated_count or complete_post < treated_count)
                else AuditStatus.PASS
            ),
            summary=(
                "没有用户具备完整处理前结果窗口，不能进行处理前轨迹诊断。"
                if treated_count and pre_outcome_complete == 0
                else "部分用户的处理前/后窗口不完整，需要明确缺失与样本纳入规则。"
                if treated_count and (complete_pre < treated_count or complete_post < treated_count)
                else "处理用户的当前相对时间窗口完整。"
            ),
            evidence={
                "pre_days": pre_days,
                "post_days": post_days,
                "complete_pre_window_users": complete_pre,
                "complete_post_window_users": complete_post,
                "pre_outcome_complete_users": pre_outcome_complete,
                "pre_outcome_complete_rate": round(pre_rate, 6),
            },
        )
    )

    checks.append(
        AuditCheck(
            code="pre_treatment_outcome",
            label="处理前结果可用性",
            status=AuditStatus.PASS if pre_outcome_complete == treated_count and treated_count else AuditStatus.REVIEW,
            summary=(
                "total_interactions在全部处理用户的处理前窗口内可用，可用于处理前轨迹诊断。"
                if pre_outcome_complete == treated_count and treated_count
                else "处理前结果覆盖不完整；不能把平行趋势当作已验证。"
            ),
            evidence={
                "outcome": spec.outcome,
                "complete_users": pre_outcome_complete,
                "treated_users": treated_count,
            },
        )
    )

    baseline_evidence: dict[str, Any] = {"covariates": list(spec.covariates)}
    varying_covariates: list[str] = []
    absent_covariates: list[str] = []
    for covariate in spec.covariates:
        if covariate not in data.columns:
            absent_covariates.append(covariate)
            continue
        if int((data.groupby(entity)[covariate].nunique(dropna=True) > 1).sum()) > 0:
            varying_covariates.append(covariate)
    baseline_evidence.update(
        {
            "missing_covariates": absent_covariates,
            "covariates_varying_within_user": varying_covariates,
        }
    )
    checks.append(
        AuditCheck(
            code="covariate_timing",
            label="协变量测量时点",
            status=AuditStatus.BLOCK if absent_covariates else AuditStatus.REVIEW,
            summary=(
                "协变量字段缺失。"
                if absent_covariates
                else "数据值不能证明协变量严格在处理前测量；必须人工核对口径。"
            ),
            evidence=baseline_evidence,
        )
    )

    overlap_evidence: dict[str, Any] = {}
    overlap_status = AuditStatus.REVIEW
    for covariate in spec.covariates:
        if covariate not in data.columns or not pd.api.types.is_numeric_dtype(data[covariate]):
            continue
        per_user_value = data.groupby(entity)[covariate].first()
        treated_values = per_user_value.reindex(treated_users).dropna().astype(float)
        control_values = per_user_value.reindex(never_treated_users).dropna().astype(float)
        if treated_values.empty or control_values.empty:
            continue
        lower = max(float(treated_values.min()), float(control_values.min()))
        upper = min(float(treated_values.max()), float(control_values.max()))
        overlap_evidence[covariate] = {
            "treated_range": [float(treated_values.min()), float(treated_values.max())],
            "control_range": [float(control_values.min()), float(control_values.max())],
            "range_overlap": bool(lower <= upper),
        }
        if lower > upper:
            overlap_status = AuditStatus.BLOCK
    checks.append(
        AuditCheck(
            code="descriptive_overlap",
            label="协变量描述性重叠",
            status=overlap_status,
            summary=(
                "至少一个数值协变量的处理组与对照组范围不重叠。"
                if overlap_status == AuditStatus.BLOCK
                else "仅完成描述性范围检查；positivity仍需更完整诊断与人工判断。"
            ),
            evidence=overlap_evidence,
        )
    )

    checks.extend(
        [
            AuditCheck(
                code="outcome_definition",
                label="结果变量是否机械包含处理",
                status=AuditStatus.REVIEW,
                summary="仅凭列值无法判断total_interactions是否包含AI回复本身，必须核对指标口径。",
                evidence={"treatment": spec.treatment, "outcome": spec.outcome},
            ),
            AuditCheck(
                code="interference",
                label="用户间干扰",
                status=AuditStatus.REVIEW,
                summary="UGC中的互动与曝光可能产生跨用户干扰，数据结构检查不能验证SUTVA。",
                evidence={"automatic_verification": False},
            ),
            AuditCheck(
                code="cluster_structure",
                label="聚类与共同冲击",
                status=AuditStatus.REVIEW,
                summary="按user_id聚类符合重复观测结构；仍需评估日期共同冲击及聚类数量。",
                evidence={
                    "declared_cluster": spec.cluster_column,
                    "user_clusters": user_count,
                    "calendar_dates": int(data[time_col].nunique(dropna=True)),
                },
            ),
        ]
    )

    return DidPanelAuditReport(
        audit_type="did_panel_pretrend_v1",
        overall_status=_overall_status(checks),
        generated_at=datetime.now(timezone.utc).isoformat(),
        row_count=len(data),
        user_count=user_count,
        treated_user_count=treated_count,
        never_treated_user_count=never_count,
        not_yet_treated_row_count=not_yet_treated_rows,
        treatment_date_count=treatment_date_count,
        staggered_adoption=staggered,
        duplicate_user_time_rows=duplicate_rows,
        complete_pre_window_users=complete_pre,
        complete_post_window_users=complete_post,
        pre_outcome_complete_users=pre_outcome_complete,
        relative_day_coverage=coverage,
        checks=checks,
        limitations=[
            "本报告只核验数据结构、窗口覆盖和可诊断性，不估计处理效应。",
            "pass仅表示相应结构检查未发现阻断项，不等于识别假设得到验证。",
            "平行趋势、无预期效应、无干扰、positivity及协变量测量时点仍需人工判断。",
        ],
    )
