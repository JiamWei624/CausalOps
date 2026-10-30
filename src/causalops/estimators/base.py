from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from causalops.schemas import DiagnosticResult, EstimateResult


@dataclass(frozen=True)
class EstimatorOutput:
    estimate: EstimateResult
    diagnostics: list[DiagnosticResult]
    evidence: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
