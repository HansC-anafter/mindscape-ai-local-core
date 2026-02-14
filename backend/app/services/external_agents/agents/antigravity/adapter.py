"""
Antigravity Agent Adapter

Dispatches coding tasks to the Antigravity IDE agent via a transport-agnostic
Dispatch Contract. Supports WebSocket Push (primary), REST Polling (fallback),
and MCP Sampling (experimental).

Unlike CLI-based adapters (e.g. OpenClawAdapter), this adapter communicates
over the network to an IDE instance rather than spawning a subprocess.
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.services.external_agents.core.base_adapter import (
    BaseAgentAdapter,
    AgentRequest,
    AgentResponse,
)

logger = logging.getLogger(__name__)


# ============================================================
#  Dispatch Contract types
# ============================================================


def build_dispatch_payload(
    request: AgentRequest,
    execution_id: str,
) -> Dict[str, Any]:
    """
    Build a transport-agnostic dispatch payload from an AgentRequest.

    This is the unified contract shared across all transport layers
    (WebSocket, REST Polling, MCP Sampling).
    """
    return {
        "execution_id": execution_id,
        "workspace_id": request.workspace_id or "",
        "agent_id": "antigravity",
        "task": request.task,
        "allowed_tools": request.allowed_tools,
        "max_duration": request.max_duration_seconds,
        "context": {
            "project_id": request.project_id,
            "intent_id": request.intent_id,
            "lens_id": request.lens_id,
            "sandbox_path": request.sandbox_path,
        },
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }


def parse_dispatch_response(
    raw: Dict[str, Any],
    start_time: float,
) -> AgentResponse:
    """
    Parse a transport-agnostic dispatch response into AgentResponse.
    """
    status = raw.get("status", "failed")
    duration = raw.get("duration_seconds", time.monotonic() - start_time)

    return AgentResponse(
        success=status == "completed",
        output=raw.get("output", ""),
        duration_seconds=duration,
        tool_calls=raw.get("tool_calls", []),
        files_modified=raw.get("files_modified", []),
        files_created=raw.get("files_created", []),
        error=raw.get("error"),
        exit_code=0 if status == "completed" else 1,
        agent_metadata={
            "transport": raw.get("metadata", {}).get("transport", "unknown"),
            "execution_id": raw.get("execution_id", ""),
            "governance": raw.get("governance", {}),
        },
    )


# ============================================================
#  AntigravityAdapter
# ============================================================


class AntigravityAdapter(BaseAgentAdapter):
    """
    Antigravity IDE Agent Adapter.

    Dispatches coding tasks to an Antigravity instance running inside
    the user's IDE via a transport-agnostic Dispatch Contract.

    Transport strategies (configurable via agent_config):
      - 'ws': WebSocket Push (default, lowest latency)
      - 'polling': REST Polling (fallback when WS is unavailable)
      - 'sampling': MCP Sampling (experimental, depends on IDE routing)

    Usage:
        adapter = AntigravityAdapter()
        if await adapter.is_available():
            response = await adapter.execute(request)
    """

    AGENT_NAME = "antigravity"
    AGENT_VERSION = "1.0.0"

    # Antigravity-specific denied tools
    ALWAYS_DENIED_TOOLS = [
        "system.run",
        "gateway",
        "docker",
    ]

    # Default timeout for waiting for ack from IDE (seconds)
    ACK_TIMEOUT: float = 30.0

    # Default timeout for waiting for result from IDE (seconds)
    RESULT_TIMEOUT: float = 600.0

    def __init__(
        self,
        strategy: str = "ws",
        ws_manager: Optional[Any] = None,
        sampling_gate: Optional[Any] = None,
        mcp_server: Optional[Any] = None,
        dispatch_store: Optional[Any] = None,
    ):
        """
        Initialize Antigravity adapter.

        Args:
            strategy: Transport strategy ('ws', 'polling', 'sampling')
            ws_manager: WebSocket connection manager (Phase 2)
            sampling_gate: SamplingGate instance (for 'sampling' strategy)
            mcp_server: MCP server instance (for 'sampling' strategy)
            dispatch_store: Store for pending/dispatched tasks (for 'polling')
        """
        super().__init__()
        self.strategy = strategy
        self.ws_manager = ws_manager
        self.sampling_gate = sampling_gate
        self.mcp_server = mcp_server
        self.dispatch_store = dispatch_store

    async def is_available(self) -> bool:
        """
        Check if Antigravity IDE agent is reachable.

        Available when:
        1. An active WS connection from the IDE exists, OR
        2. MCP REST polling endpoints are enabled (tasks queue for pull)
        """
        if self._available_cache is not None:
            return self._available_cache

        # Lazy-resolve ws_manager from global singleton
        self._resolve_ws_manager()

        ws_connected = (
            self.ws_manager is not None
            and hasattr(self.ws_manager, "has_connections")
            and self.ws_manager.has_connections()
        )

        # MCP REST polling is always enabled — tasks queue as PendingTask
        # and are pulled via GET /api/v1/mcp/agent/pending
        mcp_polling_enabled = True

        available = ws_connected or mcp_polling_enabled

        self._available_cache = available

        if ws_connected:
            self._version_cache = "ide-connected"
            logger.info("Antigravity IDE client connected via WebSocket")
        elif mcp_polling_enabled:
            self._version_cache = "mcp-polling"
            logger.info("Antigravity available via MCP REST polling")
        else:
            logger.warning(
                "NO_CLIENT_CONNECTED: Antigravity IDE agent is not reachable. "
                "No active WebSocket connection from IDE."
            )

        return available

    def _resolve_ws_manager(self) -> None:
        """
        Lazily resolve ws_manager from the global AgentDispatchManager.

        This is needed because the registry creates adapters with obj()
        (no args), so ws_manager starts as None. We resolve it at
        execution time to avoid circular import issues.
        """
        if self.ws_manager is not None:
            return

        try:
            from backend.app.routes.agent_websocket import (
                get_agent_dispatch_manager,
            )

            self.ws_manager = get_agent_dispatch_manager()
        except ImportError:
            logger.debug("agent_websocket module not available")

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """
        Execute a task by dispatching to the Antigravity IDE agent.

        Transport priority:
          1. WebSocket Push (if IDE client is connected)
          2. REST Polling fallback (queue as PendingTask for MCP pull)
        """
        logger.info(
            f"AntigravityAdapter.execute called for workspace={request.workspace_id} "
            f"task={request.task[:50]}"
        )
        # Reset availability cache on each execution
        self._available_cache = None

        # Lazy-resolve ws_manager
        self._resolve_ws_manager()

        execution_id = str(uuid.uuid4())
        has_client = self.ws_manager is not None and self.ws_manager.has_connections()

        if has_client:
            # Primary path: dispatch via WebSocket
            self.log_execution_start(request)
            try:
                response = await self._execute_via_ws(request, execution_id)
                if response.agent_metadata is None:
                    response.agent_metadata = {}
                response.agent_metadata["executor_location"] = "ide"
            except Exception as e:
                logger.exception("Antigravity WS execution failed with exception")
                response = AgentResponse(
                    success=False,
                    output="",
                    duration_seconds=0,
                    error=str(e),
                    exit_code=-1,
                    agent_metadata={"executor_location": "ide"},
                )
            self.log_execution_end(response)
            return response

        # No WS client connected — fail fast.
        # Polling tools (mindscape_task_next) have been removed;
        # tasks can only be executed via WS push.
        logger.warning(
            "No IDE agent connected via WebSocket. "
            "Task cannot be executed. Start the WS bridge: "
            "scripts/start_ws_bridge.sh "
            f"(execution_id={execution_id})"
        )
        response = AgentResponse(
            success=False,
            output="",
            duration_seconds=0,
            error=(
                "No Antigravity IDE agent connected. "
                "Start the WS bridge (scripts/start_ws_bridge.sh) "
                "to enable task dispatch."
            ),
            exit_code=-1,
            agent_metadata={"executor_location": "none"},
        )
        self.log_execution_end(response)
        return response

    # ============================================================
    #  Strategy: WebSocket Push
    # ============================================================

    async def _execute_via_ws(
        self,
        request: AgentRequest,
        execution_id: str,
    ) -> AgentResponse:
        """
        Dispatch task via WebSocket Push.

        Flow:
          1. Build dispatch payload
          2. Send via ws_manager
          3. Wait for ack (with ACK_TIMEOUT)
          4. Wait for result (with RESULT_TIMEOUT)
        """
        start_time = time.monotonic()
        payload = build_dispatch_payload(request, execution_id)

        if not self.ws_manager:
            return AgentResponse(
                success=False,
                output="",
                duration_seconds=0,
                error="WebSocket manager not initialized",
            )

        # Send dispatch via WebSocket
        ws_message = {
            "type": "dispatch",
            **payload,
        }

        try:
            # Send and wait for result
            # ws_manager.dispatch_and_wait handles:
            #   - sending the dispatch message
            #   - waiting for ack
            #   - waiting for result (or timeout)
            raw_result = await asyncio.wait_for(
                self.ws_manager.dispatch_and_wait(
                    workspace_id=request.workspace_id or "",
                    message=ws_message,
                    execution_id=execution_id,
                ),
                timeout=request.max_duration_seconds or self.RESULT_TIMEOUT,
            )

            raw_result.setdefault("metadata", {})["transport"] = "ws_push"
            return parse_dispatch_response(raw_result, start_time)

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            logger.warning(
                f"WS dispatch timed out after {elapsed:.1f}s " f"(exec={execution_id})"
            )
            # Return running status — IDE may still complete and call /agent/result
            return AgentResponse(
                success=False,
                output="",
                duration_seconds=elapsed,
                error=f"Task dispatched but timed out after {elapsed:.0f}s. "
                f"IDE may still be executing (execution_id={execution_id}).",
                exit_code=-1,
                agent_metadata={
                    "transport": "ws_push",
                    "execution_id": execution_id,
                    "status": "running",
                },
            )

    # ============================================================
    #  Strategy: REST Polling
    # ============================================================

    async def _execute_via_polling(
        self,
        request: AgentRequest,
        execution_id: str,
    ) -> AgentResponse:
        """
        Queue task for REST Polling pickup by MCP Gateway.

        Flow:
          1. Build dispatch payload
          2. Enqueue as PendingTask via AgentDispatchManager
          3. Return immediately with status='running'
        """
        start_time = time.monotonic()
        payload = build_dispatch_payload(request, execution_id)

        if self.ws_manager is not None:
            from app.routes.agent_websocket import PendingTask

            pending = PendingTask(
                execution_id=execution_id,
                workspace_id=request.workspace_id or "",
                payload=payload,
            )
            self.ws_manager._enqueue_pending(pending)
            logger.info(
                f"Task {execution_id} enqueued as PendingTask for MCP polling "
                f"(workspace={request.workspace_id})"
            )
        else:
            logger.error(f"Cannot enqueue task {execution_id}: ws_manager is None")

        # Polling is async by nature — return immediately with running status
        return AgentResponse(
            success=True,  # Task queued successfully
            output="Task queued for IDE pickup via MCP polling.",
            duration_seconds=time.monotonic() - start_time,
            exit_code=0,
            agent_metadata={
                "transport": "polling",
                "execution_id": execution_id,
                "status": "pending",
                "poll_endpoint": f"/api/v1/mcp/agent/pending?surface=antigravity",
            },
        )

    # ============================================================
    #  Strategy: MCP Sampling (experimental)
    # ============================================================

    async def _execute_via_sampling(
        self,
        request: AgentRequest,
        execution_id: str,
    ) -> AgentResponse:
        """
        Dispatch task via MCP Sampling createMessage().

        Uses SamplingGate.with_fallback with template 'agent_task_dispatch'.
        Falls back to polling if sampling is unavailable.
        """
        start_time = time.monotonic()

        if not self.sampling_gate or not self.mcp_server:
            logger.warning("Sampling not available, falling back to polling strategy")
            return await self._execute_via_polling(request, execution_id)

        from backend.app.services.sampling_gate import SamplingGate

        prompt_params = SamplingGate.build_agent_task_dispatch_prompt(
            task=request.task,
            execution_id=execution_id,
            workspace_id=request.workspace_id or "",
            allowed_tools=request.allowed_tools,
            context={
                "project_id": request.project_id,
                "intent_id": request.intent_id,
                "lens_id": request.lens_id,
            },
        )

        async def sampling_fn():
            return await self.mcp_server.createMessage(**prompt_params)

        async def fallback_fn():
            # Fall back to polling when sampling fails
            return await self._execute_via_polling(request, execution_id)

        result = await self.sampling_gate.with_fallback(
            sampling_fn=sampling_fn,
            fallback_fn=fallback_fn,
            workspace_id=request.workspace_id or "",
            template="agent_task_dispatch",
        )

        if result.source == "sampling" and result.data:
            # Parse sampling response
            raw_result = self._parse_sampling_result(
                result.data,
                execution_id,
            )
            raw_result.setdefault("metadata", {})["transport"] = "mcp_sampling"
            return parse_dispatch_response(raw_result, start_time)

        # If fallback returned an AgentResponse directly
        if isinstance(result.data, AgentResponse):
            return result.data

        return AgentResponse(
            success=False,
            output="",
            duration_seconds=time.monotonic() - start_time,
            error=f"Sampling chain failed: {result.error}",
            agent_metadata={
                "transport": "mcp_sampling",
                "execution_id": execution_id,
                "sampling_source": result.source,
            },
        )

    def _parse_sampling_result(
        self,
        sampling_response: Any,
        execution_id: str,
    ) -> Dict[str, Any]:
        """
        Parse MCP Sampling response into dispatch response format.
        """
        try:
            # MCP createMessage returns content with role + content
            content = sampling_response
            if hasattr(content, "content"):
                content = content.content
            if hasattr(content, "text"):
                content = content.text
            if isinstance(content, dict):
                content = content.get("text", str(content))

            # Try to parse as JSON
            try:
                parsed = json.loads(content) if isinstance(content, str) else content
                if isinstance(parsed, dict):
                    parsed["execution_id"] = execution_id
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

            # Raw text response
            output_text = str(content)
            return {
                "execution_id": execution_id,
                "status": "completed",
                "output": output_text,
                "governance": {
                    "output_hash": hashlib.sha256(output_text.encode()).hexdigest(),
                },
            }

        except Exception as e:
            logger.error(f"Failed to parse sampling result: {e}")
            return {
                "execution_id": execution_id,
                "status": "failed",
                "error": f"Failed to parse sampling response: {e}",
            }
