"""OpenClaw runtime adapter compatibility entrypoint."""

from typing import Any, Dict, Optional

from backend.app.services.external_agents.core.base_adapter import BaseRuntimeAdapter

from .adapter_core.availability_mixin import OpenClawAvailabilityMixin
from .adapter_core.command_mixin import OpenClawCommandMixin
from .adapter_core.execution_mixin import OpenClawExecutionMixin
from .adapter_core.result_mixin import OpenClawResultMixin


class OpenClawAdapter(
    OpenClawAvailabilityMixin,
    OpenClawExecutionMixin,
    OpenClawCommandMixin,
    OpenClawResultMixin,
    BaseRuntimeAdapter,
):
    """
    OpenClaw Code Execution Adapter

    Extends BaseRuntimeAdapter with OpenClaw CLI functionality:
    - CLI invocation via 'openclaw' command
    - Sandbox configuration generation
    - Execution trace collection

    Usage:
        adapter = OpenClawAdapter()
        if await adapter.is_available():
            response = await adapter.execute(request)
    """

    RUNTIME_NAME = "openclaw"
    RUNTIME_VERSION = "1.0.0"

    # CLI commands to try (in order of preference)
    CLI_COMMANDS = ["openclaw"]

    # OpenClaw-specific denied tools
    ALWAYS_DENIED_TOOLS = [
        "system.run",
        "gateway",
        "docker",
    ]

    def __init__(
        self,
        cli_command: str = None,  # Auto-detect if not specified
        default_model: str = "anthropic/claude-sonnet-4-20250514",
    ):
        """
        Initialize OpenClaw adapter.

        Args:
            cli_command: Command to invoke CLI (auto-detected if None)
            default_model: Default LLM model for OpenClaw
        """
        super().__init__()
        self.cli_command = cli_command
        self.default_model = default_model
        self._detected_cli = None
        self._availability_detail_cache: Optional[Dict[str, Any]] = None


__all__ = ["OpenClawAdapter"]
