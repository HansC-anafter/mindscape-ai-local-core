"""
Claude Code CLI Agent Adapter

Dispatches coding tasks to Anthropic Claude Code CLI via the shared
REST Polling + DB-primary pipeline.

All dispatch lifecycle logic is inherited from PollingAgentAdapter.
"""

from backend.app.services.external_agents.core.polling_adapter import (
    PollingAgentAdapter,
)


class ClaudeCodeCLIAdapter(PollingAgentAdapter):
    """
    Claude Code CLI Agent Adapter.

    Dispatches coding tasks to Anthropic Claude Code CLI via the shared
    polling-based dispatch pipeline. All lifecycle logic (DB persistence,
    Future notification, timeout recovery) is inherited.
    """

    AGENT_NAME = "claude_code_cli"
    AGENT_VERSION = "1.0.0"

    RESULT_TIMEOUT: float = 600.0
