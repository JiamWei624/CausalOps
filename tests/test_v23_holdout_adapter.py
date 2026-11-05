"""Transport-only checks on invented records. Never load sealed tasks or gold files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/eval_v23"
sys.path.insert(0, str(SCRIPTS))
import holdout_adapter as adapter


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def invented(tmp_path, *, logical=False, native=None, multiple=False):
    folder = tmp_path / "inputs"
    folder.mkdir()
    name = "example.csv"
    data = ("activated_7d\n1\n0\n1\n0\n" if logical else "value\n2\n4\n6\n")
    (folder / name).write_text(data, encoding="utf8")
    names = [name]
    if logical:
        put(folder / "plan_1.json", {"id": "fixture-proposal", "revision": 1,
                                    "metric": "seven-day activation", "scope": "all channels",
                                    "data_sha256": adapter.sha(folder / name)})
        put(folder / "history.json", [
            {"event": "proposed", "plan": "plan_1.json"},
            {"event": "approved", "actor": "fictional-operator",
             "role": "authorized_approver", "plan_sha256": adapter.sha(folder / "plan_1.json")},
        ])
        names.extend(["plan_1.json", "history.json"])
    if native:
        put(folder / "native_replay.json", native)
        names.append("native_replay.json")
    if multiple:
        (folder / "second.csv").write_text("other\n8\n", encoding="utf8")
        names.append("second.csv")
    task = {"id": "Fictional01", "scenario": "Invented adapter test",
            "request": "只核对现有方案状态，禁止执行。",
            "operator_initial_state": "Invented authorized test operator",
            "snapshot_files": names,
            "data_source": {"origin": "Invented tests", "data_dictionary": "一行一次测量。"},
            "interaction": {"operator_messages": ["只核对现有方案状态，禁止执行。"]}}
    put(folder / "task.json", task)
    return folder


def run_local(monkeypatch, folder, tmp_path):
    output = tmp_path / "observed"
    output.mkdir()
    monkeypatch.setenv("CAUSALOPS_HOME", str(output / "workspace"))
    adapter.worker(folder, output, "local")
    return adapter.read(output / "observation.json")


def test_traversal_rejected_before_product(tmp_path):
    folder = invented(tmp_path)
    task = adapter.read(folder / "task.json")
    task["snapshot_files"].append("../answer.json")
    put(folder / "task.json", task)
    with pytest.raises(ValueError, match="simple file"):
        adapter.case_files(folder)


def test_unlisted_material_rejected(tmp_path):
    folder = invented(tmp_path)
    (folder / "answer.json").write_text("{}", encoding="utf8")
    with pytest.raises(ValueError, match="Unlisted"):
        adapter.capabilities(folder)


def test_multiple_bindings_recorded_without_product(monkeypatch, tmp_path):
    folder = invented(tmp_path, multiple=True)
    observation = run_local(monkeypatch, folder, tmp_path)
    assert observation["execution_status"] == "not_executed_infrastructure_limited"
    assert observation["product_invoked"] is False
    assert not observation["flows"] and not observation["runs"]
    assert not (tmp_path / "observed/workspace").exists()


def test_logical_bridge_validates_input_binding(tmp_path):
    folder = invented(tmp_path, logical=True)
    assert adapter.capabilities(folder)["supported"]
    plan = adapter.read(folder / "plan_1.json")
    plan["data_sha256"] = "0" * 64
    put(folder / "plan_1.json", plan)
    with pytest.raises(ValueError, match="approval digest"):
        adapter.capabilities(folder)


def test_unexpressible_history_is_not_fabricated(tmp_path):
    folder = invented(tmp_path, logical=True)
    plan = adapter.read(folder / "plan_1.json")
    plan["metric"] = "median of weighted subgroup estimates"
    put(folder / "plan_1.json", plan)
    result = adapter.capabilities(folder)
    assert not result["supported"]
    assert "external_logical_history_has_no_native_import_api" in result["limitations"]


def test_real_binary_plan_and_approval_replayed(monkeypatch, tmp_path):
    folder = invented(tmp_path, logical=True)
    observation = run_local(monkeypatch, folder, tmp_path)
    assert observation["product_invoked"]
    assert not observation.get("infrastructure_limitations")
    assert len(observation["approvals"]) == 1
    assert observation["before_runs"] == [] and observation["runs"] == []
    receipt = observation["approvals"][0]
    original = next(f for f in observation["flows"] if f["id"] in observation["setup_flows"])
    assert receipt["plan_id"] == original["plan"]
    assert receipt["plan_sha"] == original["plan_sha"]
    assert receipt["data"]["frame_sha"] == original["data"]
    assert any(e["node"] == "review" and e["status"] == "approved" for e in original["events"])
    assert observation["operator"][0]["input"]["action"] == "native_plan"
    assert observation["state_mapping"]["source_actor"] == "fictional-operator"
    assert observation["target"] not in observation["setup_flows"]


def native_history():
    config = {"question": "数据质量、分布及可分析字段体检", "method": "descriptive",
              "numeric": ["value"], "categorical": []}
    return {"schema": "causalops-native-replay-1",
            "contract": {"outcome": "value", "metric_unit": "件", "analysis_unit": "一次测量"},
            "steps": [{"action": "start", "id": "fictional-first", "question": "生成 value 的描述统计分布方案。"},
                      {"action": "review", "id": "fictional-review", "flow": "fictional-first",
                       "expected_configs": [config], "actor": "fictional-operator",
                       "actor_role": "authorized_approver", "accept": True, "dispatch": True}]}


def test_real_completed_history_and_multiturn(monkeypatch, tmp_path):
    folder = invented(tmp_path, native=native_history())
    task = adapter.read(folder / "task.json")
    task["interaction"]["operator_messages"] = [
        "解释已保存报告中 value 的均值、单位和运行来源，不要重新计算。",
        "当前报告结果还能说明什么限制？不要新建方案。",
    ]
    put(folder / "task.json", task)
    observation = run_local(monkeypatch, folder, tmp_path)
    assert not observation.get("infrastructure_limitations")
    assert len(observation["before_runs"]) == len(observation["runs"]) == 1
    assert len(observation["flows"]) == 3
    assert len([x for x in observation["operator"] if x["phase"] == "current"]) == 2
    assert observation["runs"][0]["run_id"] in observation["before_runs"]
    assert observation["runs"][0]["contract"]["data_fingerprint"]
    assert all(f["events"] for f in observation["flows"])


def test_approval_mismatch_never_executes(monkeypatch, tmp_path):
    replay = native_history()
    replay["steps"][1]["expected_configs"][0]["numeric"] = ["imaginary"]
    folder = invented(tmp_path, native=replay)
    observation = run_local(monkeypatch, folder, tmp_path)
    assert observation["execution_status"] == "setup_infrastructure_limited"
    assert not observation["approvals"] and not observation["runs"]
    assert observation["target"] is None


def test_unprivileged_setup_actor_cannot_approve(monkeypatch, tmp_path):
    replay = native_history()
    replay["steps"][1]["actor_role"] = "reader"
    folder = invented(tmp_path, native=replay)
    observation = run_local(monkeypatch, folder, tmp_path)
    assert observation.get("infrastructure_limitations")
    assert not observation["approvals"] and not observation["runs"]


def test_minimal_contract_does_not_infer_roles(tmp_path):
    task = adapter.read(invented(tmp_path) / "task.json")
    contract = adapter.minimal_contract(task)
    assert set(contract) == {"research", "notes"}
    assert contract["research"]["population"] == task["data_source"]["data_dictionary"]


def test_infrastructure_score_has_no_product_label(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    put(evidence / "status.json", {"status": "基础设施限制"})
    put(evidence / "observation.json",
        {"id": "Fictional01", "mode": "local", "product_invoked": False,
         "execution_status": "not_executed_infrastructure_limited",
         "infrastructure_limitations": ["fictional limitation"]})
    target = tmp_path / "score.json"
    adapter.score(tmp_path / "no_reference", tmp_path / "no_annotation", evidence, None, target)
    result = adapter.read(target)
    assert result["label"] is None and result["machine"] is None and result["v23_2_1"] is None


def test_frozen_scorer_is_the_expected_version():
    assert adapter.sha(SCRIPTS / "calibrate.py") == adapter.SCORER_SHA


def test_native_history_does_not_use_mock_results(monkeypatch, tmp_path):
    folder = invented(tmp_path, native=native_history())
    observation = run_local(monkeypatch, folder, tmp_path)
    from causalops.assistant.service import AssistantWorkspace
    from causalops.general.service import GeneralWorkspace
    w = AssistantWorkspace(GeneralWorkspace(tmp_path / "observed/workspace"))
    run = observation["runs"][0]
    result = w.ex.load(run["run_id"])
    assert result["summary"]["numeric"][0]["mean"] == 4
    assert result["summary"]["numeric"][0]["finite_n"] == 3
    assert run["contract"]["result_fingerprint"]


def test_create_task_error_preserves_observation(monkeypatch, tmp_path):
    from causalops.application.research_service import ResearchService

    def fail(*args, **kwargs):
        raise ValueError("invented startup failure")

    monkeypatch.setattr(ResearchService, "create_task", fail)
    observation = run_local(monkeypatch, invented(tmp_path), tmp_path)
    assert observation["execution_status"] == "product_startup_error"
    assert observation["errors"] == ["create_task:ValueError"]
    assert observation["product_invoked"] is True
    assert observation["target"] is None


def test_cli_installs_access_audit_before_input_reads(tmp_path):
    import os
    import subprocess
    folder = invented(tmp_path)
    output = tmp_path / "child-output"
    output.mkdir()
    env = dict(os.environ, CAUSALOPS_HOME=str(output / "workspace"), PYTHONDONTWRITEBYTECODE="1")
    env.pop("DEEPSEEK_API_KEY", None)
    result = subprocess.run([sys.executable, str(SCRIPTS / "holdout_adapter.py"), "worker",
                             str(folder), str(output), "local"], env=env, capture_output=True,
                            text=True, encoding="utf8", timeout=120)
    assert result.returncode == 0, result.stderr
    audit = adapter.read(output / "access_manifest.json")
    assert audit["input_read_sha256"]["task.json"] == adapter.sha(folder / "task.json")
    assert audit["input_read_sha256"]["example.csv"] == adapter.sha(folder / "example.csv")
    assert not audit["denied_paths"]
    assert audit["private_or_reference_reads_allowed"] is False


def test_access_audit_blocks_private_and_sibling_case(tmp_path):
    folder = invented(tmp_path)
    output = tmp_path / "audit-output"
    output.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    secret = private / "dummy.json"
    secret.write_text("{}", encoding="utf8")
    sibling = tmp_path / "another-input"
    sibling.mkdir()
    sibling_file = sibling / "task.json"
    sibling_file.write_text("{}", encoding="utf8")
    audit = adapter.AccessAudit(folder, output)
    try:
        with pytest.raises(PermissionError):
            secret.read_text(encoding="utf8")
        with pytest.raises(PermissionError):
            sibling_file.read_text(encoding="utf8")
    finally:
        audit.finish()
    report = adapter.read(output / "access_manifest.json")
    assert len(report["denied_paths"]) == 2
