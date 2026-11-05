from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable
from urllib.parse import urlparse


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
ALLOWED_PROVIDER_HOSTS = {"api.deepseek.com", "tk.enjoygoo.win"}
ALLOWED_MODELS = {"deepseek-flash", "deepseek-v4-pro", "deepseek-v4.1-flash-1017"}


class DeepSeekConfigurationError(RuntimeError):
    pass


class DeepSeekResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepSeekTelemetry:
    request_id: str | None
    provider_host: str
    api_mode: str
    model: str
    status: str
    attempts: int
    latency_ms: int
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class DeepSeekStructuredModelClient:
    """DeepSeek Responses API adapter with bounded retries and no tool access."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_mode: str | None = None,
        max_output_tokens: int = 2048,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
        base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL).rstrip("/")
        api_mode = api_mode or os.environ.get("DEEPSEEK_API_MODE", "responses")
        if client is None and not key:
            raise DeepSeekConfigurationError(
                "DEEPSEEK_API_KEY is not configured. Use the secure launcher; never paste the key into source code."
            )
        if model not in ALLOWED_MODELS:
            raise DeepSeekConfigurationError(f"Unsupported DeepSeek model: {model}")
        if api_mode not in {"responses", "chat_completions"}:
            raise DeepSeekConfigurationError(f"Unsupported API mode: {api_mode}")
        parsed_base = urlparse(base_url)
        if (
            parsed_base.scheme != "https"
            or parsed_base.hostname not in ALLOWED_PROVIDER_HOSTS
            or parsed_base.username
            or parsed_base.password
            or parsed_base.query
            or parsed_base.fragment
        ):
            raise DeepSeekConfigurationError(
                "Provider base URL must use HTTPS and an explicitly allowlisted host without credentials, query, or fragment"
            )
        if not 256 <= max_output_tokens <= 8192:
            raise DeepSeekConfigurationError("max_output_tokens must be between 256 and 8192")
        if not 0 <= max_retries <= 2:
            raise DeepSeekConfigurationError("max_retries must be between 0 and 2")

        if client is None:
            from openai import OpenAI

            client = OpenAI(
                api_key=key,
                base_url=base_url,
                timeout=timeout_seconds,
                max_retries=0,
            )
        self._client = client
        self.model = model
        self.base_url = base_url
        self.api_mode = api_mode
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._sleep = sleep
        self.last_telemetry: dict[str, Any] = {}

    def complete_json(
        self,
        *,
        system_instruction: str,
        user_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        from causalops.application.automation_budget import active_budget
        if active_budget() is not None:
            raise DeepSeekConfigurationError("V2任务只允许统一预算传输接口；旧SDK路径不能绕过物理请求计数。")
        started = time.monotonic()
        attempts = 0
        use_json_object_fallback = False
        self.last_telemetry = {}
        while True:
            attempts += 1
            try:
                if self.api_mode == "responses":
                    if use_json_object_fallback:
                        response = self._responses_json_object_fallback(
                            system_instruction=system_instruction,
                            user_payload=user_payload,
                            output_schema=output_schema,
                        )
                    else:
                        response = self._client.responses.create(
                            model=self.model,
                            instructions=system_instruction,
                            input=json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
                            reasoning={"effort": "none"},
                            max_output_tokens=self.max_output_tokens,
                            stream=False,
                            text={
                                "format": {
                                    "type": "json_schema",
                                    "name": "causal_spec",
                                    "schema": output_schema,
                                }
                            },
                        )
                    payload = self._parse_response(response, attempts, started)
                    self.last_telemetry["output_contract"] = (
                        "json_object_local_schema_fallback"
                        if use_json_object_fallback
                        else "json_schema"
                    )
                else:
                    payload = self._complete_chat_json(
                        system_instruction=system_instruction,
                        user_payload=user_payload,
                        output_schema=output_schema,
                        attempts=attempts,
                        started=started,
                    )
                return payload
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                if (
                    status_code == 400
                    and self.api_mode == "responses"
                    and not use_json_object_fallback
                    and attempts <= self.max_retries
                ):
                    # Some Responses-compatible providers reject particular JSON
                    # Schema contracts while still supporting JSON-object mode.
                    # Retry once without tools; local schema validation remains
                    # authoritative in every caller.
                    use_json_object_fallback = True
                    continue
                empty_once = (
                    isinstance(exc, DeepSeekResponseError)
                    and "empty structured output" in str(exc)
                    and attempts == 1
                )
                retryable = status_code in {429, 500, 503} or self._is_timeout(exc) or empty_once
                if retryable and attempts <= self.max_retries:
                    self._sleep((1.0, 3.0)[attempts - 1])
                    continue
                safe_reason = self._safe_error_reason(status_code, exc)
                raise DeepSeekResponseError(safe_reason) from None

    def _responses_json_object_fallback(
        self,
        *,
        system_instruction: str,
        user_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> Any:
        schema_text = json.dumps(
            output_schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self._client.responses.create(
            model=self.model,
            instructions=(
                system_instruction
                + "\nThe provider rejected JSON Schema transport. Return only one JSON object "
                + "matching the following schema. Local validation is authoritative:\n"
                + schema_text
            ),
            input=json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
            reasoning={"effort": "none"},
            max_output_tokens=self.max_output_tokens,
            stream=False,
            text={"format": {"type": "json_object"}},
        )

    def _parse_response(self, response: Any, attempts: int, started: float) -> dict[str, Any]:
        status = str(getattr(response, "status", "unknown"))
        if status != "completed":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            raise DeepSeekResponseError(f"DeepSeek response was not completed: {reason or status}")
        self._record_telemetry(response, attempts, started, status)
        content = getattr(response, "output_text", None)
        if not content:
            content = self._output_text_fallback(response)
        if not content or not str(content).strip():
            raise DeepSeekResponseError("DeepSeek returned empty structured output")
        try:
            parsed = self._decode_json_object(str(content))
        except json.JSONDecodeError as exc:
            raise DeepSeekResponseError(f"DeepSeek returned invalid JSON at position {exc.pos}") from None
        if not isinstance(parsed, dict):
            raise DeepSeekResponseError("DeepSeek structured output must be a JSON object")

        return parsed

    def _record_telemetry(self, response: Any, attempts: int, started: float, status: str) -> None:
        usage = getattr(response, "usage", None)
        input_details = getattr(usage, "input_tokens_details", None)
        telemetry = DeepSeekTelemetry(
            request_id=getattr(response, "id", None),
            provider_host=urlparse(self.base_url).hostname or "unknown",
            api_mode=self.api_mode,
            model=str(getattr(response, "model", self.model)),
            status=status,
            attempts=attempts,
            latency_ms=round((time.monotonic() - started) * 1000),
            input_tokens=getattr(usage, "input_tokens", None),
            cached_input_tokens=getattr(input_details, "cached_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
        )
        self.last_telemetry = asdict(telemetry)

    def _complete_chat_json(
        self,
        *,
        system_instruction: str,
        user_payload: dict[str, Any],
        output_schema: dict[str, Any],
        attempts: int,
        started: float,
    ) -> dict[str, Any]:
        schema_text = json.dumps(output_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        system_instruction
                        + "\nThe transport supports JSON-object mode but not guaranteed JSON Schema enforcement. "
                        + "Return only one JSON object satisfying this schema; local validation is authoritative:\n"
                        + schema_text
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=self.max_output_tokens,
            stream=False,
        )
        choices = getattr(response, "choices", None) or []
        if not choices:
            self._record_chat_telemetry(response, attempts, started, "empty_choices")
            raise DeepSeekResponseError("Provider returned no chat completion choices")
        choice = choices[0]
        finish_reason = str(getattr(choice, "finish_reason", "unknown"))
        status = "completed" if finish_reason == "stop" else finish_reason
        self._record_chat_telemetry(response, attempts, started, status)
        if finish_reason != "stop":
            raise DeepSeekResponseError(f"Chat completion was not completed: {finish_reason}")
        content = getattr(getattr(choice, "message", None), "content", None)
        if not content or not str(content).strip():
            raise DeepSeekResponseError("DeepSeek returned empty structured output")
        try:
            parsed = self._decode_json_object(str(content))
        except json.JSONDecodeError as exc:
            raise DeepSeekResponseError(f"DeepSeek returned invalid JSON at position {exc.pos}") from None
        if not isinstance(parsed, dict):
            raise DeepSeekResponseError("DeepSeek structured output must be a JSON object")
        return parsed

    def _record_chat_telemetry(self, response: Any, attempts: int, started: float, status: str) -> None:
        usage = getattr(response, "usage", None)
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        telemetry = DeepSeekTelemetry(
            request_id=getattr(response, "id", None),
            provider_host=urlparse(self.base_url).hostname or "unknown",
            api_mode=self.api_mode,
            model=str(getattr(response, "model", self.model)),
            status=status,
            attempts=attempts,
            latency_ms=round((time.monotonic() - started) * 1000),
            input_tokens=getattr(usage, "prompt_tokens", None),
            cached_input_tokens=getattr(prompt_details, "cached_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
        )
        self.last_telemetry = asdict(telemetry)

    def _decode_json_object(self, content: str) -> Any:
        stripped = content.strip()
        try:
            parsed = json.loads(stripped)
            self.last_telemetry["output_normalization"] = "exact_json"
            return parsed
        except json.JSONDecodeError as exc:
            exact_error = exc
        fenced = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            parsed = json.loads(fenced.group(1))
            self.last_telemetry["output_normalization"] = "exact_markdown_fence"
            return parsed

        decoder = json.JSONDecoder()
        candidates: list[tuple[int, int, Any]] = []
        for start, character in enumerate(stripped):
            if character != "{":
                continue
            try:
                value, length = decoder.raw_decode(stripped[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                candidates.append((start, start + length, value))
        maximal = [
            candidate
            for candidate in candidates
            if not any(
                other[0] <= candidate[0]
                and candidate[1] <= other[1]
                and (other[0], other[1]) != (candidate[0], candidate[1])
                for other in candidates
            )
        ]
        if len(maximal) == 1:
            self.last_telemetry["output_normalization"] = "unique_embedded_json"
            return maximal[0][2]
        raise exact_error

    @staticmethod
    def _output_text_fallback(response: Any) -> str | None:
        dumped = response.model_dump() if hasattr(response, "model_dump") else {}
        texts: list[str] = []
        for item in dumped.get("output", []):
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "output_text" and part.get("text"):
                    texts.append(part["text"])
        return "".join(texts) or None

    @staticmethod
    def _is_timeout(exc: Exception) -> bool:
        return "timeout" in type(exc).__name__.lower()

    @staticmethod
    def _safe_error_reason(status_code: int | None, exc: Exception) -> str:
        reasons = {
            400: "DeepSeek rejected the request format; do not retry unchanged input.",
            401: "DeepSeek authentication failed. Verify or rotate the API key.",
            402: "DeepSeek account balance is insufficient.",
            403: "Provider denied access to this model or endpoint.",
            404: "Provider endpoint was not found; verify Responses API compatibility and base URL.",
            422: "DeepSeek rejected one or more request parameters.",
            429: "DeepSeek rate limit was reached after bounded retries.",
            500: "DeepSeek server error persisted after bounded retries.",
            503: "DeepSeek service remained busy after bounded retries.",
        }
        if status_code in reasons:
            summary = reasons[status_code]
            detail = DeepSeekStructuredModelClient._safe_provider_error_detail(exc)
            if detail and status_code in {400, 404, 422}:
                return f"{summary} Provider detail: {detail}"
            return summary
        if DeepSeekStructuredModelClient._is_timeout(exc):
            return "DeepSeek request timed out after bounded retries."
        if isinstance(exc, DeepSeekResponseError):
            return str(exc)
        return f"DeepSeek request failed safely ({type(exc).__name__})."

    @staticmethod
    def _safe_provider_error_detail(exc: Exception) -> str | None:
        """Extract a bounded, redacted provider error without leaking credentials.

        The OpenAI-compatible SDK exposes structured error bodies on HTTP failures.
        We deliberately ignore headers, request objects and arbitrary exception text;
        only the provider's type/code/parameter/message fields are allowlisted.
        """

        body = getattr(exc, "body", None)
        if not isinstance(body, dict):
            return None
        error = body.get("error", body)
        if not isinstance(error, dict):
            return None
        parts: list[str] = []
        for label, field in (
            ("type", "type"),
            ("code", "code"),
            ("param", "param"),
            ("message", "message"),
        ):
            value = error.get(field)
            if value is None:
                continue
            text = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED_KEY]", str(value))
            text = re.sub(r"\s+", " ", text).strip()[:500]
            if text:
                parts.append(f"{label}={text}")
        return "; ".join(parts)[:800] or None
