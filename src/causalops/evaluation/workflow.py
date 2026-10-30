from __future__ import annotations
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
import json,time
from causalops.agent import AgentRunResult,ToolTrace,inspect_dataset
from causalops.execution import execute_analysis
from causalops.identification import route_identification
from causalops.reporting import write_html_report,write_markdown_report
from causalops.schemas import GateStatus
from causalops.research import ResearchRepository,RevisionSource,DraftStatus
from causalops.ui.controller import run_versioned_workflow,run_versioned_association_workflow
from causalops.results.qa import ResultQAService


def prepare_task_session(repo,task,actor='automated_acceptance_fixture_not_human_research_approval'):
    session=repo.create_session(title='Task '+task.task_id,dataset_fingerprint=task.data_sha256,row_count=len(task.frame),
                               column_schema={c:str(t) for c,t in task.frame.dtypes.items()})
    rev=repo.create_revision(session.session_id,task.spec,source=RevisionSource.SYSTEM_INITIAL,
                            change_reason='固定验收任务设计；审批性质见actor',activate=True,status=DraftStatus.PENDING_REVIEW)
    if task.scope=='association_only':repo.authorize_association_analysis(rev.revision_id,authorized_by=actor,authorization_note='用户已授权本地固定任务验收；仅运行条件关联，不确认任何因果识别假设。')
    else:repo.approve_revision(rev.revision_id,approved_by=actor,checklist={'variables':True,'covariates':True,'assumptions':True})
    return session,rev


def run_reference_script(frame,spec,output_dir,*,source_sql,data_kind,execution_scope,study_context):
    """Expert prewritten script baseline: same gates, reports, evidence and trace as Agent."""
    trace=[]
    def step(name,fn,summary,**kwargs):
        started=datetime.now(timezone.utc);value=fn(**kwargs);completed=datetime.now(timezone.utc)
        trace.append(ToolTrace(name,'success',started.isoformat(),completed.isoformat(),summary(value)));return value
    inspection=step('inspect_dataset',inspect_dataset,lambda x:x,frame=frame,spec=spec)
    if inspection['missing_required_columns']:raise ValueError('Missing required columns')
    decision=step('route_identification',route_identification,lambda x:{'status':x.status.value,'selected_method':x.selected_method.value,'claim_ceiling':x.claim_ceiling.value},spec=spec)
    association=execution_scope=='association_only' and decision.selected_method.value=='regression_adjustment' and decision.status!=GateStatus.BLOCKED
    if decision.status!=GateStatus.PASS and not association:raise ValueError('Identification gate did not pass')
    bundle=step('execute_analysis',execute_analysis,lambda x:{'run_id':x.run_id,'method':x.plan.selected_method.value,'claim_level':x.claim_level.value},
                frame=frame,spec=spec,output_dir=output_dir/'evidence',source_sql=source_sql,data_kind=data_kind,execution_scope=execution_scope,study_context=study_context)
    md=step('write_markdown_report',write_markdown_report,lambda p:{'report_path':str(p)},bundle=bundle,output_dir=output_dir/'reports')
    html=step('write_html_report',write_html_report,lambda p:{'html_report_path':str(p)},bundle=bundle,output_dir=output_dir/'reports')
    p=output_dir/'traces'/f'agent-run-{bundle.run_id}.json';p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps({'run_id':bundle.run_id,'agent_type':'prewritten_reference_script','allowlisted_tools':[x.tool for x in trace],
                 'steps':[asdict(x) for x in trace]},ensure_ascii=False,indent=2),encoding='utf-8')
    return AgentRunResult(bundle=bundle,report_path=md,html_report_path=html,trace_path=p)


def run_complete_task(task,repo,session,rev,output_dir,condition):
    """Timed scope: authorization, execution, report/evidence/trace, local Q&A, reopen."""
    if condition not in {'script','agent'}:raise ValueError('Unknown condition')
    phase={};start=time.perf_counter()
    if condition=='agent':
        if task.scope=='association_only':
            wrapped=run_versioned_association_workflow(task.frame,repo,session_id=session.session_id,revision_id=rev.revision_id,output_dir=output_dir,
                  source_description=task.source,data_kind=task.kind,study_context=task.context)
        else:
            wrapped=run_versioned_workflow(task.frame,repo,session_id=session.session_id,revision_id=rev.revision_id,output_dir=output_dir,
                  source_description=task.source,data_kind=task.kind,study_context=task.context)
        result=wrapped.agent_result;record=wrapped.run_record
    else:
        if task.scope=='association_only':
            actual_rev=repo.get_revision(rev.revision_id)
            repo.assert_association_execution_authorized(session_id=session.session_id,revision_id=rev.revision_id,dataset_version_id=actual_rev.dataset_version_id)
        else:
            actual_session=repo.get_session(session.session_id);actual_rev=repo.get_revision(rev.revision_id)
            repo.assert_execution_authorized(session_id=session.session_id,revision_id=rev.revision_id,dataset_version_id=actual_session.current_dataset_version_id)
        result=run_reference_script(task.frame,actual_rev.spec,output_dir,source_sql=task.source if task.scope=='association_only' else '-- '+task.source,
                   data_kind=task.kind,execution_scope=task.scope,study_context=task.context)
        p=output_dir/'evidence'/f'run-{result.bundle.run_id}.json'
        record=repo.bind_analysis_run(session_id=session.session_id,revision_id=rev.revision_id,dataset_version_id=actual_rev.dataset_version_id,
                    run_id=result.bundle.run_id,result_bundle_path=str(p),report_path=str(result.report_path),execution_scope=task.scope)
    phase['analysis_reports_and_binding_seconds']=time.perf_counter()-start
    begin=time.perf_counter()
    question='请解释基线、绝对变化、实际含义和行动建议。'
    turn=ResultQAService(repo).ask(session_id=session.session_id,run_id=record.run_id,question=question,origin='acceptance_test')
    phase['local_qa_seconds']=time.perf_counter()-begin;begin=time.perf_counter()
    restored=ResearchRepository(repo.database_path);readback=restored.get_analysis_run(record.run_id)
    history=restored.list_result_qa_turns(run_id=record.run_id,snapshot_id=turn['snapshot_id'])
    phase['reopen_seconds']=time.perf_counter()-begin
    assert readback.revision_id==rev.revision_id and any(x['turn_id']==turn['turn_id'] for x in history)
    return result,record,turn,phase