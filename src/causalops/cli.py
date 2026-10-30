from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path

import duckdb
import pandas as pd

from causalops.agent import CausalOpsAgent
from causalops.benchmarks import run_gold_standard_benchmarks
from causalops.cohorts import build_common_date_psm_cohort
from causalops.execution import execute_analysis
from causalops.evals import (
    rescore_deepseek_live_report,
    run_deepseek_live_evaluation,
    run_proposal_evaluation,
)
from causalops.identification import route_identification
from causalops.schemas import CausalSpec
from causalops.sql import validate_read_only_sql


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="causalops")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="Validate and display a CausalSpec JSON file.")
    inspect_parser.add_argument("path", type=Path)
    route_parser = subparsers.add_parser("route", help="Run identification gates and route a method.")
    route_parser.add_argument("path", type=Path)
    execute_parser = subparsers.add_parser("execute", help="Execute a gated estimator on a DuckDB table.")
    execute_parser.add_argument("--spec", type=Path, required=True)
    execute_parser.add_argument("--database", type=Path, required=True)
    execute_parser.add_argument("--table", required=True)
    execute_parser.add_argument("--output", type=Path, required=True)
    cohort_parser = subparsers.add_parser(
        "build-psm-cohort", help="Build a one-row-per-user baseline cohort with read-only SQL."
    )
    cohort_parser.add_argument("--database", type=Path, required=True)
    cohort_parser.add_argument("--table", required=True)
    cohort_parser.add_argument("--output", type=Path, required=True)
    cohort_parser.add_argument("--pre-days", type=int, default=28)
    cohort_parser.add_argument("--followup-days", type=int, default=28)
    agent_parser = subparsers.add_parser(
        "agent-run", help="Run the deterministic allowlisted Agent on a Parquet cohort."
    )
    agent_parser.add_argument("--spec", type=Path, required=True)
    agent_parser.add_argument("--input", type=Path, required=True)
    agent_parser.add_argument("--output", type=Path, required=True)
    benchmark_parser = subparsers.add_parser(
        "benchmark-all", help="Run A/B, CUPED, IPW and DoubleML gold-standard benchmarks."
    )
    benchmark_parser.add_argument("--output", type=Path, required=True)
    benchmark_parser.add_argument("--rows", type=int, default=900)
    benchmark_parser.add_argument("--seed", type=int, default=20261027)
    eval_parser = subparsers.add_parser(
        "eval-proposals", help="Run deterministic structured-proposal safety evaluations."
    )
    eval_parser.add_argument("--output", type=Path, required=True)
    live_eval_parser = subparsers.add_parser(
        "eval-deepseek-live",
        help="Run the opt-in paid DeepSeek proposal evaluation (requires an environment key).",
    )
    live_eval_parser.add_argument("--output", type=Path, required=True)
    live_eval_parser.add_argument("--limit", type=int, default=30)
    live_eval_parser.add_argument("--case-id", action="append", dest="case_ids")
    live_eval_parser.add_argument(
        "--model",
        choices=["deepseek-flash", "deepseek-v4-pro", "deepseek-v4.1-flash-1017"],
        default="deepseek-flash",
    )
    live_eval_parser.add_argument(
        "--i-understand-this-costs-money",
        action="store_true",
        dest="costs_acknowledged",
    )
    rescore_parser = subparsers.add_parser(
        "rescore-deepseek-report",
        help="Recompute stricter metrics in a saved live report without any API call.",
    )
    rescore_parser.add_argument("--path", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "inspect":
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        spec = CausalSpec.model_validate(payload)
        print(spec.model_dump_json(indent=2))
    elif args.command == "route":
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        spec = CausalSpec.model_validate(payload)
        print(route_identification(spec).model_dump_json(indent=2))
    elif args.command == "execute":
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.table):
            raise ValueError("Table name must be a simple SQL identifier")
        payload = json.loads(args.spec.read_text(encoding="utf-8"))
        spec = CausalSpec.model_validate(payload)
        sql = f'SELECT * FROM "{args.table}"'
        validated = validate_read_only_sql(sql, {args.table})
        with duckdb.connect(str(args.database.resolve()), read_only=True) as connection:
            frame = connection.execute(validated.normalized_sql).df()
        result = execute_analysis(frame, spec, args.output, source_sql=validated.normalized_sql)
        print(result.model_dump_json(indent=2))
    elif args.command == "build-psm-cohort":
        _, summary, _ = build_common_date_psm_cohort(
            args.database,
            args.table,
            args.output,
            pre_period_days=args.pre_days,
            followup_days=args.followup_days,
        )
        print(json.dumps(summary.to_dict(), indent=2))
    elif args.command == "agent-run":
        payload = json.loads(args.spec.read_text(encoding="utf-8"))
        spec = CausalSpec.model_validate(payload)
        frame = pd.read_parquet(args.input)
        result = CausalOpsAgent().run(frame, spec, args.output)
        print(
            json.dumps(
                {
                    "run_id": result.bundle.run_id,
                    "method": result.bundle.plan.selected_method.value,
                    "claim_level": result.bundle.claim_level.value,
                    "report_path": str(result.report_path),
                    "trace_path": str(result.trace_path),
                },
                indent=2,
            )
        )
    elif args.command == "benchmark-all":
        path = run_gold_standard_benchmarks(args.output, seed=args.seed, rows=args.rows)
        print(path)
    elif args.command == "eval-proposals":
        summary = run_proposal_evaluation(args.output)
        print(json.dumps({**asdict(summary), "report_path": str(summary.report_path)}, indent=2))
    elif args.command == "eval-deepseek-live":
        report = run_deepseek_live_evaluation(
            args.output,
            model=args.model,
            limit=args.limit,
            case_ids=args.case_ids,
            costs_acknowledged=args.costs_acknowledged,
        )
        print(report)
    elif args.command == "rescore-deepseek-report":
        print(rescore_deepseek_live_report(args.path))


if __name__ == "__main__":
    main()

