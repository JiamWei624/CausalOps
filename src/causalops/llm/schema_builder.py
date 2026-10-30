from __future__ import annotations

from copy import deepcopy
from typing import Any

from causalops.schemas import CausalSpec


_COLUMN_FIELDS = (
    "treatment",
    "outcome",
    "time_column",
    "entity_id_column",
    "treatment_time_column",
    "cluster_column",
)


def _nullable_enum(values: list[str]) -> dict[str, Any]:
    return {"anyOf": [{"type": "string", "enum": values}, {"type": "null"}]}


def build_dynamic_causal_spec_schema(
    columns: list[str],
    *,
    allowed_source_tables: list[str] | None = None,
) -> dict[str, Any]:
    """Constrain model output to real columns while reserving evidence for humans.

    Fields that assert design validity are deliberately pinned to unverified values.
    They are filled only in the manual review UI or by deterministic diagnostics.
    """

    unique_columns = sorted(dict.fromkeys(columns))
    if not unique_columns:
        raise ValueError("At least one dataset column is required")
    if len(unique_columns) > 500:
        raise ValueError("AI proposal is limited to 500 columns; reduce the schema first")
    tables = sorted(dict.fromkeys(allowed_source_tables or []))
    schema = deepcopy(CausalSpec.model_json_schema())
    properties = schema["properties"]

    for field in _COLUMN_FIELDS:
        if field in {"treatment", "outcome"}:
            properties[field] = {"type": "string", "enum": unique_columns}
        else:
            properties[field] = _nullable_enum(unique_columns)
    properties["covariates"] = {
        "type": "array",
        "items": {"type": "string", "enum": unique_columns},
        "uniqueItems": True,
        "maxItems": min(100, len(unique_columns)),
        "default": [],
    }
    properties["source_tables"] = {
        "type": "array",
        "items": {"type": "string", "enum": tables} if tables else {"type": "string", "enum": []},
        "uniqueItems": True,
        "maxItems": len(tables),
        "default": [],
    }
    properties["candidate_methods"]["maxItems"] = 3
    properties["candidate_methods"]["uniqueItems"] = True

    # Epistemic claims are not delegated to the language model.
    properties["assignment_mechanism"] = {"type": "string", "const": "unknown", "default": "unknown"}
    properties["identification_assumptions"] = {"type": "array", "items": {"type": "string"}, "maxItems": 0, "default": []}
    properties["has_pre_treatment_outcome"] = {"type": "boolean", "const": False, "default": False}
    for field in ("positivity_plausible", "no_interference_plausible", "parallel_trends_plausible"):
        properties[field] = {"type": "null", "default": None}
    schema["additionalProperties"] = False
    return schema
