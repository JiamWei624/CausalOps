import json

import httpx
import pytest

from causalops.application.research_service import ResearchService
from causalops.assistant.service import AssistantWorkspace
from causalops.evaluation.v13.capture import Metered
from causalops.general.service import GeneralWorkspace, DesignError
from causalops.llm.providers import OutputContractError, ProviderError

SCHEMA = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}


@pytest.mark.parametrize("first,expected,exception", [
    (503, 2, None), ("connect", 2, None), (401, 1, ProviderError),
    ("protocol", 1, ProviderError), ("malformed", 1, OutputContractError),
    ("persistent", 2, ProviderError),
])
def test_physical_attempts_bind_real_requests(tmp_path, first, expected, exception):
    received = []
    secret = "dummy-credential"
    def handle(req):
        received.append((req.headers["idempotency-key"], req.content))
        if len(received) == 1 or first == "persistent":
            if first in ("connect", "persistent"):
                raise httpx.ConnectError("injected", request=req)
            if first == "protocol":
                raise httpx.LocalProtocolError("injected", request=req)
            if isinstance(first, int):
                return httpx.Response(first, headers={"x-request-id": "failed-http"})
        text = "bad JSON" if first == "malformed" else '{"ok":true}'
        return httpx.Response(200, json={"id": "success-http", "status": "completed", "output_text": text,
                                          "usage": {"input_tokens": 3, "output_tokens": 2}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        model = Metered(secret, tmp_path, client=client, sleep=lambda _: None)
        def send():
            return model.complete_json(system_instruction="test", user_payload={"private": "sensitive-example"}, output_schema=SCHEMA)
        if exception:
            with pytest.raises(exception):
                send()
        else:
            assert send() == {"ok": True}
    def records(name):
        return [json.loads(line) for line in (tmp_path / name).read_text("utf-8").splitlines()]
    req, = records("requests.jsonl")
    result, = records("responses.jsonl")
    attempts = records("physical_attempts.jsonl")
    assert len(received) == expected and len(set(received)) == 1
    assert {v["call_id"] for v in [req, result, *attempts]} == {received[0][0]}
    assert {v["request_sha256"] for v in [req, result, *attempts]} == {req["request_sha256"]}
    assert [(v["attempt"], v["event"]) for v in attempts] == [
        (i, event) for i in range(1, expected+1) for event in ("started","finished")]
    assert [e["will_retry"] for e in attempts if e["event"] == "finished"] == [True]*(expected-1)+[False]
    assert result["telemetry"]["attempts"] == expected
    assert result["valid"] is (exception is None)
    if first == "malformed":
        assert attempts[-1]["status"] == "output_contract_error" and attempts[-1]["input_tokens"] == 3
    assert secret not in str(attempts) and "sensitive-example" not in str(attempts)


def test_conflicting_run_name_fails_before_model_or_flow(tmp_path):
    workspace = AssistantWorkspace(GeneralWorkspace(tmp_path))
    service = ResearchService(workspace)
    sid = service.create_task(payload=b"col,value\nx,1\ny,2\n", name="synthetic.csv", title="unit")
    wrong = "abcd" * 8
    with pytest.raises(DesignError, match="运行与当前选择不一致"):
        service.start(sid, f"解释 run_id: {wrong} 的运行结果。", run_ids=[])
    assert service.flows(sid) == []
    with pytest.raises(DesignError, match="运行与当前选择不一致"):
        workspace.ask(sid, f"解释 [[{wrong}:rows]] 的证据。")
