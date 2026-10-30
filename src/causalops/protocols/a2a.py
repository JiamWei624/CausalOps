from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from causalops.identification import route_identification
from causalops.schemas import CausalSpec, GateStatus


A2A_PROTOCOL_VERSION = "1.0"


class TaskState(str, Enum):
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    REJECTED = "TASK_STATE_REJECTED"


class A2ATask(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    context_id: str = Field(alias="contextId")
    status: dict[str, Any]
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_agent_card(base_url: str = "http://127.0.0.1:8501/a2a/v1") -> dict[str, Any]:
    """Return an A2A 1.0 Agent Card for the local, non-network-certified contract."""

    return {
        "name": "CausalOps Design Agent",
        "description": "Designs and gates reproducible causal analyses; estimator execution requires human approval.",
        "supportedInterfaces": [
            {
                "url": base_url,
                "protocolBinding": "JSONRPC",
                "protocolVersion": A2A_PROTOCOL_VERSION,
            }
        ],
        "version": "0.1.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json", "text/markdown"],
        "skills": [
            {
                "id": "causal-design-and-gating",
                "name": "Causal design and identification gating",
                "description": "Validates a CausalSpec, routes a defensible method, and refuses unsupported causal claims.",
                "tags": ["causal-inference", "experimentation", "diagnostics", "reproducibility"],
                "examples": ["Design an analysis for whether AI replies increase later UGC activity."],
                "inputModes": ["application/json"],
                "outputModes": ["application/json", "text/markdown"],
            }
        ],
    }


class LocalA2ACoordinator:
    """Auditable local role handoff using A2A-shaped task objects.

    This is not a remote A2A server. It makes the design-agent -> identification-agent
    -> approval boundary explicit and testable before a network transport is added.
    """

    def send_spec(self, spec_payload: dict[str, Any], *, context_id: str | None = None) -> A2ATask:
        task_id = str(uuid.uuid4())
        context_id = context_id or str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        history = [
            {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_USER",
                "parts": [{"data": {"causalSpec": spec_payload}}],
            }
        ]
        try:
            spec = CausalSpec.model_validate(spec_payload)
            decision = route_identification(spec)
        except Exception as exc:
            return A2ATask(
                id=task_id,
                contextId=context_id,
                status={"state": TaskState.REJECTED.value, "timestamp": timestamp},
                artifacts=[
                    {
                        "artifactId": str(uuid.uuid4()),
                        "name": "Validation error",
                        "parts": [{"text": str(exc)}],
                    }
                ],
                history=history,
                metadata={"executionPerformed": False},
            )

        state = TaskState.INPUT_REQUIRED if decision.status != GateStatus.PASS else TaskState.COMPLETED
        artifact = {
            "artifactId": str(uuid.uuid4()),
            "name": "Identification decision",
            "parts": [{"data": decision.model_dump(mode="json")}],
        }
        return A2ATask(
            id=task_id,
            contextId=context_id,
            status={"state": state.value, "timestamp": timestamp},
            artifacts=[artifact],
            history=history,
            metadata={
                "rolesCompleted": ["design_validator", "identification_gate"],
                "humanApprovalRequired": True,
                "executionPerformed": False,
            },
        )
