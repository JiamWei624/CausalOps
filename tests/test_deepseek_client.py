from dataclasses import dataclass, field

import pytest

from causalops.llm import (
    DeepSeekConfigurationError,
    DeepSeekResponseError,
    DeepSeekStructuredModelClient,
)


@dataclass
class FakeInputDetails:
    cached_tokens: int = 7


@dataclass
class FakeUsage:
    input_tokens: int = 100
    input_tokens_details: FakeInputDetails = field(default_factory=FakeInputDetails)
    output_tokens: int = 50
    total_tokens: int = 150


class FakeResponse:
    def __init__(self, content: str | None, *, status: str = "completed") -> None:
        self.id = "response-test"
        self.model = "deepseek-flash"
        self.status = status
        self.output_text = content
        self.usage = FakeUsage()
        self.incomplete_details = None

    def model_dump(self):
        return {"output": []}


class FakeHTTPError(RuntimeError):
    def __init__(self, status_code: int, *, body=None) -> None:
        super().__init__("unsafe provider detail must not escape")
        self.status_code = status_code
        self.body = body


class FakeResponses:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes) -> None:
        self.responses = FakeResponses(outcomes)


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.message = FakeMessage(content)
        self.finish_reason = finish_reason


class FakeChatUsage:
    prompt_tokens = 120
    prompt_tokens_details = FakeInputDetails()
    completion_tokens = 40
    total_tokens = 160


class FakeChatResponse:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.id = "chat-test"
        self.model = "deepseek-v4.1-flash-1017"
        self.choices = [FakeChoice(content, finish_reason)]
        self.usage = FakeChatUsage()


class FakeChatCompletions:
    def __init__(self, response: FakeChatResponse) -> None:
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeChatNamespace:
    def __init__(self, response: FakeChatResponse) -> None:
        self.completions = FakeChatCompletions(response)


class FakeChatClient:
    def __init__(self, response: FakeChatResponse) -> None:
        self.chat = FakeChatNamespace(response)


def test_deepseek_client_uses_responses_json_schema_without_tools() -> None:
    fake = FakeClient([FakeResponse('{"question":"valid"}')])
    client = DeepSeekStructuredModelClient(client=fake, sleep=lambda _: None)
    result = client.complete_json(
        system_instruction="Return JSON.",
        user_payload={"research_question": "test"},
        output_schema={"type": "object"},
    )
    assert result == {"question": "valid"}
    request = fake.responses.calls[0]
    assert request["reasoning"] == {"effort": "none"}
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["max_output_tokens"] == 2048
    assert "tools" not in request
    assert client.last_telemetry["total_tokens"] == 150
    assert client.last_telemetry["attempts"] == 1


def test_deepseek_client_retries_429_with_bounded_backoff() -> None:
    sleeps = []
    fake = FakeClient([FakeHTTPError(429), FakeResponse("{}")])
    client = DeepSeekStructuredModelClient(client=fake, sleep=sleeps.append)
    assert client.complete_json(system_instruction="JSON", user_payload={}, output_schema={}) == {}
    assert sleeps == [1.0]
    assert len(fake.responses.calls) == 2


def test_responses_400_retries_once_with_json_object_and_local_schema() -> None:
    fake = FakeClient([FakeHTTPError(400), FakeResponse('{"answer_zh":"ok"}')])
    client = DeepSeekStructuredModelClient(client=fake, sleep=lambda _: None)
    schema = {
        "type": "object",
        "properties": {"answer_zh": {"type": "string"}},
        "required": ["answer_zh"],
        "additionalProperties": False,
    }
    result = client.complete_json(
        system_instruction="Return a Chinese explanation.",
        user_payload={"question": "test"},
        output_schema=schema,
    )
    assert result == {"answer_zh": "ok"}
    assert len(fake.responses.calls) == 2
    assert fake.responses.calls[0]["text"]["format"]["type"] == "json_schema"
    assert fake.responses.calls[1]["text"]["format"] == {"type": "json_object"}
    assert "Local validation is authoritative" in fake.responses.calls[1]["instructions"]
    assert "tools" not in fake.responses.calls[1]
    assert client.last_telemetry["output_contract"] == "json_object_local_schema_fallback"


def test_deepseek_client_does_not_retry_authentication_failure() -> None:
    fake = FakeClient([FakeHTTPError(401)])
    client = DeepSeekStructuredModelClient(client=fake, sleep=lambda _: None)
    with pytest.raises(DeepSeekResponseError, match="authentication failed") as captured:
        client.complete_json(system_instruction="JSON", user_payload={}, output_schema={})
    assert "unsafe provider detail" not in str(captured.value)
    assert len(fake.responses.calls) == 1


