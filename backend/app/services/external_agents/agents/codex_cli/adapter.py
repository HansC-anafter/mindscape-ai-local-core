"""
Codex CLI Runtime Adapter.

Runs Codex over the same WS-first bridge contract used by Gemini CLI,
with the polling path retained only as the inherited fallback.
"""

import logging

from backend.app.services.external_agents.agents.gemini_cli.adapter import (
    GeminiCLIAdapter,
)

logger = logging.getLogger(__name__)


class CodexCLIAdapter(GeminiCLIAdapter):
    """
    Codex CLI Agent Adapter.

    Uses the same WS-first runtime bridge contract as Gemini so requests
    always target the real surface-owning worker. This prevents multi-worker
    requests from queueing against the wrong in-memory manager.
    """

    RUNTIME_NAME = "codex_cli"
    RUNTIME_VERSION = "1.0.0"
    AGENT_NAME = RUNTIME_NAME
    AGENT_VERSION = RUNTIME_VERSION

    # Codex may need longer execution time
    RESULT_TIMEOUT: float = 900.0
