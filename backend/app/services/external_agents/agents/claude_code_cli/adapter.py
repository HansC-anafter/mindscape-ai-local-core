"""
Claude Code CLI Runtime Adapter.

Runs Claude Code over the same WS-first bridge contract as Gemini CLI,
with polling only kept as the inherited fallback path.
"""

import logging

from backend.app.services.external_agents.agents.gemini_cli.adapter import (
    GeminiCLIAdapter,
)

logger = logging.getLogger(__name__)


class ClaudeCodeCLIAdapter(GeminiCLIAdapter):
    """
    Claude Code CLI Agent Adapter.

    Uses the same WS-first runtime bridge contract as Gemini so requests
    always target the real surface-owning worker. This prevents multi-worker
    requests from queueing against the wrong in-memory manager.
    """

    RUNTIME_NAME = "claude_code_cli"
    RUNTIME_VERSION = "1.0.0"
    AGENT_NAME = RUNTIME_NAME
    AGENT_VERSION = RUNTIME_VERSION

    RESULT_TIMEOUT: float = 600.0
