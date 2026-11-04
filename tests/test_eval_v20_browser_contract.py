"""Regression tests for the evaluator; no browser task or answer is imported from a sealed workspace."""
import importlib.util
from pathlib import Path

import pytest


def module(name, relative):
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'eval_v20' / relative
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_actor_only_allows_explicit_review_tasks():
    actor = module('pilot_public_actor', 'actor/policy.py')
    tasks = actor.load_tasks()
    assert set(tasks) == {f'B{i:02d}' for i in range(1, 7)}
    assert {key for key, value in tasks.items() if value['allow_approval']} == {'B05', 'B06'}
    assert all('answer' not in task and 'gold' not in task for task in tasks.values())


def test_no_response_from_repeated_prompt():
    actor = module('pilot_page_actor', 'actor/policy.py')
    task = actor.load_tasks()['B04']
    question = task['prompt']
    obs = {'reply': question, 'text': question, 'controls': []}
    history = [{'submitted': True, 'value': question}]
    assert not actor._visible_response(task, obs, history)


def test_controller_refuses_overwrite_and_parent_escape(tmp_path, monkeypatch):
    common = module('pilot_controller_io', 'controller/common.py')
    monkeypatch.setattr(common, 'ROOT', tmp_path.resolve())
    output = tmp_path / 'attempt.json'
    common.save(output, {'first': True})
    with pytest.raises(FileExistsError):
        common.save(output, {'first': False})
    with pytest.raises(ValueError):
        common.bounded(tmp_path.parent / 'unrelated')
    assert common.read(output) == {'first': True}
