from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from causalops.schemas import CausalSpec

from .diff import diff_specs
from .models import (
    AnalysisRunRecord,
    ApprovalRecord,
    ChatMessageRecord,
    ConversationIntent,
    DataAuditRecord,
    DatasetVersionRecord,
    DraftRevisionRecord,
    DraftStatus,
    ResearchSessionRecord,
    RevisionSource,
)


class ResearchStateError(ValueError):
    """Raised when a requested lifecycle transition would break auditability."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class ResearchRepository:
    """SQLite-backed source of truth for study versions, approvals, and runs."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    current_dataset_version_id TEXT,
                    current_draft_revision_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dataset_versions (
                    dataset_version_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES research_sessions(session_id),
                    version_number INTEGER NOT NULL,
                    fingerprint_sha256 TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    column_schema_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, version_number)
                );
                CREATE TABLE IF NOT EXISTS draft_revisions (
                    revision_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES research_sessions(session_id),
                    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(dataset_version_id),
                    version_number INTEGER NOT NULL,
                    parent_revision_id TEXT REFERENCES draft_revisions(revision_id),
                    source TEXT NOT NULL,
                    change_reason TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    diff_json TEXT NOT NULL,
                    research_notes_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, version_number)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES research_sessions(session_id),
                    revision_id TEXT NOT NULL UNIQUE REFERENCES draft_revisions(revision_id),
                    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(dataset_version_id),
                    approved_by TEXT NOT NULL,
                    checklist_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES research_sessions(session_id),
                    revision_id TEXT NOT NULL REFERENCES draft_revisions(revision_id),
                    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(dataset_version_id),
                    status TEXT NOT NULL,
                    result_bundle_path TEXT NOT NULL,
                    report_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_audits (
                    audit_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES research_sessions(session_id),
                    revision_id TEXT NOT NULL REFERENCES draft_revisions(revision_id),
                    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(dataset_version_id),
                    audit_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES research_sessions(session_id),
                    revision_id TEXT REFERENCES draft_revisions(revision_id),
                    role TEXT NOT NULL,
                    intent TEXT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES research_sessions(session_id),
                    event_type TEXT NOT NULL,
                    object_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS result_evidence_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
                    schema_version TEXT NOT NULL,
                    bundle_sha256 TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, schema_version)
                );
                CREATE TABLE IF NOT EXISTS result_qa_turns (
                    turn_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
                    snapshot_id TEXT NOT NULL REFERENCES result_evidence_snapshots(snapshot_id),
                    question TEXT NOT NULL,
                    answer_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_result_qa_run
                    ON result_qa_turns(run_id, snapshot_id, created_at);
                CREATE TABLE IF NOT EXISTS result_qa_evaluation_labels (
                    turn_id TEXT PRIMARY KEY REFERENCES result_qa_turns(turn_id),
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS association_authorizations (
                    authorization_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL UNIQUE REFERENCES draft_revisions(revision_id),
                    dataset_version_id TEXT NOT NULL REFERENCES dataset_versions(dataset_version_id),
                    authorized_by TEXT NOT NULL,
                    authorization_note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_dataset_fingerprint
                    ON dataset_versions(fingerprint_sha256, created_at);
                CREATE INDEX IF NOT EXISTS idx_draft_session_version
                    ON draft_revisions(session_id, version_number);
                CREATE INDEX IF NOT EXISTS idx_chat_session_time
                    ON chat_messages(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_data_audit_binding
                    ON data_audits(revision_id, dataset_version_id, created_at);
                """
            )
            revision_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(draft_revisions)").fetchall()
            }
            if "research_notes_json" not in revision_columns:
                connection.execute(
                    "ALTER TABLE draft_revisions "
                    "ADD COLUMN research_notes_json TEXT NOT NULL DEFAULT '{}'"
                )

    def _audit(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        event_type: str,
        object_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?)",
            (_id("evt"), session_id, event_type, object_id, json.dumps(payload, ensure_ascii=False), _now()),
        )

    def create_session(
        self,
        *,
        title: str,
        dataset_fingerprint: str,
        row_count: int,
        column_schema: dict[str, str],
    ) -> ResearchSessionRecord:
        session_id = _id("session")
        dataset_id = _id("dataset")
        created_at = _now()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO research_sessions VALUES (?, ?, NULL, NULL, ?, ?)",
                (session_id, title, created_at, created_at),
            )
            connection.execute(
                "INSERT INTO dataset_versions VALUES (?, ?, 1, ?, ?, ?, ?)",
                (
                    dataset_id,
                    session_id,
                    dataset_fingerprint,
                    row_count,
                    json.dumps(column_schema, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
            connection.execute(
                "UPDATE research_sessions SET current_dataset_version_id = ? WHERE session_id = ?",
                (dataset_id, session_id),
            )
            self._audit(connection, session_id, "session_created", session_id, {"dataset_version_id": dataset_id})
        return self.get_session(session_id)

    def find_latest_session_by_dataset(self, fingerprint: str) -> ResearchSessionRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT s.* FROM research_sessions s
                JOIN dataset_versions d ON d.dataset_version_id = s.current_dataset_version_id
                WHERE d.fingerprint_sha256 = ?
                ORDER BY s.updated_at DESC LIMIT 1
                """,
                (fingerprint,),
            ).fetchone()
        return self._session_from_row(row) if row else None

    def get_session(self, session_id: str) -> ResearchSessionRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise ResearchStateError(f"研究会话不存在：{session_id}")
        return self._session_from_row(row)

    def list_sessions(self) -> list[ResearchSessionRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM research_sessions ORDER BY updated_at DESC, session_id"
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def _session_from_row(self, row: sqlite3.Row) -> ResearchSessionRecord:
        return ResearchSessionRecord(
            session_id=row["session_id"],
            title=row["title"],
            current_dataset_version_id=row["current_dataset_version_id"],
            current_draft_revision_id=row["current_draft_revision_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def register_dataset_version(
        self,
        session_id: str,
        *,
        fingerprint: str,
        row_count: int,
        column_schema: dict[str, str],
    ) -> DatasetVersionRecord:
        dataset_id = _id("dataset")
        with self._connection() as connection:
            session = connection.execute(
                "SELECT * FROM research_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise ResearchStateError(f"研究会话不存在：{session_id}")
            current = connection.execute(
                "SELECT * FROM dataset_versions WHERE dataset_version_id = ?",
                (session["current_dataset_version_id"],),
            ).fetchone()
            if current and current["fingerprint_sha256"] == fingerprint:
                return self._dataset_from_row(current)
            version = int(
                connection.execute(
                    "SELECT COALESCE(MAX(version_number), 0) + 1 FROM dataset_versions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0]
            )
            created_at = _now()
            connection.execute(
                "INSERT INTO dataset_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    dataset_id,
                    session_id,
                    version,
                    fingerprint,
                    row_count,
                    json.dumps(column_schema, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
            connection.execute(
                "UPDATE research_sessions SET current_dataset_version_id = ?, updated_at = ? WHERE session_id = ?",
                (dataset_id, created_at, session_id),
            )
            self._audit(connection, session_id, "dataset_version_created", dataset_id, {"version": version})
        return self.get_dataset_version(dataset_id)

    def get_dataset_version(self, dataset_version_id: str) -> DatasetVersionRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM dataset_versions WHERE dataset_version_id = ?",
                (dataset_version_id,),
            ).fetchone()
        if row is None:
            raise ResearchStateError(f"数据集版本不存在：{dataset_version_id}")
        return self._dataset_from_row(row)

    def _dataset_from_row(self, row: sqlite3.Row) -> DatasetVersionRecord:
        return DatasetVersionRecord(
            dataset_version_id=row["dataset_version_id"],
            session_id=row["session_id"],
            version_number=int(row["version_number"]),
            fingerprint_sha256=row["fingerprint_sha256"],
            row_count=int(row["row_count"]),
            column_schema=json.loads(row["column_schema_json"]),
            created_at=row["created_at"],
        )

    def create_revision(
        self,
        session_id: str,
        spec: CausalSpec,
        *,
        source: RevisionSource,
        change_reason: str,
        parent_revision_id: str | None = None,
        activate: bool = False,
        status: DraftStatus = DraftStatus.DRAFT,
        research_notes: dict[str, Any] | None = None,
    ) -> DraftRevisionRecord:
        revision_id = _id("revision")
        with self._connection() as connection:
            session = connection.execute(
                "SELECT * FROM research_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise ResearchStateError(f"研究会话不存在：{session_id}")
            parent_id = parent_revision_id or session["current_draft_revision_id"]
            parent_spec: CausalSpec | None = None
            if parent_id:
                parent = connection.execute(
                    "SELECT * FROM draft_revisions WHERE revision_id = ? AND session_id = ?",
                    (parent_id, session_id),
                ).fetchone()
                if parent is None:
                    raise ResearchStateError("来源草案不属于当前研究会话。")
                parent_spec = CausalSpec.model_validate_json(parent["spec_json"])
            version = int(
                connection.execute(
                    "SELECT COALESCE(MAX(version_number), 0) + 1 FROM draft_revisions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0]
            )
            created_at = _now()
            change_diff = diff_specs(parent_spec, spec)
            connection.execute(
                """
                INSERT INTO draft_revisions (
                    revision_id, session_id, dataset_version_id, version_number,
                    parent_revision_id, source, change_reason, spec_json, diff_json,
                    research_notes_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    session_id,
                    session["current_dataset_version_id"],
                    version,
                    parent_id,
                    source.value,
                    change_reason,
                    spec.model_dump_json(),
                    json.dumps(change_diff, ensure_ascii=False, sort_keys=True),
                    json.dumps(research_notes or {}, ensure_ascii=False, sort_keys=True),
                    status.value,
                    created_at,
                ),
            )
            if activate:
                connection.execute(
                    "UPDATE research_sessions SET current_draft_revision_id = ?, updated_at = ? WHERE session_id = ?",
                    (revision_id, created_at, session_id),
                )
            self._audit(
                connection,
                session_id,
                "draft_revision_created",
                revision_id,
                {"version": version, "active": activate, "status": status.value},
            )
        return self.get_revision(revision_id)

    def get_revision(self, revision_id: str) -> DraftRevisionRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM draft_revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone()
        if row is None:
            raise ResearchStateError(f"草案版本不存在：{revision_id}")
        return self._revision_from_row(row)

    def list_revisions(self, session_id: str) -> list[DraftRevisionRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM draft_revisions WHERE session_id = ? ORDER BY version_number",
                (session_id,),
            ).fetchall()
        return [self._revision_from_row(row) for row in rows]

    def _revision_from_row(self, row: sqlite3.Row) -> DraftRevisionRecord:
        return DraftRevisionRecord(
            revision_id=row["revision_id"],
            session_id=row["session_id"],
            dataset_version_id=row["dataset_version_id"],
            version_number=int(row["version_number"]),
            parent_revision_id=row["parent_revision_id"],
            source=RevisionSource(row["source"]),
            change_reason=row["change_reason"],
            spec=CausalSpec.model_validate_json(row["spec_json"]),
            diff=json.loads(row["diff_json"]),
            research_notes=json.loads(row["research_notes_json"] or "{}"),
            status=DraftStatus(row["status"]),
            created_at=row["created_at"],
        )

    def accept_candidate(self, revision_id: str) -> DraftRevisionRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM draft_revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            if row is None:
                raise ResearchStateError(f"候选草案不存在：{revision_id}")
            if DraftStatus(row["status"]) not in {DraftStatus.DRAFT, DraftStatus.NEEDS_REVISION}:
                raise ResearchStateError("只有草案或待修改版本可以被接受为当前草案。")
            now = _now()
            accepted_status = (
                DraftStatus.PENDING_REVIEW
                if DraftStatus(row["status"]) == DraftStatus.DRAFT
                else DraftStatus.NEEDS_REVISION
            )
            connection.execute(
                "UPDATE draft_revisions SET status = ? WHERE revision_id = ?",
                (accepted_status.value, revision_id),
            )
            connection.execute(
                "UPDATE research_sessions SET current_draft_revision_id = ?, updated_at = ? WHERE session_id = ?",
                (revision_id, now, row["session_id"]),
            )
            self._audit(connection, row["session_id"], "candidate_accepted", revision_id, {})
        return self.get_revision(revision_id)

    def reject_candidate(self, revision_id: str) -> DraftRevisionRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM draft_revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            if row is None:
                raise ResearchStateError(f"候选草案不存在：{revision_id}")
            if DraftStatus(row["status"]) in {DraftStatus.APPROVED, DraftStatus.REJECTED}:
                raise ResearchStateError("已批准或已拒绝的草案不能再次拒绝。")
            connection.execute(
                "UPDATE draft_revisions SET status = ? WHERE revision_id = ?",
                (DraftStatus.REJECTED.value, revision_id),
            )
            self._audit(connection, row["session_id"], "candidate_rejected", revision_id, {})
        return self.get_revision(revision_id)

    def approve_revision(
        self,
        revision_id: str,
        *,
        approved_by: str,
        checklist: dict[str, bool],
    ) -> ApprovalRecord:
        if not checklist or not all(checklist.values()):
            raise ResearchStateError("人工审核清单尚未全部确认。")
        approval_id = _id("approval")
        with self._connection() as connection:
            revision = connection.execute(
                "SELECT * FROM draft_revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            if revision is None:
                raise ResearchStateError(f"草案版本不存在：{revision_id}")
            session = connection.execute(
                "SELECT * FROM research_sessions WHERE session_id = ?",
                (revision["session_id"],),
            ).fetchone()
            if session["current_draft_revision_id"] != revision_id:
                raise ResearchStateError("只能批准当前草案版本。")
            if session["current_dataset_version_id"] != revision["dataset_version_id"]:
                raise ResearchStateError("数据集版本已变化，必须重新验证并创建新草案。")
            if DraftStatus(revision["status"]) != DraftStatus.PENDING_REVIEW:
                raise ResearchStateError("草案尚未进入待人工审核状态。")
            created_at = _now()
            connection.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    approval_id,
                    revision["session_id"],
                    revision_id,
                    revision["dataset_version_id"],
                    approved_by,
                    json.dumps(checklist, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
            connection.execute(
                "UPDATE draft_revisions SET status = ? WHERE revision_id = ?",
                (DraftStatus.APPROVED.value, revision_id),
            )
            self._audit(connection, revision["session_id"], "revision_approved", revision_id, {})
        return self.get_approval(revision_id)

    def get_approval(self, revision_id: str) -> ApprovalRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE revision_id = ?", (revision_id,)
            ).fetchone()
        if row is None:
            raise ResearchStateError("该草案没有有效审批记录。")
        return ApprovalRecord(
            approval_id=row["approval_id"],
            session_id=row["session_id"],
            revision_id=row["revision_id"],
            dataset_version_id=row["dataset_version_id"],
            approved_by=row["approved_by"],
            checklist=json.loads(row["checklist_json"]),
            created_at=row["created_at"],
        )

    def bind_analysis_run(
        self,
        *,
        session_id: str,
        revision_id: str,
        dataset_version_id: str,
        run_id: str,
        result_bundle_path: str,
        report_path: str,
        execution_scope: str = "approved",
    ) -> AnalysisRunRecord:
        if execution_scope == 'association_only':
            self.assert_association_execution_authorized(session_id=session_id,revision_id=revision_id,
                                                         dataset_version_id=dataset_version_id)
            from causalops.schemas import ResultBundle, ClaimLevel, CausalMethod
            bundle = ResultBundle.model_validate_json(Path(result_bundle_path).read_text(encoding='utf-8'))
            revision = self.get_revision(revision_id)
            if (bundle.run_id!=run_id or bundle.spec!=revision.spec or bundle.claim_level!=ClaimLevel.ASSOCIATIONAL
                    or bundle.plan.selected_method!=CausalMethod.REGRESSION_ADJUSTMENT):
                raise ResearchStateError('关联执行记录必须匹配草案，且不得升级为因果主张。')
        elif execution_scope == 'approved':
            self.assert_execution_authorized(session_id=session_id,revision_id=revision_id,dataset_version_id=dataset_version_id)
        else:
            raise ResearchStateError('未知执行授权范围。')
        with self._connection() as connection:
            created_at = _now()
            connection.execute(
                "INSERT INTO analysis_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    session_id,
                    revision_id,
                    dataset_version_id,
                    "completed",
                    result_bundle_path,
                    report_path,
                    created_at,
                ),
            )
            self._audit(connection, session_id, "analysis_run_bound", run_id, {"revision_id": revision_id})
        return self.get_analysis_run(run_id)

    def assert_execution_authorized(
        self,
        *,
        session_id: str,
        revision_id: str,
        dataset_version_id: str,
    ) -> ApprovalRecord:
        """Fail before any estimator runs unless exact versions are approved."""

        with self._connection() as connection:
            session = connection.execute(
                "SELECT * FROM research_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            revision = connection.execute(
                "SELECT * FROM draft_revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            approval = connection.execute(
                "SELECT * FROM approvals WHERE revision_id = ?", (revision_id,)
            ).fetchone()
        if session is None or revision is None:
            raise ResearchStateError("研究会话或草案版本不存在。")
        if revision["session_id"] != session_id:
            raise ResearchStateError("草案不属于当前研究会话。")
        if session["current_draft_revision_id"] != revision_id:
            raise ResearchStateError("只能执行当前草案版本。")
        if session["current_dataset_version_id"] != dataset_version_id:
            raise ResearchStateError("只能对当前数据集版本执行分析。")
        if revision["dataset_version_id"] != dataset_version_id:
            raise ResearchStateError("草案与数据集版本不一致。")
        if DraftStatus(revision["status"]) != DraftStatus.APPROVED:
            raise ResearchStateError("当前草案尚未处于已批准状态。")
        if approval is None or approval["dataset_version_id"] != dataset_version_id:
            raise ResearchStateError("当前草案和数据集版本尚未获得有效人工审批。")
        return ApprovalRecord(
            approval_id=approval["approval_id"],
            session_id=approval["session_id"],
            revision_id=approval["revision_id"],
            dataset_version_id=approval["dataset_version_id"],
            approved_by=approval["approved_by"],
            checklist=json.loads(approval["checklist_json"]),
            created_at=approval["created_at"],
        )

    def get_analysis_run(self, run_id: str) -> AnalysisRunRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise ResearchStateError(f"分析运行不存在：{run_id}")
        return AnalysisRunRecord(
            run_id=row["run_id"],
            session_id=row["session_id"],
            revision_id=row["revision_id"],
            dataset_version_id=row["dataset_version_id"],
            status=row["status"],
            result_bundle_path=row["result_bundle_path"],
            report_path=row["report_path"],
            created_at=row["created_at"],
        )

    def authorize_association_analysis(self, revision_id: str, *, authorized_by: str,
                                       authorization_note: str) -> None:
        """Record explicit user permission without falsely approving identification assumptions."""
        if not authorized_by or len(authorization_note.strip())<15:
            raise ResearchStateError('必须记录真实的用户授权来源和执行范围。')
        revision=self.get_revision(revision_id)
        self._check_association_design(revision)
        session=self.get_session(revision.session_id)
        if session.current_draft_revision_id!=revision_id or session.current_dataset_version_id!=revision.dataset_version_id:
            raise ResearchStateError('只能授权当前草案和当前数据版本。')
        with self._connection() as connection:
            connection.execute('INSERT OR IGNORE INTO association_authorizations VALUES (?,?,?,?,?,?)',
                (_id('association_auth'),revision_id,revision.dataset_version_id,authorized_by,authorization_note,_now()))
            self._audit(connection,revision.session_id,'association_execution_authorized',revision_id,
                        {'scope':'association_only','identification_assumptions_approved':False})

    @staticmethod
    def _check_association_design(revision: DraftRevisionRecord) -> None:
        from causalops.schemas import CausalMethod, AssignmentMechanism
        if (revision.spec.candidate_methods != [CausalMethod.REGRESSION_ADJUSTMENT]
                or revision.spec.assignment_mechanism != AssignmentMechanism.OBSERVATIONAL):
            raise ResearchStateError('此授权仅适用于单一观察性回归调整设计。')

    def get_association_authorization(self, revision_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row=connection.execute('SELECT * FROM association_authorizations WHERE revision_id=?',(revision_id,)).fetchone()
        return dict(row) if row else None

    def assert_association_execution_authorized(self, *, session_id: str, revision_id: str,
                                               dataset_version_id: str) -> None:
        revision=self.get_revision(revision_id)
        self._check_association_design(revision)
        session=self.get_session(session_id)
        auth=self.get_association_authorization(revision_id)
        if (not auth or revision.session_id!=session_id or session.current_draft_revision_id!=revision_id
                or session.current_dataset_version_id!=dataset_version_id
                or auth['dataset_version_id']!=dataset_version_id or revision.dataset_version_id!=dataset_version_id):
            raise ResearchStateError('缺少与当前草案、数据版本绑定的仅关联分析授权。')

    def get_latest_analysis_run(
        self, *, revision_id: str, dataset_version_id: str
    ) -> AnalysisRunRecord | None:
        """Return only a completed run bound to these exact versions."""
        with self._connection() as connection:
            row = connection.execute(
                """SELECT run_id FROM analysis_runs
                   WHERE revision_id = ? AND dataset_version_id = ? AND status = 'completed'
                   ORDER BY created_at DESC, run_id DESC LIMIT 1""",
                (revision_id, dataset_version_id),
            ).fetchone()
        return self.get_analysis_run(row["run_id"]) if row else None

    def list_analysis_runs(self, *, revision_id: str, dataset_version_id: str) -> list[AnalysisRunRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT run_id FROM analysis_runs WHERE revision_id=? AND dataset_version_id=? "
                "AND status='completed' ORDER BY created_at DESC, run_id DESC",
                (revision_id, dataset_version_id),
            ).fetchall()
        return [self.get_analysis_run(row["run_id"]) for row in rows]

    def save_result_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Insert once. A changed result file must never overwrite an earlier snapshot."""
        run = self.get_analysis_run(snapshot["run_id"])
        if run.status != "completed":
            raise ResearchStateError("只能为已完成的运行创建结果证据。")
        serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        with self._connection() as connection:
            old = connection.execute(
                "SELECT evidence_json FROM result_evidence_snapshots WHERE run_id=? AND schema_version=?",
                (run.run_id, snapshot["schema_version"]),
            ).fetchone()
            if old:
                if json.loads(old["evidence_json"]) != snapshot:
                    raise ResearchStateError("同一运行的结果证据已改变，拒绝覆盖历史快照。")
            else:
                connection.execute("INSERT INTO result_evidence_snapshots VALUES (?,?,?,?,?,?)", (
                    snapshot["snapshot_id"], run.run_id, snapshot["schema_version"],
                    snapshot["bundle_sha256"], serialized, _now(),
                ))
        return snapshot

    def add_result_qa_turn(self, *, run_id: str, snapshot_id: str, question: str,
                           answer: dict[str, Any]) -> dict[str, Any]:
        turn = {"turn_id": _id("result_qa"), "run_id": run_id, "snapshot_id": snapshot_id,
                "question": question, "answer": answer, "created_at": _now()}
        with self._connection() as connection:
            snapshot = connection.execute(
                "SELECT run_id FROM result_evidence_snapshots WHERE snapshot_id=?", (snapshot_id,),
            ).fetchone()
            if not snapshot or snapshot["run_id"] != run_id or answer.get("run_id") != run_id:
                raise ResearchStateError("回答、证据快照与分析运行不一致。")
            connection.execute("INSERT INTO result_qa_turns VALUES (?,?,?,?,?,?)", (
                turn["turn_id"], run_id, snapshot_id, question,
                json.dumps(answer, ensure_ascii=False, sort_keys=True), turn["created_at"],
            ))
        return turn

    def list_result_qa_turns(self, *, run_id: str, snapshot_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM result_qa_turns WHERE run_id=? AND snapshot_id=? ORDER BY created_at, rowid",
                (run_id, snapshot_id),
            ).fetchall()
            evaluation_ids = {r["turn_id"] for r in connection.execute(
                "SELECT turn_id FROM result_qa_evaluation_labels").fetchall()}
        return [{"turn_id": r["turn_id"], "run_id": r["run_id"], "snapshot_id": r["snapshot_id"],
                 "question": r["question"], "answer": json.loads(r["answer_json"]),
                 "origin": "acceptance_test" if r["turn_id"] in evaluation_ids else "user",
                 "created_at": r["created_at"]} for r in rows]

    def list_previous_result_qa_turns(self, *, run_id: str, exclude_snapshot_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows=connection.execute("SELECT t.* FROM result_qa_turns t WHERE t.run_id=? AND t.snapshot_id<>? AND NOT EXISTS (SELECT 1 FROM result_qa_evaluation_labels e WHERE e.turn_id=t.turn_id) ORDER BY t.created_at,t.rowid",(run_id,exclude_snapshot_id)).fetchall()
        return [{'turn_id':x['turn_id'],'question':x['question'],'answer':json.loads(x['answer_json']),'snapshot_id':x['snapshot_id']} for x in rows]

    def mark_result_qa_evaluation(self, turn_id: str) -> None:
        """Append a presentation label without altering original question/answer evidence."""
        with self._connection() as connection:
            connection.execute("INSERT OR IGNORE INTO result_qa_evaluation_labels VALUES (?,?,?)",
                               (turn_id, "自动验收", _now()))

    def record_data_audit(
        self,
        *,
        session_id: str,
        revision_id: str,
        dataset_version_id: str,
        audit_type: str,
        status: str,
        report: dict[str, Any],
    ) -> DataAuditRecord:
        """Persist an immutable audit bound to one exact draft and dataset version."""

        audit_id = _id("data_audit")
        created_at = _now()
        with self._connection() as connection:
            revision = connection.execute(
                "SELECT * FROM draft_revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            if revision is None or revision["session_id"] != session_id:
                raise ResearchStateError("数据审计对应的草案不属于当前研究会话。")
            if revision["dataset_version_id"] != dataset_version_id:
                raise ResearchStateError("数据审计必须绑定草案创建时的数据集版本。")
            connection.execute(
                "INSERT INTO data_audits VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    audit_id,
                    session_id,
                    revision_id,
                    dataset_version_id,
                    audit_type,
                    status,
                    json.dumps(report, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
            self._audit(
                connection,
                session_id,
                "data_audit_recorded",
                audit_id,
                {
                    "revision_id": revision_id,
                    "dataset_version_id": dataset_version_id,
                    "audit_type": audit_type,
                    "status": status,
                },
            )
        return self.get_data_audit(audit_id)

    def get_data_audit(self, audit_id: str) -> DataAuditRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM data_audits WHERE audit_id = ?", (audit_id,)
            ).fetchone()
        if row is None:
            raise ResearchStateError(f"数据审计记录不存在：{audit_id}")
        return self._data_audit_from_row(row)

    def get_latest_data_audit(
        self,
        *,
        revision_id: str,
        dataset_version_id: str,
        audit_type: str = "did_panel_pretrend_v1",
    ) -> DataAuditRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM data_audits
                WHERE revision_id = ? AND dataset_version_id = ? AND audit_type = ?
                ORDER BY created_at DESC, audit_id DESC LIMIT 1
                """,
                (revision_id, dataset_version_id, audit_type),
            ).fetchone()
        return self._data_audit_from_row(row) if row else None

    @staticmethod
    def _data_audit_from_row(row: sqlite3.Row) -> DataAuditRecord:
        return DataAuditRecord(
            audit_id=row["audit_id"],
            session_id=row["session_id"],
            revision_id=row["revision_id"],
            dataset_version_id=row["dataset_version_id"],
            audit_type=row["audit_type"],
            status=row["status"],
            report=json.loads(row["report_json"]),
            created_at=row["created_at"],
        )

    def add_chat_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        revision_id: str | None = None,
        intent: ConversationIntent | None = None,
    ) -> ChatMessageRecord:
        if role not in {"user", "assistant", "system"}:
            raise ResearchStateError(f"不支持的消息角色：{role}")
        message_id = _id("message")
        created_at = _now()
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM research_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not exists:
                raise ResearchStateError(f"研究会话不存在：{session_id}")
            connection.execute(
                "INSERT INTO chat_messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    message_id,
                    session_id,
                    revision_id,
                    role,
                    intent.value if intent else None,
                    content,
                    created_at,
                ),
            )
        return ChatMessageRecord(
            message_id=message_id,
            session_id=session_id,
            revision_id=revision_id,
            role=role,
            intent=intent,
            content=content,
            created_at=created_at,
        )

    def list_chat_messages(self, session_id: str) -> list[ChatMessageRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at, message_id",
                (session_id,),
            ).fetchall()
        return [
            ChatMessageRecord(
                message_id=row["message_id"],
                session_id=row["session_id"],
                revision_id=row["revision_id"],
                role=row["role"],
                intent=ConversationIntent(row["intent"]) if row["intent"] else None,
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

