"""Append-only diagnostic snapshots in the existing workspace SQLite."""
from __future__ import annotations
import json
from causalops.assistant.service import digest
from causalops.general.service import DesignError
from .contracts import DiagnosticAssessment

def encoded(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True)

class DiagnosticRepository:
    def __init__(self,ws):
        self.ws=ws
        with ws.connection() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS diagnostic_assessments(
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, context_sha TEXT NOT NULL,
                    schema_version TEXT NOT NULL, rule_pack TEXT NOT NULL,
                    body TEXT NOT NULL, body_sha TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS diagnostic_observations(
                    id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL, finding_id TEXT NOT NULL,
                    body TEXT NOT NULL, body_sha TEXT NOT NULL,
                    UNIQUE(assessment_id,finding_id));
                CREATE TRIGGER IF NOT EXISTS diagnostic_assessments_no_update
                    BEFORE UPDATE ON diagnostic_assessments BEGIN SELECT RAISE(ABORT,'immutable diagnostic snapshot'); END;
                CREATE TRIGGER IF NOT EXISTS diagnostic_assessments_no_delete
                    BEFORE DELETE ON diagnostic_assessments BEGIN SELECT RAISE(ABORT,'immutable diagnostic snapshot'); END;
                CREATE TRIGGER IF NOT EXISTS diagnostic_observations_no_update
                    BEFORE UPDATE ON diagnostic_observations BEGIN SELECT RAISE(ABORT,'immutable diagnostic observation'); END;
                CREATE TRIGGER IF NOT EXISTS diagnostic_observations_no_delete
                    BEFORE DELETE ON diagnostic_observations BEGIN SELECT RAISE(ABORT,'immutable diagnostic observation'); END;
            """)

    def get(self,assessment_id,session_id):
        with self.ws.connection() as c:
            row=c.execute("SELECT session_id,body,body_sha FROM diagnostic_assessments WHERE id=?",(assessment_id,)).fetchone()
        if not row or row[0]!=session_id:raise DesignError("诊断快照不可用或不属于当前会话。")
        body=json.loads(row[1])
        if digest(body)!=row[2]:raise DesignError("诊断快照内容指纹不一致。")
        a=DiagnosticAssessment.model_validate(body)
        if a.assessment_id!=assessment_id or a.context.task_ref["session_id"]!=session_id:
            raise DesignError("诊断快照身份不一致。")
        return a

    def save(self,assessment,observations):
        body=assessment.model_dump(mode="json")
        with self.ws.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            prior=c.execute("SELECT id FROM diagnostic_assessments WHERE id=?",(assessment.assessment_id,)).fetchone()
            if not prior:
                c.execute("INSERT INTO diagnostic_assessments VALUES(?,?,?,?,?,?,?,?)",
                    (assessment.assessment_id,assessment.context.task_ref["session_id"],assessment.context_fingerprint,
                     assessment.schema_version,assessment.rule_pack,encoded(body),digest(body),assessment.created_at))
                for oid,fid,observation in observations:
                    c.execute("INSERT INTO diagnostic_observations VALUES(?,?,?,?,?)",
                        (oid,assessment.assessment_id,fid,encoded(observation),digest(observation)))
        return self.get(assessment.assessment_id,assessment.context.task_ref["session_id"])

    def observation(self,assessment_id,finding_id,session_id):
        a=self.get(assessment_id,session_id)
        f=next((f for f in a.findings if f.finding_id==finding_id),None)
        if f is None:raise DesignError("该诊断不属于当前快照。")
        with self.ws.connection() as c:
            row=c.execute("SELECT id,body,body_sha FROM diagnostic_observations WHERE assessment_id=? AND finding_id=?",
                (assessment_id,finding_id)).fetchone()
        if not row:raise DesignError("缺少诊断观察回执。")
        b=json.loads(row[1])
        ref=next((r for r in f.evidence_refs if r.artifact_kind=="validation_observation"),None)
        if not ref or ref.artifact_id!=row[0] or ref.sha!=row[2] or digest(b)!=row[2]:
            raise DesignError("诊断观察回执内容指纹不一致。")
        return b
