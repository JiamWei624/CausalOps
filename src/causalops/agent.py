from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from causalops.execution import execute_analysis
from causalops.identification import route_identification
from causalops.reporting import write_html_report, write_markdown_report
from causalops.schemas import CausalSpec, GateStatus, ResultBundle


@dataclass(frozen=True)
class ToolTrace:
    tool: str
    status: str
    started_at: str
    completed_at: str
    summary: dict[str, Any]


@dataclass(frozen=True)
class AgentRunResult:
    bundle: ResultBundle
    report_path: Path
    trace_path: Path
    html_report_path: Path | None = None


class ToolRegistry:
    """Explicit allowlist; arbitrary Python or shell execution is intentionally absent."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, function: Callable[..., Any]) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = function

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool is not allowlisted: {name}")
        return self._tools[name](**kwargs)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))


def inspect_dataset(frame: pd.DataFrame, spec: CausalSpec) -> dict[str, Any]:
    required = {
        spec.treatment,
        spec.outcome,
        *spec.covariates,
        *filter(None, [spec.entity_id_column, spec.time_column, spec.treatment_time_column]),
    }
    missing = sorted(required - set(frame.columns))
    return {
        "row_count": len(frame),
        "column_count": len(frame.columns),
        "missing_required_columns": missing,
        "required_column_null_counts": {
            column: int(frame[column].isna().sum()) for column in sorted(required & set(frame.columns))
        },
    }


class CausalOpsAgent:
    """Deterministic tool-using workflow; no LLM is required or implied."""

    def __init__(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register("inspect_dataset", inspect_dataset)
        self.registry.register("route_identification", route_identification)
        self.registry.register("execute_analysis", execute_analysis)
        self.registry.register("write_markdown_report", write_markdown_report)
        self.registry.register("write_html_report", write_html_report)

    def run(
        self,
        frame: pd.DataFrame,
        spec: CausalSpec,
        output_dir: Path,
        *,
        source_sql: str = "-- DataFrame supplied by caller; no SQL executed by CausalOps.",
        data_kind: str = "unspecified",
        execution_scope: str = "approved",
        study_context: dict | None = None,
    ) -> AgentRunResult:
        output_dir = output_dir.resolve()
        trace: list[ToolTrace] = []

        def invoke(name: str, summary_builder: Callable[[Any], dict[str, Any]], **kwargs: Any) -> Any:
            started = datetime.now(timezone.utc)
            try:
                result = self.registry.call(name, **kwargs)
            except Exception as exc:
                completed = datetime.now(timezone.utc)
                trace.append(
                    ToolTrace(
                        tool=name,
                        status="error",
                        started_at=started.isoformat(),
                        completed_at=completed.isoformat(),
                        summary={"error_type": type(exc).__name__, "message": str(exc)},
                    )
                )
                self._write_failed_trace(output_dir, trace)
                raise
            completed = datetime.now(timezone.utc)
            trace.append(
                ToolTrace(
                    tool=name,
                    status="success",
                    started_at=started.isoformat(),
                    completed_at=completed.isoformat(),
                    summary=summary_builder(result),
                )
            )
            return result

        inspection = invoke(
            "inspect_dataset",
            lambda value: value,
            frame=frame,
            spec=spec,
        )
        if inspection["missing_required_columns"]:
            now = datetime.now(timezone.utc).isoformat()
            trace.append(
                ToolTrace(
                    tool="validate_required_columns",
                    status="error",
                    started_at=now,
                    completed_at=now,
                    summary={"missing_required_columns": inspection["missing_required_columns"]},
                )
            )
            self._write_failed_trace(output_dir, trace)
            raise ValueError(f"Missing required columns: {inspection['missing_required_columns']}")
        decision = invoke(
            "route_identification",
            lambda value: {
                "status": value.status.value,
                "selected_method": value.selected_method.value,
                "claim_ceiling": value.claim_ceiling.value,
            },
            spec=spec,
        )
        association_only = execution_scope == "association_only" and decision.selected_method.value == 'regression_adjustment' and decision.status != GateStatus.BLOCKED
        if decision.status != GateStatus.PASS and not association_only:
            now = datetime.now(timezone.utc).isoformat()
            trace.append(
                ToolTrace(
                    tool="enforce_identification_gate",
                    status="error",
                    started_at=now,
                    completed_at=now,
                    summary={
                        "status": decision.status.value,
                        "required_actions": decision.required_actions,
                    },
                )
            )
            self._write_failed_trace(output_dir, trace)
            raise ValueError(f"Identification gate did not pass: {decision.required_actions}")
        bundle = invoke(
            "execute_analysis",
            lambda value: {
                "run_id": value.run_id,
                "method": value.plan.selected_method.value,
                "claim_level": value.claim_level.value,
            },
            frame=frame,
            spec=spec,
            output_dir=output_dir / "evidence",
            source_sql=source_sql,
            data_kind=data_kind,
            execution_scope=execution_scope,
            study_context=study_context,
        )
        report_path = invoke(
            "write_markdown_report",
            lambda value: {"report_path": str(value)},
            bundle=bundle,
            output_dir=output_dir / "reports",
        )
        html_report_path = invoke(
            "write_html_report", lambda value: {"html_report_path": str(value)},
            bundle=bundle, output_dir=output_dir / "reports",
        )
        trace_path = output_dir / "traces" / f"agent-run-{bundle.run_id}.json"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(
                {
                    "run_id": bundle.run_id,
                    "agent_type": "deterministic_allowlisted_tool_agent",
                    "allowlisted_tools": self.registry.names,
                    "steps": [asdict(step) for step in trace],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return AgentRunResult(bundle=bundle, report_path=report_path, trace_path=trace_path,
                              html_report_path=html_report_path)

    @staticmethod
    def _write_failed_trace(output_dir: Path, trace: list[ToolTrace]) -> None:
        target_dir = output_dir / "traces"
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        (target_dir / f"failed-agent-run-{timestamp}.json").write_text(
            json.dumps({"steps": [asdict(step) for step in trace]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
