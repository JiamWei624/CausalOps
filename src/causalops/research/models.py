from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from causalops.schemas import CausalSpec


class DraftStatus(str, Enum):
    DRAFT = "draft"
    NEEDS_REVISION = "needs_revision"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    INVALID = "invalid"


class RevisionSource(str, Enum):
    AI_PROPOSAL = "ai_proposal"
    AI_CONVERSATION = "ai_conversation"
    USER_EDIT = "user_edit"
    CONVERSATION_REVISION = "conversation_revision"
    SYSTEM_INITIAL = "system_initial"


class ConversationIntent(str, Enum):
    EXPLAIN = "explain"
    MODIFY = "modify"
    COMPARE = "compare"
    DIAGNOSE = "diagnose"


@dataclass(frozen=True)
class ResearchSessionRecord:
    session_id: str
    title: str
    current_dataset_version_id: str
    current_draft_revision_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DatasetVersionRecord:
    dataset_version_id: str
    session_id: str
    version_number: int
    fingerprint_sha256: str
    row_count: int
    column_schema: dict[str, str]
    created_at: str


@dataclass(frozen=True)
class DraftRevisionRecord:
    revision_id: str
    session_id: str
    dataset_version_id: str
    version_number: int
    parent_revision_id: str | None
    source: RevisionSource
    change_reason: str
    spec: CausalSpec
    diff: dict[str, Any]
    research_notes: dict[str, Any]
    status: DraftStatus
    created_at: str


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    session_id: str
    revision_id: str
    dataset_version_id: str
    approved_by: str
    checklist: dict[str, bool]
    created_at: str


@dataclass(frozen=True)
class AnalysisRunRecord:
    run_id: str
    session_id: str
    revision_id: str
    dataset_version_id: str
    status: str
    result_bundle_path: str
    report_path: str
    created_at: str


@dataclass(frozen=True)
class DataAuditRecord:
    audit_id: str
    session_id: str
    revision_id: str
    dataset_version_id: str
    audit_type: str
    status: str
    report: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class ChatMessageRecord:
    message_id: str
    session_id: str
    revision_id: str | None
    role: str
    intent: ConversationIntent | None
    content: str
    created_at: str

