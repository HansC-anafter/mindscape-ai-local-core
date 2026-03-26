"""
Gemini CLI runtime adapter.

Provider-specific facade over the shared host bridge runtime layer.
"""

from backend.app.services.external_agents.bridge.runtime_adapter import (
    HostBridgeRuntimeAdapter,
)


class GeminiCLIAdapter(HostBridgeRuntimeAdapter):
    """Gemini surface routed through the shared host bridge runtime."""

    RUNTIME_NAME = "gemini_cli"
    RUNTIME_VERSION = "1.0.0"

    ALWAYS_DENIED_TOOLS = [
        "system.run",
        "gateway",
        "docker",
    ]

    ACK_TIMEOUT: float = 30.0
    RESULT_TIMEOUT: float = 600.0
