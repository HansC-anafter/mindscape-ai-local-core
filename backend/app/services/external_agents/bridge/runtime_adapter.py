"""Shared host-bridge runtime adapter compatibility entrypoint."""

import logging
import uuid
from typing import Any, Optional

from backend.app.services.external_agents.core.base_adapter import (
    RuntimeExecRequest,
    RuntimeExecResponse,
)
from backend.app.services.external_agents.core.polling_adapter import (
    PollingRuntimeAdapter,
)

from .runtime_adapter_core.availability_mixin import AvailabilityMixin
from .runtime_adapter_core.parsing import parse_dispatch_response
from .runtime_adapter_core.sampling_mixin import SamplingExecutionMixin
from .runtime_adapter_core.ws_mixin import WsExecutionMixin

logger = logging.getLogger(__name__)


class HostBridgeRuntimeAdapter(
    AvailabilityMixin,
    WsExecutionMixin,
    SamplingExecutionMixin,
    PollingRuntimeAdapter,
):
    """Shared host-bridge runtime adapter."""

    RUNTIME_NAME = "gemini_cli"
    RUNTIME_VERSION = "1.0.0"

    ALWAYS_DENIED_TOOLS = [
        "system.run",
        "gateway",
        "docker",
    ]

    ACK_TIMEOUT: float = 30.0
    RESULT_TIMEOUT: float = 600.0

    def __init__(
        self,
        strategy: str = "ws",
        ws_manager: Optional[Any] = None,
        sampling_gate: Optional[Any] = None,
        mcp_server: Optional[Any] = None,
        dispatch_store: Optional[Any] = None,
    ):
        """Initialize host bridge runtime adapter."""
        super().__init__(dispatch_store=dispatch_store)
        self.strategy = strategy
        self.ws_manager = ws_manager
        self.sampling_gate = sampling_gate
        self.mcp_server = mcp_server

    async def execute(self, request: RuntimeExecRequest) -> RuntimeExecResponse:
        """Execute a task by dispatching to the host bridge."""
        logger.info(
            "%s.execute called for workspace=%s task=%s",
            self.__class__.__name__,
            request.workspace_id,
            request.task[:50],
        )
        self._available_cache = None
        self._resolve_ws_manager()
        logger.info(
            "%s: ws_manager resolved? %s",
            self.__class__.__name__,
            self.ws_manager is not None,
        )
        if self.ws_manager:
            logger.info(
                "%s: ws_manager has surface connection? %s",
                self.__class__.__name__,
                self.ws_manager.has_connections(
                    workspace_id=request.workspace_id or None,
                    surface_type=self.RUNTIME_NAME,
                ),
            )

        self.log_execution_start(request)
        execution_id = str(uuid.uuid4())

        try:
            logger.info("%s: strategy=%s", self.__class__.__name__, self.strategy)

            if self.strategy == "ws":
                target_client_id = ""
                if isinstance(request.agent_config, dict):
                    target_client_id = str(
                        request.agent_config.get("target_client_id") or ""
                    ).strip()
                ws_connected = self.ws_manager is not None and (
                    hasattr(self.ws_manager, "has_connections")
                    and self.ws_manager.has_connections(
                        workspace_id=request.workspace_id or None,
                        surface_type=self.RUNTIME_NAME,
                    )
                )
                if not ws_connected and target_client_id:
                    logger.info(
                        "%s: no local WS client, dispatching directly to target client %s",
                        self.__class__.__name__,
                        target_client_id,
                    )
                    response = await self._execute_via_ws(request, execution_id)
                elif not ws_connected and self._has_registered_runtime_polling_fallback(
                    request.workspace_id or None
                ):
                    logger.info(
                        "%s: no WS client connected, falling back to polling transport",
                        self.__class__.__name__,
                    )
                    response = await self._execute_via_polling(request, execution_id)
                elif not ws_connected:
                    logger.warning(
                        "%s: no WS client connected, failing fast instead of queuing",
                        self.__class__.__name__,
                    )
                    return RuntimeExecResponse(
                        success=False,
                        output="",
                        duration_seconds=0,
                        error=(
                            "No WebSocket client connected. "
                            f"Run scripts/start_cli_bridge.sh --surface {self.RUNTIME_NAME} "
                            "to connect the host bridge."
                        ),
                    )
                else:
                    response = await self._execute_via_ws(request, execution_id)
            elif self.strategy == "polling":
                response = await self._execute_via_polling(request, execution_id)
            elif self.strategy == "sampling":
                response = await self._execute_via_sampling(request, execution_id)
            else:
                response = RuntimeExecResponse(
                    success=False,
                    output="",
                    duration_seconds=0,
                    error=f"Unknown transport strategy: {self.strategy}",
                )
        except Exception as e:
            logger.exception("Gemini CLI execution failed with exception")
            response = RuntimeExecResponse(
                success=False,
                output="",
                duration_seconds=0,
                error=str(e),
                exit_code=-1,
            )

        self.log_execution_end(response)
        return response


__all__ = [
    "HostBridgeRuntimeAdapter",
    "parse_dispatch_response",
]
