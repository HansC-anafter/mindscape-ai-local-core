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
        success=status in ("completed", "dispatched_to_ide"),
        output=raw.get("output", ""),
        duration_seconds=duration,
        tool_calls=raw.get("tool_calls", []),
        files_modified=raw.get("files_modified", []),
        files_created=raw.get("files_created", []),
        error=raw.get("error"),
        exit_code=0 if status in ("completed", "dispatched_to_ide") else 1,
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
        Check if Antigravity is reachable via the configured transport.

        - ws: Check if ws_manager has an active connection
        - polling: Always available (tasks are queued)
        - sampling: Check if mcp_server is injected
        """
        if self._available_cache is not None:
            return self._available_cache

        # Lazy-resolve ws_manager from global singleton
        self._resolve_ws_manager()

        if self.strategy == "ws":
            available = self.ws_manager is not None and (
                hasattr(self.ws_manager, "has_connections")
                and self.ws_manager.has_connections()
            )
            # Auto-fallback to polling if WS has no connections
            if not available and self.ws_manager is not None:
                logger.info(
                    "WS manager exists but no connections, "
                    "falling back to polling strategy"
                )
                self.strategy = "polling"
                available = True
        elif self.strategy == "polling":
            # Polling is always available — tasks go to the pending queue
            available = True
        elif self.strategy == "sampling":
            available = self.sampling_gate is not None and self.mcp_server is not None
        else:
            logger.warning(f"Unknown strategy: {self.strategy}")
            available = False

        self._available_cache = available

        if available:
            self._version_cache = "ide-connected"
            logger.info(f"Antigravity adapter available via '{self.strategy}' strategy")
        else:
            logger.warning(
                f"Antigravity adapter not available via '{self.strategy}' strategy"
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

        Routes to the appropriate transport strategy.
        """
        logger.info(
            f"AntigravityAdapter.execute called for workspace={request.workspace_id} task={request.task[:50]}"
        )
        # Reset availability cache on each execution
        self._available_cache = None

        # Lazy-resolve ws_manager
        self._resolve_ws_manager()
        logger.info(
            f"AntigravityAdapter: ws_manager resolved? {self.ws_manager is not None}"
        )
        if self.ws_manager:
            logger.info(
                f"AntigravityAdapter: ws_manager has connections? {self.ws_manager.has_connections()}"
            )

        self.log_execution_start(request)
        execution_id = str(uuid.uuid4())

        try:
            logger.info(f"AntigravityAdapter: strategy={self.strategy}")
            if self.strategy == "ws":
                response = await self._execute_via_ws(request, execution_id)
            elif self.strategy == "polling":
                response = await self._execute_via_polling(request, execution_id)
            elif self.strategy == "sampling":
                response = await self._execute_via_sampling(request, execution_id)
            else:
                response = AgentResponse(
                    success=False,
                    output="",
                    duration_seconds=0,
                    error=f"Unknown transport strategy: {self.strategy}",
                )
        except Exception as e:
            logger.exception("Antigravity execution failed with exception")
            response = AgentResponse(
                success=False,
                output="",
                duration_seconds=0,
                error=str(e),
                exit_code=-1,
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
        Queue task for REST Polling pickup by IDE.

        Flow:
          1. Build dispatch payload
          2. Store as 'pending' in dispatch_store
          3. Return immediately with status='running'
        """
        start_time = time.monotonic()
        payload = build_dispatch_payload(request, execution_id)

        if self.dispatch_store:
            await self.dispatch_store.create_pending_task(
                execution_id=execution_id,
                workspace_id=request.workspace_id or "",
                payload=payload,
            )

        # Polling is async by nature — return immediately with running status
        return AgentResponse(
            success=True,  # Task queued successfully
            output="Task queued for IDE pickup via polling.",
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
