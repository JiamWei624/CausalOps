from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd
from .presentation_zh import field_label_zh


_KNOWN_LABELS_ZH = {
    "user_id": "用户ID",
    "post_id": "帖子ID",
    "treated": "是否进入处理组",
    "gender": "性别",
    "verified": "是否认证",
    "baseline_activity": "处理前活跃度",
    "registration_age_days": "注册时长（天）",
    "pre_total_interactions": "处理前总互动量",
    "post_total_interactions": "处理后总互动量",
    "event_date": "事件日期",
    "first_ai_reply_date": "首次 AI 回复日期",
    "ai_reply_received": "是否收到人工智能回复",
    "total_interactions": "总互动量",
    "first_post_got_reply": "首帖是否收到回复",
    "continue_robot": "后续行为指标（业务定义待确认）",
}


@dataclass(frozen=True)
class FieldCatalogEntry:
    name: str
    label_zh: str
    dtype: str
    semantic_type: str
    non_null_count: int
    missing_count: int
    unique_count: int
    measurement_timing: str
    can_be_treatment: bool
    can_be_outcome: bool
    can_be_covariate: bool
    can_be_entity_id: bool
    can_be_time: bool
    requires_encoding: bool
    availability_reason: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _looks_like_id(
    name: str, series: pd.Series, unique_count: int, non_null_count: int
) -> bool:
    normalized = name.lower()
    explicit = normalized == "id" or normalized.endswith("_id") or normalized.startswith("id_")
    text_like = pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)
    near_unique_text = (
        text_like and non_null_count > 0 and unique_count / non_null_count >= 0.95
    )
    return explicit or near_unique_text


def _looks_like_time(name: str, series: pd.Series) -> bool:
    normalized = name.lower()
    tokens = ("date", "time", "month", "year", "日期", "时间", "月份", "年份")
    return pd.api.types.is_datetime64_any_dtype(series) or any(token in normalized for token in tokens)


def _semantic_type(series: pd.Series, *, is_id: bool, is_time: bool) -> str:
    if is_time:
        return "时间"
    if is_id:
        return "标识符"
    if pd.api.types.is_bool_dtype(series):
        return "布尔"
    if pd.api.types.is_numeric_dtype(series):
        return "数值"
    if isinstance(series.dtype, pd.CategoricalDtype) or pd.api.types.is_object_dtype(series):
        return "分类"
    return "其他"


def build_field_catalog(frame: pd.DataFrame) -> dict[str, FieldCatalogEntry]:
    """Build one deterministic field catalog for UI, validation, and later AI context.

    The catalog describes technical eligibility only.  It deliberately leaves
    treatment timing as unknown because column names cannot establish causal order.
    """

    entries: dict[str, FieldCatalogEntry] = {}
    row_count = len(frame)
    for raw_name in frame.columns:
        name = str(raw_name)
        series = frame[raw_name]
        non_null_count = int(series.notna().sum())
        missing_count = row_count - non_null_count
        unique_count = int(series.nunique(dropna=True))
        is_time = _looks_like_time(name, series)
        is_id = _looks_like_id(name, series, unique_count, non_null_count) and not is_time
        semantic_type = _semantic_type(series, is_id=is_id, is_time=is_time)
        is_binary = unique_count == 2
        low_cardinality = 2 <= unique_count <= min(100, max(20, int(max(row_count, 1) * 0.20)))
        categorical = semantic_type in {"分类", "布尔"}
        numeric = semantic_type == "数值"
        can_be_covariate = (numeric or categorical) and not is_id and not is_time
        categorical_time_effect = is_time and name.endswith('_cat') and low_cardinality
        if categorical_time_effect:
            can_be_covariate = True
        if is_id:
            reason = "标识符默认不作为协变量；可作为分析单位或聚类字段。"
        elif categorical_time_effect:
            reason = "可作为明确声明的低基数时间固定效应；不代表其为处理前混杂变量。"
        elif is_time:
            reason = "时间字段用于时间结构，不自动作为处理前协变量。"
        elif semantic_type == "分类" and not low_cardinality:
            can_be_covariate = False
            reason = "分类水平过多，需先定义合并或编码规则。"
        elif can_be_covariate:
            reason = "技术上可选；仍需人工确认其在处理前测量且不构成信息泄漏。"
        else:
            reason = "当前数据类型尚未纳入受控统计预处理。"

        entries[name] = FieldCatalogEntry(
            name=name,
            label_zh=_KNOWN_LABELS_ZH.get(name, field_label_zh(name)),
            dtype=str(series.dtype),
            semantic_type=semantic_type,
            non_null_count=non_null_count,
            missing_count=missing_count,
            unique_count=unique_count,
            measurement_timing="未知（需人工确认）",
            can_be_treatment=is_binary and (numeric or semantic_type == "布尔") and not is_id and not is_time,
            can_be_outcome=numeric and not is_id and not is_time,
            can_be_covariate=can_be_covariate,
            can_be_entity_id=is_id or unique_count > 1,
            can_be_time=is_time,
            requires_encoding=semantic_type == "分类",
            availability_reason=reason,
        )
    return entries


def sanitize_defaults(
    proposed: Iterable[str], available: Iterable[str]
) -> tuple[list[str], list[str]]:
    """Return valid defaults and explicitly report excluded/stale values."""

    available_set = set(available)
    valid: list[str] = []
    invalid: list[str] = []
    for raw in proposed:
        value = str(raw)
        target = valid if value in available_set else invalid
        if value not in target:
            target.append(value)
    return valid, invalid

