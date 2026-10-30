"""Local protocol contracts for safe inter-agent integration.

These modules implement and test protocol-shaped messages. They do not claim remote
deployment, official SDK certification, authentication, or network interoperability.
"""

from causalops.protocols.a2a import LocalA2ACoordinator, build_agent_card
from causalops.protocols.mcp import MCP_PROTOCOL_VERSION, ModernMCPBridge

__all__ = [
    "LocalA2ACoordinator",
    "MCP_PROTOCOL_VERSION",
    "ModernMCPBridge",
    "build_agent_card",
]
