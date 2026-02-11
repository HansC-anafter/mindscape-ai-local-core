"""
Cloud Connector - Transport Handler

Handles execution request processing, event reporting, and usage reporting.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, Any, Optional

from websockets.client import WebSocketClientProtocol

from sitehub_protocol.transport import ExecutionRequest, ExecutionEvent, UsageReport
from sitehub_protocol.contracts.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


class TransportHandler:
    """
    Transport handler for execution requests and event reporting.

    Handles:
    - ExecutionRequest processing
    - ExecutionEvent reporting
    - UsageReport reporting
    """

    def __init__(self, websocket: WebSocketClientProtocol, device_id: str):
        """
        Initialize transport handler.

        Args:
            websocket: WebSocket connection
            device_id: Executor device identifier
        """
        self.websocket = websocket
        self.device_id = device_id
        self._active_executions: Dict[str, asyncio.Task] = {}

    async def handle_execution_request(self, request_data: Dict[str, Any]) -> None:
        """
        Handle execution request from Cloud.

        Args:
            request_data: Execution request data
        """
        try:
            request = ExecutionRequest.from_dict(request_data)
            logger.info(f"Received execution request: {request.request_id}")

            task = asyncio.create_task(self._execute_and_report(request))
            self._active_executions[request.request_id] = task

        except Exception as e:
            logger.error(f"Failed to handle execution request: {e}", exc_info=True)
            await self._report_error(
                request_data.get("request_id", "unknown"),
                str(e),
            )

    async def _execute_and_report(self, request: ExecutionRequest) -> None:
        """
        Execute request and report results.

        Args:
            request: Execution request
        """
        execution_start = _utc_now()
        event_id = f"event_{uuid.uuid4().hex[:16]}"

        try:
            await self._report_event(
                request.request_id,
                event_id,
                "started",
                {"message": "Execution started"},
            )

            result = await self._execute_job(request)

            execution_end = _utc_now()
            duration_ms = int((execution_end - execution_start).total_seconds() * 1000)

            await self._report_event(
                request.request_id,
                f"event_{uuid.uuid4().hex[:16]}",
                "completed",
                result,
            )

            await self._report_usage(
                request.request_id,
                duration_ms,
                result.get("token_usage", {}),
                result.get("cost_estimate"),
            )

        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)
            await self._report_event(
                request.request_id,
                f"event_{uuid.uuid4().hex[:16]}",
                "failed",
                {"error": str(e)},
            )

        finally:
            self._active_executions.pop(request.request_id, None)

    async def _execute_job(self, request: ExecutionRequest) -> Dict[str, Any]:
        """
        Execute job based on job_type.

        Args:
            request: Execution request

        Returns:
            Execution result
        """
        if request.job_type == "playbook":
            return await self._execute_playbook(request)
        elif request.job_type == "tool":
            return await self._execute_tool(request)
        elif request.job_type == "chain":
            return await self._execute_chain(request)
        else:
            raise ValueError(f"Unknown job_type: {request.job_type}")

    async def _execute_playbook(self, request: ExecutionRequest) -> Dict[str, Any]:
        """
        Execute playbook.

        Args:
            request: Execution request

        Returns:
            Execution result
        """
        from backend.app.services.playbook_runner import PlaybookRunner

        playbook_runner = PlaybookRunner()
        playbook_code = request.payload.get("playbook_code")
        inputs = request.payload.get("inputs", {})

        if not playbook_code:
            raise ValueError("playbook_code is required for playbook execution")

        workspace_id = request.execution_context.metadata.get("workspace_id")
        profile_id = request.execution_context.metadata.get("profile_id")

        if not workspace_id:
            raise ValueError("workspace_id is required in execution_context.metadata")
        if not profile_id:
            raise ValueError("profile_id is required in execution_context.metadata")

        result = await playbook_runner.start_playbook_execution(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=workspace_id,
        )

        return {
            "status": "completed",
            "result": result,
            "token_usage": result.get("token_usage", {}),
            "cost_estimate": result.get("cost_estimate"),
        }

    async def _execute_tool(self, request: ExecutionRequest) -> Dict[str, Any]:
        """
        Execute tool.

        Args:
            request: Execution request

        Returns:
            Execution result
        """
        from backend.app.services.unified_tool_executor import UnifiedToolExecutor

        tool_executor = UnifiedToolExecutor()
        tool_name = request.payload.get("tool_name")
        tool_inputs = request.payload.get("inputs", {})

        if not tool_name:
            raise ValueError("tool_name is required for tool execution")

        workspace_id = request.execution_context.metadata.get("workspace_id")
        if not workspace_id:
            raise ValueError("workspace_id is required in execution_context.metadata")

        execution_result = await tool_executor.execute_tool(
            tool_name=tool_name,
            arguments=tool_inputs,
            timeout=300.0,
        )

        if not execution_result.success:
            raise Exception(execution_result.error or "Tool execution failed")

        return {
            "status": "completed",
            "result": execution_result.result,
            "token_usage": {},
            "cost_estimate": None,
        }

    async def _execute_chain(self, request: ExecutionRequest) -> Dict[str, Any]:
        """
        Execute chain.

        Args:
            request: Execution request

        Returns:
            Execution result
        """
        raise NotImplementedError("Chain execution not yet implemented")

    async def _report_event(
        self,
        request_id: str,
        event_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Report execution event to Cloud.

        Args:
            request_id: Request identifier
            event_id: Event identifier
            event_type: Event type
            data: Event data
        """
        try:
            event = ExecutionEvent(
                event_id=event_id,
                request_id=request_id,
                event_type=event_type,
                data=data,
                timestamp=_utc_now().isoformat(),
            )

            message = {
                "type": "execution_event",
                "payload": event.to_dict(),
            }

            await self.websocket.send(json.dumps(message))
            logger.debug(f"Reported event: {event_id} ({event_type})")

        except Exception as e:
            logger.error(f"Failed to report event: {e}", exc_info=True)

    async def _report_usage(
        self,
        request_id: str,
        duration_ms: int,
        token_usage: Optional[Dict[str, Any]] = None,
        cost_estimate: Optional[float] = None,
    ) -> None:
        """
        Report usage metrics to Cloud.

        Args:
            request_id: Request identifier
            duration_ms: Execution duration in milliseconds
            token_usage: Token usage metrics
            cost_estimate: Cost estimate
        """
        try:
            metrics = {
                "duration_ms": duration_ms,
            }

            if token_usage:
                metrics["token_usage"] = token_usage

            if cost_estimate is not None:
                metrics["cost_estimate"] = cost_estimate

            report = UsageReport(
                request_id=request_id,
                executor_device_id=self.device_id,
                metrics=metrics,
            )

            message = {
                "type": "usage_report",
                "payload": report.to_dict(),
            }

            await self.websocket.send(json.dumps(message))
            logger.debug(f"Reported usage: {request_id}")

        except Exception as e:
            logger.error(f"Failed to report usage: {e}", exc_info=True)

    async def _report_error(self, request_id: str, error_message: str) -> None:
        """
        Report error event.

        Args:
            request_id: Request identifier
            error_message: Error message
        """
        await self._report_event(
            request_id,
            f"event_{uuid.uuid4().hex[:16]}",
            "failed",
            {"error": error_message},
        )
