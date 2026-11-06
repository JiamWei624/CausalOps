"""Read-only workbench facade over the existing diagnostics/report services.

Only explicit create/save calls write diagnostic-owned tables. History and view
loading never approve or dispatch statistics. No independent fact store/cache.
"""
from dataclasses import dataclass
from causalops.general.service import DesignError
from causalops.assistant.service import digest
from .reports import DiagnosticReportService

@dataclass(frozen=True)
class ReportView:
    report: object
    source_current: bool
    source_error: str | None

def safe_error(exc):
    if isinstance(exc,DesignError):
        return str(exc)
    return "读取或核验未完成（"+type(exc).__name__+"）；未展示替代结果，请保留记录并核对来源。"

class DiagnosticWorkbench:
    def __init__(self,service):
        self.s=service
        self.reports=DiagnosticReportService(service)

    def subjects(self,mode):
        if mode not in ("preflight","post_run"):raise DesignError("诊断模式不受支持。")
        if mode=="preflight":
            return [dict(id=x["id"],session_id=x["id"],title=x["title"],status="已登记数据")
                    for x in self.s.a.sessions()]
        with self.s.ws.connection() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='automation_v2_tasks'").fetchone():
                return []
            rows=c.execute("SELECT id,session_id,status FROM automation_v2_tasks ORDER BY created DESC,id DESC").fetchall()
        return [dict(id=r[0],session_id=r[1],title="自动化研究",status=r[2]) for r in rows]

    def subject(self,mode,identifier):
        item=next((x for x in self.subjects(mode) if x["id"]==identifier),None)
        if item is None:raise DesignError("所选研究任务不可用，请明确选择当前工作区中的任务。")
        return item

    @staticmethod
    def _binding(report,mode,item):
        kind="research_session" if mode=="preflight" else "automation_v2"
        ref=report.context.task_ref
        if ref.kind!=kind or ref.task_id!=item["id"] or ref.session_id!=item["session_id"]:
            raise DesignError("诊断报告与当前任务或模式不一致；未展示其他任务结果。")

    def history(self,mode,identifier):
        item=self.subject(mode,identifier)
        with self.s.ws.connection() as c:
            return [dict(id=r[0],version=r[1]) for r in c.execute(
                "SELECT id,version FROM diagnostic_reports WHERE task_id=? AND session_id=? ORDER BY version DESC",
                (identifier,item["session_id"]))]

    def create(self,mode,identifier):
        item=self.subject(mode,identifier)
        if mode=="preflight":return self.reports.preflight(item["session_id"])
        return self.reports.post_run(identifier,session_id=item["session_id"])

    def load(self,mode,identifier,report_id):
        item=self.subject(mode,identifier)
        report=self.reports.get(report_id,session_id=item["session_id"])
        self._binding(report,mode,item)
        assessment=self.reports.diagnostics.get(report.assessment_id,session_id=item["session_id"])
        try:
            # Existing stage-two read-only check; no generation or mutation.
            self.reports._verify_inputs(assessment)
            return ReportView(report,True,None)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:
            return ReportView(report,False,safe_error(exc))

    def evidence(self,mode,identifier,report_id,finding_id):
        item=self.subject(mode,identifier)
        report=self.reports.get(report_id,session_id=item["session_id"])
        self._binding(report,mode,item)
        return self.reports.diagnostics.evidence(report.assessment_id,finding_id,session_id=item["session_id"])

    def original_evidence(self,mode,identifier,report_id):
        item=self.subject(mode,identifier)
        report=self.reports.get(report_id,session_id=item["session_id"])
        self._binding(report,mode,item)
        assessment=self.reports.diagnostics.get(report.assessment_id,session_id=item["session_id"])
        native=self.reports._verify_inputs(assessment)
        if not native.task or report.results.status!="available":
            raise DesignError("当前没有可完整引用的双Run证据；请查看诊断回执与部分完成说明。")
        return {step:native.evidence[step] for step in ("S02","S03","S04","S05")}

    def save(self,mode,identifier,report_id,suggestion_id,intent,*,confirmed=False):
        item=self.subject(mode,identifier)
        view=self.load(mode,identifier,report_id)
        if not view.source_current:raise DesignError("建议来源已过期，请重新检查研究证据；旧报告和已有草案保留。")
        # Stable across refresh/repeated submission; changed intent is a distinct request.
        request_id=digest({"report":report_id,"suggestion":suggestion_id,"intent":intent.strip()})
        return self.reports.save_draft(report_id,suggestion_id,session_id=item["session_id"],
            user_intent=intent.strip(),request_id=request_id,human_confirmed=confirmed)

    def drafts(self,mode,identifier,report_id):
        item=self.subject(mode,identifier)
        report=self.reports.get(report_id,session_id=item["session_id"])
        self._binding(report,mode,item)
        with self.s.ws.connection() as c:
            ids=[r[0] for r in c.execute("SELECT id FROM diagnostic_request_drafts WHERE session_id=? ORDER BY rowid DESC",
                                        (item["session_id"],))]
        return [d for d in (self.reports.get_draft(i,session_id=item["session_id"]) for i in ids)
                if d.report_id==report_id]
