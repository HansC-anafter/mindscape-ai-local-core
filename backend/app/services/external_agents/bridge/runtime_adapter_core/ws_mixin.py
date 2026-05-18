"""WebSocket execution helpers for host bridge runtime adapter."""

import logging
import time
from typing import Any

from backend.app.services.external_agents.core.base_adapter import (
    RuntimeExecRequest,
    RuntimeExecResponse,
)
from backend.app.services.external_agents.core.polling_adapter import (
    build_dispatch_payload,
)

from .parsing import parse_dispatch_response

logger = logging.getLogger(__name__)


class WsExecutionMixin:
    def _resolve_ws_manager(self) -> None:
        """Lazily resolve ws_manager from the global AgentDispatchManager."""
        if self.ws_manager is not None:
            return

        try:
            from backend.app.routes.agent_websocket import (
                get_agent_dispatch_manager,
            )

            self.ws_manager = get_agent_dispatch_manager()
        except ImportError:
            logger.debug("agent_websocket module not available")

    async def _execute_via_ws(
        self,
        request: RuntimeExecRequest,
        execution_id: str,
    ) -> RuntimeExecResponse:
        """Dispatch task via WebSocket Push."""
        start_time = time.monotonic()
        payload = build_dispatch_payload(request, execution_id, self.RUNTIME_NAME)

        if not self.ws_manager:
            return RuntimeExecResponse(
                success=False,
                output="",
                duration_seconds=0,
                error="WebSocket manager not initialized",
            )

        ws_message = {
            "type": "dispatch",
            **payload,
        }
        target_client_id = ""
        if isinstance(request.agent_config, dict):
            target_client_id = str(
                request.agent_config.get("target_client_id") or ""
            ).strip()

        try:
            raw_result = await self.ws_manager.dispatch_and_wait(
                workspace_id=request.workspace_id or "",
                message=ws_message,
                execution_id=execution_id,
                timeout=request.max_duration_seconds or self.RESULT_TIMEOUT,
                target_client_id=target_client_id or None,
            )

            if raw_result.get("status") == "timeout":
                elapsed = time.monotonic() - start_time
                logger.warning(
                    f"WS dispatch: no activity timeout after {elapsed:.1f}s "
                    f"(exec={execution_id})"
                )
                return RuntimeExecResponse(
                    success=False,
                    output="",
                    duration_seconds=elapsed,
                    error=raw_result.get("error", f"No activity for {elapsed:.0f}s"),
                    exit_code=-1,
                    agent_metadata={
                        "transport": "ws_push",
                        "execution_id": execution_id,
                        "status": "timeout",
                    },
                )

            raw_result.setdefault("metadata", {})["transport"] = "ws_push"
            response = parse_dispatch_response(raw_result, start_time)
            if not response.success:
                logger.warning(
                    "[%s] DIAGNOSTIC: WS dispatch returned failure for exec=%s. "
                    "parsed_error=%r, parsed_output=%r, raw_status=%r, "
                    "raw_error=%r, raw_output=%r",
                    self.RUNTIME_NAME,
                    execution_id,
                    response.error,
                    str(response.output)[:500],
                    raw_result.get("status"),
                    raw_result.get("error"),
                    str(raw_result.get("output", ""))[:500],
                )
            return response

        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.exception(f"WS dispatch failed for exec={execution_id}: {e}")
            return RuntimeExecResponse(
                success=False,
                output="",
                duration_seconds=elapsed,
                error=str(e),
                exit_code=-1,
                agent_metadata={
                    "transport": "ws_push",
                    "execution_id": execution_id,
                    "status": "error",
                },
            )
