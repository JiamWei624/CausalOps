"""Append-only reports and explicit user drafts in the original workspace."""
import json
from causalops.assistant.service import digest
from causalops.general.service import DesignError
from .repository import encoded
from .report_contracts import DiagnosticReportManifest, ResearchRequestDraft

class ReportRepository:
    def __init__(self, ws):
        self.ws = ws
        with ws.connection() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS diagnostic_reports(
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, task_id TEXT NOT NULL,
                    version INTEGER NOT NULL, body TEXT NOT NULL, body_sha TEXT NOT NULL,
                    UNIQUE(task_id,version));
                CREATE TABLE IF NOT EXISTS diagnostic_request_drafts(
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    body TEXT NOT NULL, body_sha TEXT NOT NULL, UNIQUE(session_id,request_id));
                CREATE TRIGGER IF NOT EXISTS diagnostic_reports_no_update
                    BEFORE UPDATE ON diagnostic_reports BEGIN SELECT RAISE(ABORT,'immutable report'); END;
                CREATE TRIGGER IF NOT EXISTS diagnostic_reports_no_delete
                    BEFORE DELETE ON diagnostic_reports BEGIN SELECT RAISE(ABORT,'immutable report'); END;
                CREATE TRIGGER IF NOT EXISTS diagnostic_request_drafts_no_update
                    BEFORE UPDATE ON diagnostic_request_drafts BEGIN SELECT RAISE(ABORT,'immutable request draft'); END;
                CREATE TRIGGER IF NOT EXISTS diagnostic_request_drafts_no_delete
                    BEFORE DELETE ON diagnostic_request_drafts BEGIN SELECT RAISE(ABORT,'immutable request draft'); END;
            """)

    def get(self, identifier, sid, *, draft=False):
        table = "diagnostic_request_drafts" if draft else "diagnostic_reports"
        model = ResearchRequestDraft if draft else DiagnosticReportManifest
        with self.ws.connection() as c:
            row = c.execute(f"SELECT body,body_sha FROM {table} WHERE id=? AND session_id=?",
                            (identifier, sid)).fetchone()
        if not row:
            raise DesignError("报告或草案不可用，或不属于当前会话。")
        body = json.loads(row[0])
        if digest(body) != row[1]:
            raise DesignError("报告或草案指纹不一致。")
        value = model.model_validate(body)
        expected_id = value.draft_id if draft else value.report_id
        owner = value.session_id if draft else value.context.task_ref.session_id
        if expected_id != identifier or owner != sid:
            raise DesignError("报告或草案身份冲突。")
        return value

    def save_report(self, body):
        sid = body["context"]["task_ref"]["session_id"]
        tid = body["context"]["task_ref"]["task_id"]
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            old = c.execute("SELECT id FROM diagnostic_reports WHERE id=?", (body["report_id"],)).fetchone()
            if not old:
                version = c.execute("SELECT COALESCE(MAX(version),0)+1 FROM diagnostic_reports WHERE task_id=?",
                                    (tid,)).fetchone()[0]
                body = {**body, "version": version}
                value = DiagnosticReportManifest.model_validate(body).model_dump(mode="json")
                c.execute("INSERT INTO diagnostic_reports VALUES(?,?,?,?,?,?)",
                          (body["report_id"], sid, tid, version, encoded(value), digest(value)))
        return self.get(body["report_id"], sid)

    def save_draft(self, draft, request_id):
        body = draft.model_dump(mode="json")
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            old = c.execute("SELECT id FROM diagnostic_request_drafts WHERE session_id=? AND request_id=?",
                            (draft.session_id, request_id)).fetchone()
            if old and old[0] != draft.draft_id:
                raise DesignError("同一保存请求已绑定不同内容。")
            if not old:
                c.execute("INSERT INTO diagnostic_request_drafts VALUES(?,?,?,?,?)",
                          (draft.draft_id, draft.session_id, request_id, encoded(body), digest(body)))
        return self.get(draft.draft_id, draft.session_id, draft=True)

