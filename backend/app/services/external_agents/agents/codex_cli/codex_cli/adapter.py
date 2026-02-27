"""
Codex CLI Agent Adapter

Dispatches coding tasks to OpenAI Codex CLI via the shared
REST Polling + DB-primary pipeline.

All dispatch lifecycle logic is inherited from PollingAgentAdapter.
"""

from backend.app.services.external_agents.core.polling_adapter import (
    PollingAgentAdapter,
)


class CodexCLIAdapter(PollingAgentAdapter):
    """
    Codex CLI Agent Adapter.

    Dispatches coding tasks to OpenAI Codex CLI via the shared
    polling-based dispatch pipeline. All lifecycle logic (DB persistence,
    Future notification, timeout recovery) is inherited.
    """

    AGENT_NAME = "codex_cli"
    AGENT_VERSION = "1.0.0"

    # Codex may need longer execution time
    RESULT_TIMEOUT: float = 900.0
