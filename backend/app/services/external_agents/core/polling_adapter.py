"""Polling runtime adapter compatibility entrypoint."""

from typing import Any, Optional

from backend.app.services.external_agents.core.base_adapter import BaseRuntimeAdapter

from .polling_adapter_core.availability_mixin import PollingAvailabilityMixin
from .polling_adapter_core.execution_mixin import PollingExecutionMixin
from .polling_adapter_core.payload import build_dispatch_payload
from .polling_adapter_core.response_mixin import PollingResponseMixin


class PollingRuntimeAdapter(
    PollingAvailabilityMixin,
    PollingExecutionMixin,
    PollingResponseMixin,
    BaseRuntimeAdapter,
):
    """
    Base class for runtimes dispatched through the polling runtime store.

    Subclasses provide runtime identity and optional timeout overrides while the
    mixins provide availability, execution, and response recovery behavior.

    Usage:
        class CodexCLIAdapter(PollingRuntimeAdapter):
            RUNTIME_NAME = "codex_cli"
            RUNTIME_VERSION = "1.0.0"
    """

    RUNTIME_NAME: str = "polling_agent"
    RUNTIME_VERSION: str = "1.0.0"

    ALWAYS_DENIED_TOOLS = [
        "system.run",
        "gateway",
        "docker",
    ]

    # Timeout for ack from runner (seconds)
    ACK_TIMEOUT: float = 30.0

    # Timeout for result from runner (seconds)
    RESULT_TIMEOUT: float = 600.0

    # Maximum time to wait before checking DB for cross-process completion
    WAIT_SLICE_SECONDS: float = 5.0

    def __init__(self, dispatch_store: Optional[Any] = None):
        """
        Initialize polling adapter.

        Args:
            dispatch_store: Optional store for pending/dispatched tasks
        """
        super().__init__()
        self.dispatch_store = dispatch_store


PollingAgentAdapter = PollingRuntimeAdapter

__all__ = [
    "PollingRuntimeAdapter",
    "PollingAgentAdapter",
    "build_dispatch_payload",
]
