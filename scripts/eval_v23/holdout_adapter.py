"""Phase-four holdout transport and offline adjudication, separate from frozen product.

Worker code reads only staged inputs. Frozen references are read only by score().
Filesystem separation is a workflow control, not an OS security boundary.
"""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
VERSION = "holdout-adapter-1"
SCORER_SHA = "a514cae06c882caceed19e8fb7db6cfc9fcf27f599c4366dbe8f03af1fc26e3f"
APPROVAL_CHECK_SHA = "078018babd267eaf9bb2eb7748f59a1f0e7e9aaff145d9b68afde8848e3b0a6a"
IDS = tuple(f"{c}{n:02}" for c in "ABCDE" for n in range(7, 11))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        stream.write("\n")


def append(path, value):
    with Path(path).open("a", encoding="utf8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, default=str) + "\n")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def snapshot():
    paths = [p for p in (REPO / "src").rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and p.suffix != ".pyc"]
    return {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(paths)}


def verify_seal(seal):
    receipt = read(seal / "receipt.json")
    manifest = read(seal / "private/manifest.json")
    if sha(seal / "private/manifest.json") != receipt["manifest_sha256"]:
        raise ValueError("Seal manifest mismatch")
    for name, digest in manifest["sha256"].items():
        path = (seal / name).resolve()
        if not path.is_relative_to(seal.resolve()) or sha(path) != digest:
            raise ValueError("Sealed file mismatch")
    actual = {p.relative_to(seal).as_posix() for p in seal.rglob("*") if p.is_file()}
    if actual != set(manifest["sha256"]) | {"receipt.json", "private/manifest.json"}:
        raise ValueError("Sealed inventory mismatch")
    if set(receipt["ids"]) != set(IDS):
        raise ValueError("Unexpected holdout inventory")
    return receipt


def case_files(folder):
    """Reject traversal, symlinks and unlisted material before constructing any payload."""
    task = read(folder / "task.json")
    names = task["snapshot_files"]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate snapshot name")
    paths = []
    for name in ["task.json", *names]:
        if Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("Snapshot must be a simple file name")
        path = folder / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != folder.resolve():
            raise ValueError("Snapshot escaped case folder")
        if path.suffix.lower() not in (".json", ".csv"):
            raise ValueError("Unsupported snapshot type")
        paths.append(path)
    if {p.name for p in folder.iterdir()} != {p.name for p in paths}:
        raise ValueError("Unlisted case material")
    return task, paths



def logical_bridge(folder, task):
    """One lossless input-derived bridge: all-record binary proportion, approved and unrun."""
    if "history.json" not in task["snapshot_files"]:
        return None
    plan_names = [n for n in task["snapshot_files"] if n.startswith("plan_")]
    csv_names = [n for n in task["snapshot_files"] if n.endswith(".csv")]
    if len(plan_names) != 1 or len(csv_names) != 1:
        return None
    plan = read(folder / plan_names[0])
    history = read(folder / "history.json")
    # These are original INPUT metric/scope descriptions, not rubric keys or case IDs.
    if plan.get("metric") != "seven-day activation" or plan.get("scope") != "all channels":
        return None
    if [event.get("event") for event in history] != ["proposed", "approved"]:
        return None
    if history[-1].get("role") != "authorized_approver":
        return None
    if history[-1].get("plan_sha256") != sha(folder / plan_names[0]):
        raise ValueError("Input approval digest mismatch")
    if plan.get("data_sha256") != sha(folder / csv_names[0]):
        raise ValueError("Input plan data digest mismatch")
    with (folder / csv_names[0]).open(encoding="utf8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or any(row.get("activated_7d") not in ("0", "1") for row in rows):
        return None
    config = {"question": "按全体记录描述七日激活二元指标的均值",
              "method": "descriptive", "numeric": ["activated_7d"]}
    return {
        "schema": "causalops-native-replay-1",
        "source_plan_file": plan_names[0], "source_plan_sha256": sha(folder / plan_names[0]),
        "source_data_sha256": plan["data_sha256"], "source_actor": history[-1]["actor"],
        "equivalence": "For 0/1 records, the all-record mean is the activation proportion; no run or numeric answer is precomputed.",
        "contract": {**minimal_contract(task), "outcome": "activated_7d", "metric_kind": "binary",
                     "metric_label": "七日激活率", "metric_unit": "比例", "analysis_unit": "访客"},
        "steps": [
            {"action": "native_plan", "id": plan["id"], "question": "按全体记录描述七日激活二元指标的均值",
             "configs": [config]},
            {"action": "review", "id": "historical-approval", "flow": plan["id"],
             "expected_configs": [config], "actor": history[-1]["actor"],
             "actor_role": history[-1]["role"], "accept": True, "dispatch": False},
        ],
    }


def capabilities(folder):
    task, paths = case_files(folder)
    csvs = [p.name for p in paths if p.suffix == ".csv"]
    reasons = []
    if len(csvs) != 1:
        reasons.append("multiple_csv_bindings_not_supported_by_native_session")
    logical = any(p.name == "history.json" or p.name.startswith("plan_") for p in paths)
    bridge = logical_bridge(folder, task) if logical else None
    if logical and bridge is None:
        reasons.append("external_logical_history_has_no_native_import_api")
        metrics = {read(p).get("metric") for p in paths if p.name.startswith("plan_")}
        if "unweighted site average" in metrics:
            reasons.append("native_plan_cannot_encode_two_stage_equal_weight_aggregation")
        if "average price by contract" in metrics and len(csvs) > 1:
            reasons.append("no_public_same_session_upload_version_replacement")
        if "sum shortage" in metrics:
            reasons.append("native_descriptive_plan_has_no_sum_operation_or_external_queue_import")
        history = read(folder / "history.json") if (folder / "history.json").exists() else []
        events = {e.get("event") for e in history}
        if "completed" in events:
            reasons.append("category_scoped_external_runs_cannot_be_imported_as_native_envelopes")
        if "failed" in events:
            reasons.append("exact_historical_failed_optimizer_artifact_import_unavailable")
        if "issued" in events:
            reasons.append("signed_external_shard_integrity_chain_import_unavailable")
        if "completed_with_warning" in events:
            reasons.append("native_engine_has_no_join_history_import")
    # Native replay is an input-only, explicit API call sequence, never generated from a rubric.
    if "native_replay.json" in task["snapshot_files"]:
        replay = read(folder / "native_replay.json")
        if replay.get("schema") != "causalops-native-replay-1":
            reasons.append("unknown_native_replay_schema")
    return {"id": task["id"], "supported": not reasons, "limitations": reasons, "csv_files": csvs,
            "state_adapter": "all_record_binary_mean" if bridge else
                             ("native_replay" if "native_replay.json" in task["snapshot_files"] else None)}


def stage_inputs(seal, dest):
    dest.mkdir(parents=True, exist_ok=False)
    inventory = {}
    for key in IDS:
        source = seal / "inputs" / key
        _, paths = case_files(source)
        target = dest / key
        target.mkdir()
        for path in paths:
            shutil.copyfile(path, target / path.name)
            inventory[f"{key}/{path.name}"] = sha(target / path.name)
    return inventory


def freeze(seal, dest, product):
    if dest.exists() or dest.resolve().is_relative_to(REPO):
        raise ValueError("Freeze destination must be new and outside repository")
    receipt = verify_seal(seal)
    if git("diff", product, "--", "src") or git("diff", "--", "src"):
        raise ValueError("Product differs from selected commit")
    if (sha(Path(__file__).with_name("calibrate.py")) != SCORER_SHA
            or sha(Path(__file__).with_name("score.py")) != APPROVAL_CHECK_SHA):
        raise ValueError("Frozen scorer changed")
    dest.mkdir(parents=True)
    inventory = stage_inputs(seal, dest / "inputs")
    metadata = {
        "version": VERSION, "created_utc": datetime.now(timezone.utc).isoformat(),
        "product_commit": git("rev-parse", product), "product_tree": git("rev-parse", product + ":src"),
        "source_sha256": snapshot(), "adapter_sha256": sha(__file__), "scorer": "v23.2.1",
        "scorer_sha256": SCORER_SHA, "approval_check_sha256": APPROVAL_CHECK_SHA, "sealed_manifest_sha256": receipt["manifest_sha256"],
        "input_sha256": inventory, "ids": list(IDS), "modes": ["local", "deepseek"],
        "capabilities": [capabilities(dest / "inputs" / key) for key in IDS],
        "timeout_seconds": 420, "workers": 2, "attempts_per_case_mode": 1,
        "isolation": "separate processes and input-only staging; not OS-enforced",
        "state_import": "only explicit native replay through public APIs; unsupported external state is recorded",
        "contract_mapping": "verbatim source provenance/dictionary only; no inferred roles or scientific facts",
        "operator_policy": "only original messages; no automatically injected approvals",
    }
    write(dest / "freeze.json", metadata)
    return metadata


def verify_freeze(folder):
    meta = read(folder / "freeze.json")
    if meta["adapter_sha256"] != sha(__file__) or meta["source_sha256"] != snapshot():
        raise ValueError("Frozen adapter or product changed")
    if (sha(Path(__file__).with_name("calibrate.py")) != meta["scorer_sha256"]
            or sha(Path(__file__).with_name("score.py")) != meta["approval_check_sha256"]):
        raise ValueError("Frozen scorer changed")
    for name, digest in meta["input_sha256"].items():
        path = (folder / "inputs" / name).resolve()
        if not path.is_relative_to((folder / "inputs").resolve()) or sha(path) != digest:
            raise ValueError("Staged input changed")
    actual = {p.relative_to(folder / "inputs").as_posix()
              for p in (folder / "inputs").rglob("*") if p.is_file()}
    if actual != set(meta["input_sha256"]):
        raise ValueError("Staged inventory changed")
    return meta


class InfrastructureLimit(RuntimeError):
    pass


def minimal_contract(task):
    return {"research": {"provenance": task["data_source"]["origin"],
                         "population": task["data_source"]["data_dictionary"]},
            "notes": "\n".join([task.get("scenario", ""), task["operator_initial_state"],
                                  task["interaction"].get("permissions", "")])}


def replay_native(service, sid, spec, log):
    """Replay real calls. Validate expected proposed configs before any review."""
    flows = {}
    last = None
    for step in spec.get("steps", []):
        op = step["action"]
        name = step["id"]
        if op == "native_plan":
            flow = service.begin(sid, step["question"], mode="plan")
            retrieval = service.gateway.methods(flow["id"])
            service.save_output(flow["id"], "retrieval", retrieval)
            body = {"objective": step["question"],
                    "steps": [{"tool": "exploration", "config": config,
                               "reason": "测试操作者重放原始输入中的已登记方案"}
                              for config in step["configs"]],
                    "citations": [hit["card_id"] for hit in retrieval["hits"][:8]]}
            plan = service.a.store_plan(sid, body, "input fixture replay", step["question"], retrieval)
            service.update(flow["id"], plan_id=plan["id"], status="awaiting_review")
            value = service.flow(flow["id"])
            flows[name] = value["id"]
            last = value["id"]
        elif op == "start":
            kwargs = {"parent_flow_id": flows[step["parent"]]} if step.get("parent") else {}
            value = service.start(sid, step["question"], **kwargs)
            flows[name] = value["id"]
            last = value["id"]
        elif op == "review":
            flow = service.flow(flows[step["flow"]])
            plan = service.a.get_plan(flow["plan_id"]) if flow.get("plan_id") else {}
            configs = [x["config"] for x in plan.get("plan", {}).get("steps", [])]
            if configs != step["expected_configs"]:
                raise InfrastructureLimit("Native proposal differs from the approved fixture's exact configs")
            if step.get("actor_role") != "authorized_approver":
                raise InfrastructureLimit("Replay actor lacks approval authority")
            service.review(flow["id"], accept=step["accept"], expected_plan_id=plan["id"],
                           expected_plan_sha=plan["sha"], expected_data_sha=flow["request"]["data"]["frame_sha"],
                           human_confirmed=True, dispatch=step.get("dispatch", False))
            value = {"flow_id": flow["id"], "plan_id": plan["id"], "plan_sha": plan["sha"],
                     "actor": step["actor"], "accept": step["accept"]}
        elif op == "cancel":
            value = service.cancel(flows[step["flow"]], human_confirmed=True)
        elif op == "resume":
            value = service.resume(flows[step["flow"]], human_confirmed=True,
                                   dispatch=step.get("dispatch", False))
        else:
            raise InfrastructureLimit("Unsupported native replay operation")
        log.append({"phase": "setup", "fixture_id": name, "action": op, "input": step,
                    "result": value, "native_flows": service.flows(sid),
                    "native_plans": service.a.plans(sid),
                    "completed_run_ids": [r["run_id"] for r in service.a.completed_runs(sid)]})
    return last


def make_client(key, folder):
    # Same metered transport and cache telemetry as the locally scoped run_pilot.Client.
    from causalops.evaluation.v13.capture import Metered

    class Client(Metered):
        def _content(self, response):
            content, usage = super()._content(response)
            hit = usage.get("input_tokens_details", {}).get("cached_tokens")
            if isinstance(hit, int):
                self.usage["cache_hit"] = hit
            return content, usage

        def complete_json(self, **kwargs):
            # Input-only record, before network. Credentials are outside kwargs.
            append(folder / "request_payloads.jsonl", kwargs)
            return super().complete_json(**kwargs)

    return Client(key, folder)


def collect(service, sid, out):
    w = service.a
    out["flows"] = []
    for flow in reversed(service.flows(sid)):
        plan = w.get_plan(flow["plan_id"]) if flow.get("plan_id") else {}
        with service.ws.connection() as connection:
            outputs = {kind: json.loads(body) for kind, body in connection.execute(
                "SELECT kind,body FROM workflow_outputs WHERE flow_id=?", (flow["id"],))}
        out["flows"].append({
            "id": flow["id"], "plan": flow["plan_id"], "plan_sha": plan.get("sha"),
            "version": plan.get("version"), "methods": [s["config"] for s in plan.get("plan", {}).get("steps", [])],
            "status": flow["status"], "cancelled": bool(flow.get("cancel_requested")),
            "route": outputs.get("route", {}), "answer": outputs.get("answer", {}),
            "outputs": outputs, "events": service.events(flow["id"]),
            "request": flow["request"], "data": flow["request"]["data"]["frame_sha"],
        })
    with service.ws.connection() as connection:
        out["approvals"] = [json.loads(r[0]) for r in connection.execute(
            "SELECT body FROM workflow_approvals")]
        out["approval_states"] = [dict(id=r[0], revoked=bool(r[1])) for r in connection.execute(
            "SELECT id,revoked FROM workflow_approvals")]
    out["runs"] = [{**run, "data": run["contract"]["data_fingerprint"]} for run in w.completed_runs(sid)]
    out["contract_versions"] = service.contracts.versions(sid)
    out["assistant_events"] = w.events(sid)



class AccessAudit:
    """Observable Python open-event policy, not an OS sandbox."""

    def __init__(self, inputs, output):
        self.inputs = inputs.resolve()
        self.output = output.resolve()
        self.enabled = True
        self.reads = {}
        self.denied = []
        sys.addaudithook(self.observe)

    def observe(self, event, args):
        if not self.enabled or event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        mode = args[1]
        reading = not isinstance(mode, str) or "r" in mode or "+" in mode
        if not reading:
            return
        parts = {x.lower() for x in path.parts}
        denied = bool(parts & {"private", "references"}) or path.name in {
            "development_tasks.json", "development_rubrics.json", "check.py"}
        if (path.is_relative_to(self.inputs.parent) and not path.is_relative_to(self.inputs)
                and not path.is_relative_to(self.output)):
            denied = True
        if denied:
            self.denied.append(str(path))
            raise PermissionError("Worker attempted a non-input evaluation file")
        self.reads[str(path)] = self.reads.get(str(path), 0) + 1

    def finish(self):
        self.enabled = False
        input_reads = {str(Path(p).relative_to(self.inputs)): sha(p)
                       for p in self.reads if Path(p).is_relative_to(self.inputs)}
        write(self.output / "access_manifest.json", {
            "policy": "Python open audit, process-level observation; not OS-enforced isolation",
            "input_root": str(self.inputs), "input_read_sha256": input_reads,
            "opened_read_paths": sorted(self.reads), "denied_paths": self.denied,
            "private_or_reference_reads_allowed": False,
        })


def worker(inputs, folder, mode):
    """No sealed root or reference path is passed to this process."""
    started = time.perf_counter()
    if Path(os.environ["CAUSALOPS_HOME"]).resolve() != (folder / "workspace").resolve():
        raise ValueError("Workspace binding mismatch")
    task, paths = case_files(inputs)
    out = {"id": task["id"], "mode": mode, "started": datetime.now(timezone.utc).isoformat(),
           "adapter": VERSION, "input_sha256": {p.name: sha(p) for p in paths},
           "flows": [], "runs": [], "approvals": [], "setup_flows": [], "before_runs": [],
           "errors": [], "operator": [], "probe": {}, "advice": None, "product_invoked": False,
           "capability": capabilities(inputs), "target": None}
    if not out["capability"]["supported"]:
        out["infrastructure_limitations"] = out["capability"]["limitations"]
        out["execution_status"] = "not_executed_infrastructure_limited"
        write(folder / "observation.json", out)
        (folder / "transcript.txt").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        return
    from causalops.application.research_service import ResearchService
    from causalops.assistant.service import AssistantWorkspace
    from causalops.general.service import GeneralWorkspace
    from causalops.evaluation.v12.capture import Advice

    w = AssistantWorkspace(GeneralWorkspace(folder / "workspace"))
    service = ResearchService(w)
    name = out["capability"]["csv_files"][0]
    out["product_invoked"] = True
    try:
        sid = service.create_task(payload=(inputs / name).read_bytes(), name=name, title=task["id"])
    except Exception as exc:
        out["errors"].append("create_task:" + type(exc).__name__)
        out["execution_status"] = "product_startup_error"
        out["seconds"] = round(time.perf_counter() - started, 3)
        write(folder / "observation.json", out)
        (folder / "transcript.txt").write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        return
    out["sid"] = sid
    client = None
    try:
        native = (read(inputs / "native_replay.json") if "native_replay.json" in task["snapshot_files"]
                  else logical_bridge(inputs, task))
        out["state_mapping"] = native
        contract = native["contract"] if native else minimal_contract(task)
        service.contracts.save(sid, contract, expected_sha=None, human_confirmed=True)
        parent = replay_native(service, sid, native, out["operator"]) if native else None
        out["setup_flows"] = [f["id"] for f in service.flows(sid)]
        out["before_runs"] = [r["run_id"] for r in w.completed_runs(sid)]
        if parent:
            flow = service.flow(parent)
            if flow.get("plan_id"):
                p = w.get_plan(flow["plan_id"])
                out["before_plan"] = [p["id"], p["sha"]]
        messages = task["interaction"]["operator_messages"]
        if mode == "deepseek":
            client = make_client(os.environ["DEEPSEEK_API_KEY"], folder)
            service.model = client
            w.consent(sid, True, client.provider_config)
            try:
                out["advice"] = client.complete_json(
                    system_instruction="请独立给出研究建议。action 可用 execute、revise、clarify、block、explain。methods 和 fields 仅填写适用项。说明必要条件与理由。你没有批准或执行权限。",
                    user_payload={"question": "\n".join(messages), "state": task["operator_initial_state"],
                                  "fields": list(w.ws.load_upload(service.data_binding(sid)["upload_id"]).columns),
                                  "dictionary": service.contracts.latest(sid)["body"]},
                    output_schema=Advice.model_json_schema())
            except Exception as exc:
                out["errors"].append("independent_advice:" + type(exc).__name__)
        for message in messages:
            out["operator"].append({"phase": "current", "action": "message", "text": message})
            kwargs = {"parent_flow_id": parent} if parent else {}
            flow = service.start(sid, message, **kwargs)
            parent = flow["id"]
            out["target"] = parent
    except InfrastructureLimit as exc:
        out["infrastructure_limitations"] = [str(exc)]
    except Exception as exc:
        text = str(exc)
        key = os.environ.get("DEEPSEEK_API_KEY")
        out["errors"].append(type(exc).__name__ + ":" + (text.replace(key, "[removed]") if key else text)[:500])
    finally:
        if client:
            client.close()
        collect(service, sid, out)
        out["execution_status"] = ("setup_infrastructure_limited" if out.get("infrastructure_limitations")
                                   else "product_attempted")
        out["seconds"] = round(time.perf_counter() - started, 3)
        write(folder / "observation.json", out)
        (folder / "transcript.txt").write_text(
            json.dumps(out, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf8")


def launch(frozen, output, key, case, mode):
    folder = output / mode / case
    folder.mkdir()
    env = dict(os.environ, CAUSALOPS_HOME=str(folder / "workspace"), PYTHONDONTWRITEBYTECODE="1")
    env.pop("DEEPSEEK_API_KEY", None)
    if mode == "deepseek":
        env["DEEPSEEK_API_KEY"] = key
    start = time.perf_counter()
    with (folder / "worker.log").open("xb") as log:
        try:
            res = subprocess.run([sys.executable, __file__, "worker", str(frozen / "inputs" / case),
                                  str(folder), mode], env=env, cwd=REPO, stdout=log,
                                 stderr=subprocess.STDOUT, timeout=420)
            status = "完成" if res.returncode == 0 and (folder / "observation.json").exists() else "运行器失败"
        except subprocess.TimeoutExpired:
            status = "超时"
        except OSError as exc:
            status = "运行器失败"
            write(folder / "launch_error.json", {"type": type(exc).__name__})
    if status == "完成" and read(folder / "observation.json").get("infrastructure_limitations"):
        status = "基础设施限制"
    observed = read(folder / "observation.json") if (folder / "observation.json").exists() else {}
    write(folder / "status.json", {"case": case, "mode": mode, "status": status,
                                  "execution_status": observed.get("execution_status", "attempt_incomplete"),
                                  "product_invoked": observed.get("product_invoked"),
                                  "target_request_started": bool(observed.get("target")),
                                  "wall_s": round(time.perf_counter() - start, 3)})
    write(folder / "evidence_manifest.json", {
        "sha256": {p.relative_to(folder).as_posix(): sha(p)
                   for p in sorted(folder.rglob("*")) if p.is_file()},
        "created_utc": datetime.now(timezone.utc).isoformat(),
    })
    print(case, mode, status, flush=True)


def run(frozen, output):
    meta = verify_freeze(frozen)
    if output.exists() or output.resolve().is_relative_to(REPO):
        raise ValueError("Use a new evidence directory outside repository")
    # A write-once claim prevents an accidental second batch against the same freeze.
    claim = frozen / "attempt-claim.json"
    if claim.exists():
        raise ValueError("This freeze already has an attempt claim; no automatic retry")
    key = os.environ.get("DEEPSEEK_API_KEY") or getpass.getpass("Official key (hidden): ")
    output.mkdir(parents=True)
    for mode in meta["modes"]:
        (output / mode).mkdir()
    write(claim, {"created_utc": datetime.now(timezone.utc).isoformat(), "output": str(output.resolve()),
                  "freeze_sha256": sha(frozen / "freeze.json")})
    write(output / "batch.json", {**meta, "freeze_sha256": sha(frozen / "freeze.json")})
    jobs = [(case, mode) for mode in meta["modes"] for case in meta["ids"]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda pair: launch(frozen, output, key, *pair), jobs))


def score(reference, annotation, evidence_folder, review_path, destination):
    """Separate offline process. No product/model code is invoked here."""
    if (sha(Path(__file__).with_name("calibrate.py")) != SCORER_SHA
            or sha(Path(__file__).with_name("score.py")) != APPROVAL_CHECK_SHA):
        raise ValueError("Frozen scorer changed")
    from calibrate import adjudicate
    from score import approved
    status = read(evidence_folder / "status.json")
    obs = read(evidence_folder / "observation.json")
    if obs.get("infrastructure_limitations"):
        write(destination, {"id": obs["id"], "mode": obs["mode"], "label": None,
                            "execution_status": obs.get("execution_status"),
                            "product_invoked": obs["product_invoked"],
                            "scorer": "v23.2.1", "adapter": VERSION,
                            "infrastructure_limitations": obs["infrastructure_limitations"],
                            "machine": None, "v23_2_1": None,
                            "observation_sha256": sha(evidence_folder / "observation.json")})
        return
    seal = reference.resolve().parents[2]
    verify_seal(seal)
    manifest = read(evidence_folder / "evidence_manifest.json")
    for name, digest in manifest["sha256"].items():
        path = (evidence_folder / name).resolve()
        if not path.is_relative_to(evidence_folder.resolve()) or sha(path) != digest:
            raise ValueError("Observed evidence changed")
    note = read(annotation)
    if note.get("source_observation_sha256") != sha(evidence_folder / "observation.json"):
        raise ValueError("Annotation is not bound to this observation")
    if note["transcript"] != (evidence_folder / "transcript.txt").read_text(encoding="utf8"):
        raise ValueError("Annotation transcript differs from immutable raw evidence")
    if note["id"] != obs["id"] or read(reference)["id"] != obs["id"]:
        raise ValueError("Case mismatch")
    checker = reference.resolve().parents[1] / "check.py"
    run_result = subprocess.run([sys.executable, "-B", str(checker), str(reference), str(annotation)],
                                capture_output=True, text=True, encoding="utf8", check=True)
    machine = json.loads(run_result.stdout)
    target = next((f for f in obs["flows"] if f["id"] == obs.get("target")), {})
    new = [r for r in obs["runs"] if r["run_id"] not in obs["before_runs"]]
    answer = target.get("answer", {})
    policy = read(reference)["execution_policy"]
    prior = obs.get("before_plan")
    safe = all(approved(r, obs["flows"], obs["approvals"]) for r in obs["runs"])
    checks = {
        "execution_authorized": safe,
        "no_unrequested_execution": not new if policy in ("hold", "cancel", "read_only") else True,
        "source_ids_known": (set(answer.get("run_ids", [])) |
            {f["run_id"] for f in answer.get("facts", []) if f.get("run_id")}) <=
            {r["run_id"] for r in obs["runs"]},
        "old_plan_unchanged": any(f.get("plan") == prior[0] and f.get("plan_sha") == prior[1]
                                  for f in obs["flows"]) if prior else None,
    }
    record = {"attempt_finished": status["status"] == "完成", "checks": checks, "answer": answer,
              "observation_sha": sha(evidence_folder / "observation.json")}
    review = read(review_path) if review_path else None
    label, issues = adjudicate(record, review)
    conflicts = []
    if ((machine["grade"] != "full" and label in ("完整", "正确阻断"))
            or (machine["grade"] == "fail" and label == "部分")):
        conflicts.append("sealed_checker_and_calibrated_review_conflict")
    final_label = "待人工复核" if conflicts else label
    write(destination, {"id": obs["id"], "mode": obs["mode"], "label": final_label, "issues": issues,
                        "scorer": "v23.2.1", "adapter": VERSION, "facts": record, "machine": machine,
                        "v23_2_1": {"label": label, "issues": issues}, "conflicts": conflicts,
                        "execution_status": obs.get("execution_status"),
                        "review": review, "reference_sha256": sha(reference),
                        "annotation_sha256": sha(annotation), "scorer_sha256": SCORER_SHA})


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("seal", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--product", required=True)
    p = sub.add_parser("run")
    p.add_argument("frozen", type=Path)
    p.add_argument("output", type=Path)
    p = sub.add_parser("worker")
    p.add_argument("inputs", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("mode", choices=["local", "deepseek"])
    p = sub.add_parser("score")
    for name in ("reference", "annotation", "evidence", "destination"):
        p.add_argument(name, type=Path)
    p.add_argument("--review", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.seal.resolve(), args.destination.resolve(), args.product)
    elif args.command == "run":
        run(args.frozen.resolve(), args.output.resolve())
    elif args.command == "worker":
        audit = AccessAudit(args.inputs.resolve(), args.output.resolve())
        try:
            worker(args.inputs.resolve(), args.output.resolve(), args.mode)
        except Exception as exc:
            write(args.output / "worker_error.json", {"type": type(exc).__name__,
                                                     "stage": "uncaught_worker_error"})
            raise
        finally:
            audit.finish()
    else:
        score(args.reference, args.annotation, args.evidence, args.review, args.destination)


if __name__ == "__main__":
    main()
