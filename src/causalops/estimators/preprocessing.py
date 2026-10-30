from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from causalops.schemas import CausalSpec


@dataclass(frozen=True)
class PreparedEstimatorInput:
    frame: pd.DataFrame
    spec: CausalSpec
    evidence: dict[str, Any]


def prepare_estimator_input(
    frame: pd.DataFrame,
    spec: CausalSpec,
    *,
    maximum_categories: int = 100,
) -> PreparedEstimatorInput:
    """Deterministically encode declared covariates for validated estimators.

    Numeric covariates keep their names. Boolean covariates become 0/1. Low-cardinality
    string/category covariates use reference-cell one-hot encoding. Missing values stay
    missing so each estimator's existing complete-case policy remains unchanged.
    """

    if not spec.covariates:
        return PreparedEstimatorInput(
            frame=frame,
            spec=spec,
            evidence={"applied": False, "covariate_mapping": {}},
        )

    prepared = frame.copy()
    encoded_covariates: list[str] = []
    mapping: dict[str, list[str]] = {}
    for name in spec.covariates:
        if name not in prepared.columns:
            raise ValueError(f"协变量不存在：{name}")
        series = prepared[name]
        if pd.api.types.is_bool_dtype(series):
            prepared[name] = series.astype("Int8").astype(float)
            encoded_covariates.append(name)
            mapping[name] = [name]
            continue
        if pd.api.types.is_numeric_dtype(series):
            encoded_covariates.append(name)
            mapping[name] = [name]
            continue
        if pd.api.types.is_datetime64_any_dtype(series):
            raise ValueError(f"时间字段不能自动作为协变量：{name}")
        if not (
            pd.api.types.is_object_dtype(series)
            or isinstance(series.dtype, pd.CategoricalDtype)
            or pd.api.types.is_string_dtype(series)
        ):
            raise ValueError(f"协变量类型尚未纳入受控预处理：{name} ({series.dtype})")

        levels = int(series.nunique(dropna=True))
        if levels < 2:
            raise ValueError(f"分类协变量至少需要两个有效水平：{name}")
        if levels > maximum_categories:
            raise ValueError(
                f"分类协变量 {name} 包含 {levels} 个水平，超过上限 {maximum_categories}；"
                "请先制定合并或降维规则。"
            )
        encoded = pd.get_dummies(
            series.astype("string"),
            prefix=name,
            prefix_sep="__",
            drop_first=True,
            dtype=float,
        )
        encoded.loc[series.isna(), :] = float("nan")
        collisions = sorted(set(encoded.columns).intersection(prepared.columns))
        if collisions:
            raise ValueError(f"分类编码字段与原数据重名：{collisions}")
        prepared = pd.concat([prepared, encoded], axis=1)
        names = [str(column) for column in encoded.columns]
        encoded_covariates.extend(names)
        mapping[name] = names

    prepared_spec = spec.model_copy(update={"covariates": encoded_covariates})
    return PreparedEstimatorInput(
        frame=prepared,
        spec=prepared_spec,
        evidence={
            "applied": prepared_spec.covariates != spec.covariates,
            "original_covariates": list(spec.covariates),
            "encoded_covariates": list(prepared_spec.covariates),
            "covariate_mapping": mapping,
            "missing_values_preserved_for_complete_case_filter": True,
            "categorical_reference_cell_encoding": True,
        },
    )

