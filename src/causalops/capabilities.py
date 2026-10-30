from __future__ import annotations

from dataclasses import dataclass

from causalops.schemas import CausalMethod


@dataclass(frozen=True)
class MethodCapability:
    """Product and execution contract for one causal-analysis method.

    The UI, execution layer, and tests read this registry instead of keeping
    separate lists of supported methods.  ``executor_name`` is deliberately a
    symbolic key so this module does not import estimators and create circular
    dependencies.
    """

    method: CausalMethod
    label_zh: str
    executor_name: str | None
    relevant_fields: frozenset[str]
    unavailable_reason: str | None = None

    @property
    def executable(self) -> bool:
        return self.executor_name is not None

    def uses(self, field: str) -> bool:
        return field in self.relevant_fields


_BASE_FIELDS = frozenset({"analysis_unit", "treatment", "outcome", "assumptions"})
_OBSERVATIONAL_FIELDS = frozenset(
    {"covariates", "entity_id", "positivity", "assignment"}
)


METHOD_CAPABILITIES: dict[CausalMethod, MethodCapability] = {
    CausalMethod.AB_TEST: MethodCapability(
        CausalMethod.AB_TEST,
        "A/B 实验",
        "ab_test",
        _BASE_FIELDS | {"entity_id", "assignment", "cluster"},
    ),
    CausalMethod.CUPED: MethodCapability(
        CausalMethod.CUPED,
        "CUPED",
        "cuped",
        _BASE_FIELDS
        | {"entity_id", "assignment", "cluster", "covariates", "has_pre_outcome"},
    ),
    CausalMethod.REGRESSION_ADJUSTMENT: MethodCapability(
        CausalMethod.REGRESSION_ADJUSTMENT,
        "回归调整",
        "regression_adjustment",
        _BASE_FIELDS | {"covariates", "entity_id", "cluster", "assignment", "data_structure", "time_column"},
        None,
    ),
    CausalMethod.PSM: MethodCapability(
        CausalMethod.PSM,
        "倾向得分匹配（PSM）",
        "psm",
        _BASE_FIELDS | _OBSERVATIONAL_FIELDS,
    ),
    CausalMethod.IPW: MethodCapability(
        CausalMethod.IPW,
        "逆概率加权（IPW）",
        "ipw",
        _BASE_FIELDS | _OBSERVATIONAL_FIELDS,
    ),
    CausalMethod.AIPW: MethodCapability(CausalMethod.AIPW,"交叉拟合AIPW（IRM-ATE）","aipw",_BASE_FIELDS | _OBSERVATIONAL_FIELDS),
    CausalMethod.DID: MethodCapability(
        CausalMethod.DID,
        "双重差分（DID）",
        "did",
        _BASE_FIELDS
        | {
            "entity_id",
            "covariates",
            "assignment",
            "time_column",
            "treatment_time",
            "data_structure",
            "windows",
            "parallel_trends",
            "cluster",
        },
    ),
    CausalMethod.EVENT_STUDY: MethodCapability(
        CausalMethod.EVENT_STUDY,
        "事件研究",
        None,
        _BASE_FIELDS
        | {
            "entity_id",
            "covariates",
            "assignment",
            "time_column",
            "treatment_time",
            "data_structure",
            "windows",
            "parallel_trends",
            "cluster",
        },
        "事件研究目前支持识别条件检查，但尚未开放独立执行器。",
    ),
    CausalMethod.FIXED_EFFECTS: MethodCapability(
        CausalMethod.FIXED_EFFECTS,
        "固定效应模型",
        None,
        _BASE_FIELDS | {"entity_id", "time_column", "data_structure", "cluster"},
        "固定效应模型目前仅支持研究设计建议，尚未接入经过验证的执行器。",
    ),
    CausalMethod.DOUBLE_ML: MethodCapability(
        CausalMethod.DOUBLE_ML,
        "DoubleML",
        "double_ml",
        _BASE_FIELDS | _OBSERVATIONAL_FIELDS,
    ),
    CausalMethod.DESCRIPTIVE: MethodCapability(
        CausalMethod.DESCRIPTIVE,
        "描述性分析",
        None,
        _BASE_FIELDS,
        "描述性分析执行器在通用工作台独立入口运行，无需因果草案的处理变量；请切换分析任务类型。",
    ),
}


def get_method_capability(method: CausalMethod) -> MethodCapability:
    try:
        return METHOD_CAPABILITIES[method]
    except KeyError as exc:  # pragma: no cover - guarded by the enum and registry test
        raise ValueError(f"No capability is registered for method: {method.value}") from exc


def format_method_label(method: CausalMethod) -> str:
    capability = get_method_capability(method)
    suffix = "" if capability.executable else "（仅设计，暂不可运行）"
    return f"{capability.label_zh}{suffix}"

