from __future__ import annotations

from typing import Any

from causalops.schemas import CausalSpec


def diff_specs(before: CausalSpec | None, after: CausalSpec) -> dict[str, Any]:
    """Return a stable top-level diff suitable for review and audit."""

    after_payload = after.model_dump(mode="json")
    if before is None:
        return {
            "changed_fields": sorted(after_payload),
            "changes": {
                field: {"before": None, "after": after_payload[field]}
                for field in sorted(after_payload)
            },
        }
    before_payload = before.model_dump(mode="json")
    changes = {
        field: {"before": before_payload.get(field), "after": after_payload.get(field)}
        for field in sorted(set(before_payload) | set(after_payload))
        if before_payload.get(field) != after_payload.get(field)
    }
    return {"changed_fields": list(changes), "changes": changes}

