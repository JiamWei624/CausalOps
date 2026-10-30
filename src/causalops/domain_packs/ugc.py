from __future__ import annotations

from causalops.schemas import CausalSpec, DomainName

from .base import DomainPack, MetricDefinition


class UGCPack(DomainPack):
    name = DomainName.UGC
    metrics = {
        "remention_any": MetricDefinition("remention_any", "Another @AI post observed before follow-up ends.", "mean", "user-post-event"),
        "remention_7d": MetricDefinition("remention_7d", "Another @AI post within 7 days; unknown if censored earlier.", "mean", "user-post-event"),
        "remention_30d": MetricDefinition("remention_30d", "Another @AI post within 30 days; unknown if censored earlier.", "mean", "user-post-event"),
        "post_count": MetricDefinition("post_count", "Number of original posts.", "sum", "user-day"),
        "comment_count": MetricDefinition("comment_count", "Number of comments.", "sum", "user-day"),
        "total_interactions": MetricDefinition(
            "total_interactions", "Posts, comments, likes and reposts.", "sum", "user-day"
        ),
        "post_total_interactions": MetricDefinition(
            "post_total_interactions",
            "Total posts, comments, likes and reposts in the declared follow-up window.",
            "sum",
            "user-follow-up-window",
        ),
        "is_active": MetricDefinition("is_active", "Whether the user was active that day.", "max", "user-day"),
    }

    def validate_spec(self, spec: CausalSpec) -> list[str]:
        errors: list[str] = []
        if spec.domain != self.name:
            errors.append("UGCPack can only validate domain='ugc'.")
        if spec.analysis_unit not in {"user", "user_day", "user-week", "user-month", "post_event"}:
            errors.append("UGC causal analysis must use a supported user-level analysis unit.")
        if spec.outcome not in self.metrics:
            errors.append(f"Unknown UGC outcome: {spec.outcome}.")
        if not spec.entity_id_column:
            errors.append("UGC analysis requires an entity_id_column to prevent cross-user leakage.")
        return errors

