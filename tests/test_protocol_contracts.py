from causalops.protocols import MCP_PROTOCOL_VERSION, LocalA2ACoordinator, ModernMCPBridge, build_agent_card


def valid_spec() -> dict:
    return {
        "question": "What is the average effect of AI reply exposure on later user activity?",
        "domain": "generic",
        "analysis_unit": "user",
        "treatment": "treated",
        "outcome": "post_posts",
        "entity_id_column": "user_id",
        "covariates": ["pre_posts"],
        "candidate_methods": ["psm"],
        "identification_assumptions": ["conditional exchangeability"],
        "assignment_mechanism": "observational",
        "data_structure": "cross_section",
        "positivity_plausible": True,
    }


def request(method: str, params: dict | None = None, version: str = MCP_PROTOCOL_VERSION) -> dict:
    payload = dict(params or {})
    payload["_meta"] = ModernMCPBridge.request_meta()
    payload["_meta"]["io.modelcontextprotocol/protocolVersion"] = version
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": payload}


def test_mcp_modern_discovery_and_deterministic_tool_order() -> None:
    bridge = ModernMCPBridge()
    discovery = bridge.handle(request("server/discover"))
    assert discovery["result"]["protocolVersions"] == ["2026-07-28"]
    listing = bridge.handle(request("tools/list"))
    names = [tool["name"] for tool in listing["result"]["tools"]]
    assert names == ["causalops.route_spec", "causalops.validate_spec"]
    assert listing["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"]


def test_mcp_rejects_unsupported_protocol_revision() -> None:
    response = ModernMCPBridge().handle(request("tools/list", version="2025-11-25"))
    assert response["error"]["code"] == -32022
    assert response["error"]["data"]["supported"] == ["2026-07-28"]


def test_mcp_routes_but_never_executes() -> None:
    response = ModernMCPBridge().handle(
        request("tools/call", {"name": "causalops.route_spec", "arguments": {"spec": valid_spec()}})
    )
    result = response["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["executionPerformed"] is False
    assert result["structuredContent"]["requiresHumanApproval"] is True


def test_mcp_unknown_tool_is_a_tool_error() -> None:
    response = ModernMCPBridge().handle(
        request("tools/call", {"name": "causalops.shell", "arguments": {}})
    )
    assert response["result"]["isError"] is True


def test_mcp_invalid_request_and_unknown_method_are_protocol_errors() -> None:
    bridge = ModernMCPBridge()
    assert bridge.handle({"jsonrpc": "1.0", "id": 7})["error"]["code"] == -32600
    assert bridge.handle(request("not/a/method"))["error"]["code"] == -32601


def test_mcp_invalid_tool_arguments_are_a_tool_error() -> None:
    response = ModernMCPBridge().handle(
        request("tools/call", {"name": "causalops.validate_spec", "arguments": {"spec": {}}})
    )
    assert response["result"]["isError"] is True


def test_a2a_agent_card_uses_v1_fields() -> None:
    card = build_agent_card()
    interface = card["supportedInterfaces"][0]
    assert interface["protocolVersion"] == "1.0"
    assert interface["protocolBinding"] == "JSONRPC"
    assert card["defaultInputModes"] == ["application/json", "text/plain"]


def test_a2a_local_handoff_stops_at_human_approval_boundary() -> None:
    task = LocalA2ACoordinator().send_spec(valid_spec())
    payload = task.model_dump(mode="json", by_alias=True)
    assert payload["status"]["state"] == "TASK_STATE_COMPLETED"
    assert payload["metadata"]["humanApprovalRequired"] is True
    assert payload["metadata"]["executionPerformed"] is False


def test_a2a_rejects_invalid_spec() -> None:
    invalid = valid_spec()
    invalid["outcome"] = invalid["treatment"]
    task = LocalA2ACoordinator().send_spec(invalid)
    assert task.status["state"] == "TASK_STATE_REJECTED"
