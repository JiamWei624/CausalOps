from __future__ import annotations

import json
from typing import Any, Callable

from pydantic import ValidationError

from causalops.identification import route_identification
from causalops.schemas import CausalSpec


MCP_PROTOCOL_VERSION = "2026-07-28"
_SERVER_INFO = {"name": "causalops-local-bridge", "version": "0.1.0"}


class ModernMCPBridge:
    """Small stateless MCP 2026-07-28 JSON-RPC bridge.

    The bridge intentionally exposes only design validation and identification
    routing. Estimation remains behind the application's human approval gate.
    Transport, authentication, and remote hosting are outside this local contract.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "causalops.route_spec": self._route_spec,
            "causalops.validate_spec": self._validate_spec,
        }

    @staticmethod
    def _meta_for_response() -> dict[str, Any]:
        return {"io.modelcontextprotocol/serverInfo": _SERVER_INFO}

    @staticmethod
    def request_meta(*, client_name: str = "causalops-test-client") -> dict[str, Any]:
        return {
            "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientInfo": {"name": client_name, "version": "0.1.0"},
            "io.modelcontextprotocol/clientCapabilities": {},
        }

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        if request.get("jsonrpc") != "2.0" or "method" not in request:
            return self._error(request_id, -32600, "Invalid Request")
        params = request.get("params") or {}
        meta = params.get("_meta") or request.get("_meta") or {}
        requested_version = meta.get("io.modelcontextprotocol/protocolVersion")
        if requested_version != MCP_PROTOCOL_VERSION:
            return self._error(
                request_id,
                -32022,
                "Unsupported protocol version",
                {"supported": [MCP_PROTOCOL_VERSION], "requested": requested_version},
            )

        method = request["method"]
        if method == "server/discover":
            result = {
                "resultType": "complete",
                "protocolVersions": [MCP_PROTOCOL_VERSION],
                "capabilities": {"tools": {"listChanged": False}},
                "instructions": "Validate and route causal designs. Human approval is required before execution.",
                "ttlMs": 300000,
                "cacheScope": "public",
            }
        elif method == "tools/list":
            result = {
                "resultType": "complete",
                "tools": self._tool_definitions(),
                "ttlMs": 300000,
                "cacheScope": "public",
            }
        elif method == "tools/call":
            result = self._call_tool(params)
        else:
            return self._error(request_id, -32601, "Method not found")
        result["_meta"] = self._meta_for_response()
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in self._tools:
            return {
                "resultType": "complete",
                "content": [{"type": "text", "text": f"Unknown allowlisted tool: {name}"}],
                "isError": True,
            }
        try:
            structured = self._tools[name](arguments)
        except (ValidationError, ValueError, TypeError) as exc:
            return {
                "resultType": "complete",
                "content": [{"type": "text", "text": f"Validation failed: {exc}"}],
                "isError": True,
            }
        return {
            "resultType": "complete",
            "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
            "structuredContent": structured,
            "isError": False,
        }

    @staticmethod
    def _validate_spec(arguments: dict[str, Any]) -> dict[str, Any]:
        spec = CausalSpec.model_validate(arguments.get("spec"))
        return {
            "valid": True,
            "spec": spec.model_dump(mode="json"),
            "requiresHumanApproval": True,
        }

    @staticmethod
    def _route_spec(arguments: dict[str, Any]) -> dict[str, Any]:
        spec = CausalSpec.model_validate(arguments.get("spec"))
        decision = route_identification(spec)
        return {
            "decision": decision.model_dump(mode="json"),
            "requiresHumanApproval": True,
            "executionPerformed": False,
        }

    @staticmethod
    def _tool_definitions() -> list[dict[str, Any]]:
        spec_schema = CausalSpec.model_json_schema()
        return [
            {
                "name": "causalops.route_spec",
                "title": "Route a causal design",
                "description": "Run deterministic identification gates without executing an estimator.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"spec": spec_schema},
                    "required": ["spec"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "destructiveHint": False},
            },
            {
                "name": "causalops.validate_spec",
                "title": "Validate a CausalSpec",
                "description": "Validate and normalize a strict CausalSpec object.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"spec": spec_schema},
                    "required": ["spec"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "destructiveHint": False},
            },
        ]

    def _error(
        self,
        request_id: Any,
        code: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error,
            "_meta": self._meta_for_response(),
        }
