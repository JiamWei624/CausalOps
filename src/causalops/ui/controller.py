from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from causalops.agent import CausalOpsAgent, AgentRunResult, inspect_dataset
from causalops.identification import route_identification
from causalops.llm import (
    DatasetSchema,
    DeepSeekStructuredModelClient,
    SpecProposalResult,
    StructuredModelClient,
    propose_causal_spec,
)
from causalops.research import AnalysisRunRecord, ResearchRepository
from causalops.schemas import CausalSpec, IdentificationDecision


MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class WorkflowValidation:
    inspection: dict[str, object]
    decision: IdentificationDecision


@dataclass(frozen=True)
class VersionedWorkflowResult:
    agent_result: AgentRunResult
    run_record: AnalysisRunRecord


def dataset_schema_from_frame(
    frame: pd.DataFrame,
    *,
    allowed_source_tables: list[str] | None = None,
    sensitive_columns: list[str] | None = None,
) -> DatasetSchema:
    """Create the metadata-only contract that may be sent to a model.

    Values and sample rows are intentionally excluded.  This boundary is kept in
    the controller so the UI cannot accidentally serialize the full DataFrame.
    """

    return DatasetSchema(
        columns={str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        row_count=len(frame),
        allowed_source_tables=allowed_source_tables or [],
        sensitive_columns=sensitive_columns or [],
    )


def generate_ai_proposal(
    frame: pd.DataFrame,
    *,
    question: str,
    allowed_source_tables: list[str] | None = None,
    sensitive_columns: list[str] | None = None,
    client: StructuredModelClient | None = None,
) -> SpecProposalResult:
    """Generate a guarded proposal; it remains non-executable until review."""

    model_client = client or DeepSeekStructuredModelClient()
    return propose_causal_spec(
        model_client,
        question=question,
        dataset=dataset_schema_from_frame(
            frame,
            allowed_source_tables=allowed_source_tables,
            sensitive_columns=sensitive_columns,
        ),
    )


def load_uploaded_table(
    content: bytes | BinaryIO,
    filename: str,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> pd.DataFrame:
    payload = content if isinstance(content, bytes) else content.read()
    if len(payload) > max_bytes:
        raise ValueError(f"Upload exceeds the {max_bytes // (1024 * 1024)} MB application limit")
    suffix = Path(filename).suffix.lower()
    stream = BytesIO(payload)
    if suffix == ".csv":
        frame = pd.read_csv(stream)
    elif suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(stream)
    else:
        raise ValueError("Only CSV and Parquet uploads are supported")
    if frame.empty:
        raise ValueError("Uploaded table is empty")
    return frame


def validate_workflow(frame: pd.DataFrame, spec: CausalSpec) -> WorkflowValidation:
    return WorkflowValidation(
        inspection=inspect_dataset(frame, spec),
        decision=route_identification(spec),
    )


def run_workflow(
    frame: pd.DataFrame,
    spec: CausalSpec,
    output_dir: Path,
    *,
    source_description: str,
    data_kind: str = "unspecified",
    study_context: dict | None = None,
) -> AgentRunResult:
    return CausalOpsAgent().run(
        frame,
        spec,
        output_dir,
        source_sql=f"-- {source_description}",
        data_kind=data_kind,
        study_context=study_context,
    )


def run_versioned_workflow(
    frame: pd.DataFrame,
    repository: ResearchRepository,
    *,
    session_id: str,
    revision_id: str,
    output_dir: Path,
    source_description: str,
    data_kind: str = "unspecified",
    study_context: dict | None = None,
) -> VersionedWorkflowResult:
    """Execute only the exact approved revision and persist its immutable binding."""

    session = repository.get_session(session_id)
    revision = repository.get_revision(revision_id)
    repository.assert_execution_authorized(
        session_id=session_id,
        revision_id=revision_id,
        dataset_version_id=session.current_dataset_version_id,
    )
    result = run_workflow(
        frame,
        revision.spec,
        output_dir,
        source_description=source_description,
        data_kind=data_kind,
        study_context=study_context,
    )
    evidence_path = result.report_path.parent.parent / "evidence" / f"run-{result.bundle.run_id}.json"
    record = repository.bind_analysis_run(
        session_id=session_id,
        revision_id=revision_id,
        dataset_version_id=session.current_dataset_version_id,
        run_id=result.bundle.run_id,
        result_bundle_path=str(evidence_path),
        report_path=str(result.report_path),
    )
    return VersionedWorkflowResult(agent_result=result, run_record=record)


def run_versioned_association_workflow(
    frame: pd.DataFrame, repository: ResearchRepository, *, session_id: str,
    revision_id: str, output_dir: Path, source_description: str,
    data_kind: str = 'user_provided',
    study_context: dict | None = None,
) -> VersionedWorkflowResult:
    revision = repository.get_revision(revision_id)
    repository.assert_association_execution_authorized(session_id=session_id, revision_id=revision_id,
                                                       dataset_version_id=revision.dataset_version_id)
    result = CausalOpsAgent().run(frame,revision.spec,output_dir,source_sql=source_description,
                                  data_kind=data_kind,execution_scope='association_only',study_context=study_context)
    path=result.report_path.parent.parent/'evidence'/f'run-{result.bundle.run_id}.json'
    record=repository.bind_analysis_run(session_id=session_id,revision_id=revision_id,
        dataset_version_id=revision.dataset_version_id,run_id=result.bundle.run_id,
        result_bundle_path=str(path),report_path=str(result.report_path),execution_scope='association_only')
    return VersionedWorkflowResult(agent_result=result,run_record=record)
