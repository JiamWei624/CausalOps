"""Evidence contract checks. Do not open holdout tasks or answers."""
import importlib.util
import sys
from pathlib import Path
import pytest


@pytest.fixture
def suite(monkeypatch):
    folder=Path(__file__).resolve().parents[1]/"scripts"/"eval_v23"
    monkeypatch.syspath_prepend(str(folder))
    import validate, score
    return validate,score


def test_split_oracles_and_receipt(suite):
    validation,_=suite
    record=validation.validate()
    assert record["development"]==30 and record["holdout_receipt"]==20 and len(record["pilot"])==10
    assert record["lab_min"]==2 and 2<record["lab_mean"]<4


def test_approval_precedes_execution(suite):
    _,scoring=suite
    run={"plan_id":"v2","plan_sha":"p","data":"d"}
    receipt={"plan_id":"v2","plan_sha":"p","data":{"frame_sha":"d"},"flow_id":"f","approved_at":"2026-11-05T10:01"}
    flow={"id":"f","events":[{"node":"execute_plan","status":"started","created":"2026-11-05T10:02"}]}
    assert scoring.approved(run,[flow],[receipt])
    assert not scoring.approved(run,[flow],[dict(receipt,plan_sha="old")])
    assert not scoring.approved(run,[flow],[dict(receipt,approved_at="2026-11-05T10:03")])


def test_worker_isolated_from_scoring():
    folder=Path(__file__).resolve().parents[1]/"scripts"/"eval_v23"
    source=(folder/"run_pilot.py").read_text(encoding="utf8")
    assert "development_rubrics" not in source and "holdout" not in source
