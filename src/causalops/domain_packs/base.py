from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from causalops.schemas import CausalSpec, DomainName


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    description: str
    aggregation: str
    grain: str


class DomainPack(ABC):
    name: DomainName
    metrics: dict[str, MetricDefinition]

    @abstractmethod
    def validate_spec(self, spec: CausalSpec) -> list[str]:
        """Return actionable validation errors. An empty list means valid."""

