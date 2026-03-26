"""
Claude Code CLI Runtime Adapter.

Runs Claude Code over the shared WS-first bridge contract,
with polling only kept as the inherited fallback path.
"""

import logging

from backend.app.services.external_agents.bridge.runtime_adapter import (
    HostBridgeRuntimeAdapter,
)

logger = logging.getLogger(__name__)


class ClaudeCodeCLIAdapter(HostBridgeRuntimeAdapter):
    """
    Claude Code CLI Agent Adapter.

    Uses the shared WS-first runtime bridge contract so requests
    always target the real surface-owning worker. This prevents multi-worker
    requests from queueing against the wrong in-memory manager.
    """

    RUNTIME_NAME = "claude_code_cli"
    RUNTIME_VERSION = "1.0.0"
    AGENT_NAME = RUNTIME_NAME
    AGENT_VERSION = RUNTIME_VERSION

    RESULT_TIMEOUT: float = 600.0
