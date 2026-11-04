"""Meter real HTTP attempts independently of model output and local schema repair."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from causalops.evaluation.v12.capture import append
from causalops.llm.providers import ProviderConfig, StructuredModelClient


class Metered(StructuredModelClient):
    def __init__(self, key, folder, *, client=None, sleep=None):
        options = {} if sleep is None else {"sleep": sleep}
        super().__init__(ProviderConfig(max_output_tokens=3000, timeout_seconds=45, max_retries=1),
                         key, client=client, **options)
        self.folder = Path(folder)
        self.index = 0

    def _request(self, system, payload, schema):
        path, headers, body = super()._request(system, payload, schema)
        # Stable on transport replay only. No assumption about provider-side deduplication.
        headers["Idempotency-Key"] = self.call_id
        return path, headers, body

    def _observe_attempt(self, event):
        append(self.folder / "physical_attempts.jsonl", {
            **event, "at": datetime.now(timezone.utc).isoformat(),
            "call_id": self.call_id, "number": self.index, "request_sha256": self.request_sha,
        })

    def _content(self, response):
        text, usage = super()._content(response)
        self.raw = text.replace(self._api_key, "[已移除]")
        self.usage = {k: v for k, v in usage.items() if k in
                      ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens", "total_tokens")
                      and type(v) is int and v >= 0}
        return text, usage

    def complete_json(self, **kwargs):
        self.index += 1
        self.call_id = uuid4().hex
        self.raw = None
        self.usage = {}
        self.last_telemetry = {}
        self.request_sha = sha256(json.dumps(kwargs, sort_keys=True, ensure_ascii=False,
                                             separators=(",", ":")).encode()).hexdigest()
        started = perf_counter()
        record = {"number": self.index, "call_id": self.call_id, "request_sha256": self.request_sha,
                  "schema": kwargs["output_schema"].get("title", "结构化输出"),
                  "at": datetime.now(timezone.utc).isoformat(), "config": self.provider_config.model_dump()}
        append(self.folder / "requests.jsonl", record)
        try:
            value = super().complete_json(**kwargs)
            record.update(valid=True, output=value)
            return value
        except Exception as exc:
            record.update(valid=False, error=type(exc).__name__)
            raise
        finally:
            record.update(seconds=perf_counter()-started, raw=self.raw, usage=self.usage,
                          telemetry=self.last_telemetry)
            append(self.folder / "responses.jsonl", record)
