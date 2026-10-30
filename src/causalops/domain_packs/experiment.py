from __future__ import annotations

from causalops.schemas import CausalMethod, CausalSpec, DomainName

from .base import DomainPack, MetricDefinition


class ExperimentPack(DomainPack):
    name = DomainName.EXPERIMENT
    metrics = {
        "conversion": MetricDefinition("conversion", "Binary conversion outcome.", "mean", "randomization-unit"),
        "retention_7d": MetricDefinition("retention_7d", "Seven-day retention.", "mean", "user"),
        "revenue": MetricDefinition("revenue", "Net revenue in the analysis window.", "sum", "user"),
    }

    def validate_spec(self, spec: CausalSpec) -> list[str]:
        errors: list[str] = []
        if spec.domain != self.name:
            errors.append("ExperimentPack can only validate domain='experiment'.")
        allowed = {CausalMethod.AB_TEST, CausalMethod.CUPED}
        if spec.candidate_methods and not set(spec.candidate_methods).issubset(allowed):
            errors.append("ExperimentPack currently supports only A/B testing and CUPED.")
        if not spec.entity_id_column:
            errors.append("Experiment analysis requires the randomization-unit ID column.")
        if spec.outcome not in self.metrics:
            errors.append(f"Unknown experiment outcome: {spec.outcome}.")
        return errors