def test_bad_request_exposes_only_bounded_redacted_structured_detail() -> None:
    error = FakeHTTPError(
        400,
        body={
            "error": {
                "type": "invalid_request_error",
                "code": "unsupported_parameter",
                "param": "text.format",
                "message": "Unsupported format for " + "sk-" + "secret-that-must-not-escape",
            }
        },
    )
    fake = FakeClient([error, error])
    client = DeepSeekStructuredModelClient(client=fake, sleep=lambda _: None)
    with pytest.raises(DeepSeekResponseError) as captured:
        client.complete_json(system_instruction="JSON", user_payload={}, output_schema={})
    message = str(captured.value)
    assert "unsupported_parameter" in message
    assert "text.format" in message
    assert "[REDACTED_KEY]" in message
    assert "sk-secret" not in message
    assert "unsafe provider detail" not in message


def test_deepseek_client_retries_empty_content_once() -> None:
    sleeps = []
    fake = FakeClient([FakeResponse(""), FakeResponse("{}")])
    client = DeepSeekStructuredModelClient(client=fake, sleep=sleeps.append)
    assert client.complete_json(system_instruction="JSON", user_payload={}, output_schema={}) == {}
    assert sleeps == [1.0]


def test_deepseek_client_blocks_invalid_json_and_incomplete_response() -> None:
    invalid = DeepSeekStructuredModelClient(client=FakeClient([FakeResponse("not-json")]), sleep=lambda _: None)
    with pytest.raises(DeepSeekResponseError, match="invalid JSON"):
        invalid.complete_json(system_instruction="JSON", user_payload={}, output_schema={})
    assert invalid.last_telemetry["provider_host"] == "api.deepseek.com"
    incomplete = DeepSeekStructuredModelClient(
        client=FakeClient([FakeResponse("{}", status="incomplete")]), sleep=lambda _: None
    )
    with pytest.raises(DeepSeekResponseError, match="not completed"):
        incomplete.complete_json(system_instruction="JSON", user_payload={}, output_schema={})


def test_deepseek_client_accepts_only_an_exact_fenced_json_object() -> None:
    fenced = DeepSeekStructuredModelClient(
        client=FakeClient([FakeResponse('```json\n{"question":"valid"}\n```')]),
        sleep=lambda _: None,
    )
    assert fenced.complete_json(system_instruction="JSON", user_payload={}, output_schema={}) == {
        "question": "valid"
    }
    mixed = DeepSeekStructuredModelClient(
        client=FakeClient([FakeResponse('Reasoning text. Final answer: {"question":"valid"}')]),
        sleep=lambda _: None,
    )
    assert mixed.complete_json(system_instruction="JSON", user_payload={}, output_schema={}) == {
        "question": "valid"
    }
    assert mixed.last_telemetry["output_normalization"] == "unique_embedded_json"
    chatter = DeepSeekStructuredModelClient(
        client=FakeClient([FakeResponse('Example {"x":1}; final {"question":"valid"}')]),
        sleep=lambda _: None,
    )
    with pytest.raises(DeepSeekResponseError, match="invalid JSON"):
        chatter.complete_json(system_instruction="JSON", user_payload={}, output_schema={})


def test_provider_url_and_model_are_explicitly_allowlisted() -> None:
    client = DeepSeekStructuredModelClient(
        model="deepseek-v4.1-flash-1017",
        base_url="https://tk.enjoygoo.win/v1/",
        client=FakeClient([FakeResponse("{}")]),
    )
    assert client.base_url == "https://tk.enjoygoo.win/v1"
    with pytest.raises(DeepSeekConfigurationError, match="allowlisted"):
        DeepSeekStructuredModelClient(
            base_url="http://127.0.0.1:8000/v1",
            client=FakeClient([]),
        )
    with pytest.raises(DeepSeekConfigurationError, match="Unsupported"):
        DeepSeekStructuredModelClient(
            model="unreviewed-model",
            client=FakeClient([]),
        )


def test_chat_completions_mode_uses_json_object_and_local_schema_contract() -> None:
    fake = FakeChatClient(FakeChatResponse('{"question":"valid"}'))
    client = DeepSeekStructuredModelClient(
        client=fake,
        api_mode="chat_completions",
        model="deepseek-v4.1-flash-1017",
        base_url="https://tk.enjoygoo.win/v1",
    )
    result = client.complete_json(
        system_instruction="Return JSON.",
        user_payload={"research_question": "test"},
        output_schema={"type": "object"},
    )
    assert result == {"question": "valid"}
    request = fake.chat.completions.calls[0]
    assert request["response_format"] == {"type": "json_object"}
    assert "local validation is authoritative" in request["messages"][0]["content"]
    assert "tools" not in request
    assert client.last_telemetry["api_mode"] == "chat_completions"
    assert client.last_telemetry["total_tokens"] == 160
