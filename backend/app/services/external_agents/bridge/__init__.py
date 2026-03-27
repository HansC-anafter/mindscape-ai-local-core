"""
Shared host-bridge infrastructure for WS-dispatched CLI runtimes.

Architecture boundary:
- external_agents.bridge: shared transport/runtime plumbing
- external_agents.agents.<surface>: surface identity, defaults, docs, wrappers
- scripts/gemini_cli_runtime_bridge.py: provider-specific Gemini subprocess bridge
"""

from backend.app.services.external_agents.bridge.host_ws_client import (
    HostBridgeWSClient,
)
from backend.app.services.external_agents.bridge.runtime_adapter import (
    HostBridgeRuntimeAdapter,
)
from backend.app.services.external_agents.bridge.task_executor import (
    ExecutionContext,
    ExecutionResult,
    HostBridgeTaskExecutor,
)

__all__ = [
    "ExecutionContext",
    "ExecutionResult",
    "HostBridgeRuntimeAdapter",
    "HostBridgeTaskExecutor",
    "HostBridgeWSClient",
]
