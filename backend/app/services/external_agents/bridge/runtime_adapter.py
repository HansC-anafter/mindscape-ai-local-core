"""
Shared host-bridge runtime adapter.

Dispatches coding tasks to a host-side CLI surface via a transport-agnostic
Dispatch Contract. Supports WebSocket Push (primary), REST Polling (inherited
from PollingRuntimeAdapter), and MCP Sampling (experimental).

Unlike CLI-based adapters (e.g. OpenClawAdapter), this adapter communicates
over the network to a host-side bridge client rather than spawning a subprocess.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.services.external_agents.core.polling_adapter import (
    PollingRuntimeAdapter,
    build_dispatch_payload,
)
from backend.app.services.external_agents.core.base_adapter import (
    RuntimeExecRequest,
    RuntimeExecResponse,
)

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; falling back to %.2f", name, raw, default)
        return default
    if value < minimum:
        logger.warning(
            "Invalid %s=%.3f below minimum %.3f; falling back to %.2f",
            name,
            value,
            minimum,
            default,
        )
        return default
    return value


# ============================================================
#  Dispatch Contract types
# ============================================================


# build_dispatch_payload is now imported from polling_adapter


def parse_dispatch_response(
    raw: Dict[str, Any],
    start_time: float,
) -> RuntimeExecResponse:
    """
    Parse a transport-agnostic dispatch response into RuntimeExecResponse.
    """
    status = raw.get("status", "failed")
    duration = raw.get("duration_seconds", time.monotonic() - start_time)

    return RuntimeExecResponse(
        success=status in ("completed", "dispatched_to_ide"),
        output=raw.get("output", ""),
        duration_seconds=duration,
        tool_calls=raw.get("tool_calls", []),
        files_modified=raw.get("files_modified", []),
        files_created=raw.get("files_created", []),
        error=raw.get("error"),
        exit_code=0 if status in ("completed", "dispatched_to_ide") else 1,
        agent_metadata={
            **(
                raw.get("metadata")
                if isinstance(raw.get("metadata"), dict)
                else {}
            ),
            "transport": raw.get("metadata", {}).get("transport", "unknown"),
            "execution_id": raw.get("execution_id", ""),
            "governance": raw.get("governance", {}),
        },
    )


def _build_cancelled_response(
    *,
    execution_id: str,
    start_time: Optional[float] = None,
    transport: str = "unknown",
    detail: Optional[str] = None,
) -> RuntimeExecResponse:
    """Normalize cancellation into a regular failure response."""
    elapsed = 0.0 if start_time is None else max(0.0, time.monotonic() - start_time)
    message = detail or "Execution cancelled while waiting for runtime response"
    return RuntimeExecResponse(
        success=False,
        output="",
        duration_seconds=elapsed,
        error=message,
        exit_code=-1,
        agent_metadata={
            "transport": transport,
            "execution_id": execution_id,
            "status": "cancelled",
        },
    )


# ============================================================
#  HostBridgeRuntimeAdapter
# ============================================================


class HostBridgeRuntimeAdapter(PollingRuntimeAdapter):
    """
    Shared host-bridge runtime adapter.

    Dispatches coding tasks to a host-side bridge client via a
    transport-agnostic Dispatch Contract.

    Transport strategies (configurable via agent_config):
      - 'ws': WebSocket Push (default, lowest latency)
      - 'polling': REST Polling (fallback when WS is unavailable)
      - 'sampling': MCP Sampling (experimental, depends on IDE routing)

    Usage:
        adapter = HostBridgeRuntimeAdapter()
        if await adapter.is_available():
            response = await adapter.execute(request)
    """

    RUNTIME_NAME = "gemini_cli"
    RUNTIME_VERSION = "1.0.0"

    # Gemini CLI denied tools
    ALWAYS_DENIED_TOOLS = [
        "system.run",
        "gateway",
        "docker",
    ]

    # Default timeout for waiting for ack from IDE (seconds)
    ACK_TIMEOUT: float = 30.0

    # Default timeout for waiting for result from IDE (seconds)
    RESULT_TIMEOUT: float = 600.0

    # Availability cache TTLs. Positive hits can be sticky; negative hits
    # must expire quickly so reconnects are visible to retry loops.
    WS_AVAILABLE_CACHE_TTL: float = 30.0
    WS_UNAVAILABLE_CACHE_TTL: float = 1.0
    # If a surface was recently connected, tolerate a brief reconnect gap
    # before declaring the runtime unavailable for the next meeting turn.
    WS_RECONNECT_GRACE_SECONDS: float = 20.0
    WS_RECONNECT_POLL_INTERVAL: float = 1.0

    def __init__(
        self,
        strategy: str = "ws",
        ws_manager: Optional[Any] = None,
        sampling_gate: Optional[Any] = None,
        mcp_server: Optional[Any] = None,
        dispatch_store: Optional[Any] = None,
    ):
        """
        Initialize host bridge runtime adapter.

        Args:
            strategy: Transport strategy ('ws', 'polling', 'sampling')
            ws_manager: WebSocket connection manager
            sampling_gate: SamplingGate instance (for 'sampling' strategy)
            mcp_server: MCP server instance (for 'sampling' strategy)
            dispatch_store: Store for pending/dispatched tasks (for 'polling')
        """
        super().__init__(dispatch_store=dispatch_store)
        self.strategy = strategy
        self.ws_manager = ws_manager
        self.sampling_gate = sampling_gate
        self.mcp_server = mcp_server
        self.WS_RECONNECT_GRACE_SECONDS = _env_float(
            "MINDSCAPE_WS_RECONNECT_GRACE_SECONDS",
            self.WS_RECONNECT_GRACE_SECONDS,
            minimum=0.0,
        )
        self.WS_RECONNECT_POLL_INTERVAL = _env_float(
            "MINDSCAPE_WS_RECONNECT_POLL_INTERVAL",
            self.WS_RECONNECT_POLL_INTERVAL,
            minimum=0.1,
        )
        self._last_ws_connected_at: Dict[Optional[str], float] = {}

    async def is_available(self, workspace_id: str = None) -> bool:
        """
        Check if the host bridge runtime is actually connected.

        Strict transport semantics:
        - ws: True ONLY if ws_manager has active WS connections.
              Runner heartbeat alone does NOT count -- the runner
              handles playbook DB polling, not chat WS dispatch.
        - polling: True only if runners have active heartbeat.
        - sampling: True only if mcp_server is injected.
        """
        detail = self.get_availability_detail(workspace_id=workspace_id)
        return detail["available"]

    def get_availability_detail(self, workspace_id: str = None) -> dict:
        """
        Return structured availability info for API responses.

        Args:
            workspace_id: Optional workspace ID for per-workspace check.

        Returns:
            dict with keys: available (bool), transport (str|None),
            reason (str).
        """
        import time

        now = time.monotonic()
        cache_key = workspace_id  # None for global check

        # Per-workspace cache bucket
        if not hasattr(self, "_ws_avail_cache"):
            self._ws_avail_cache = {}  # Dict[Optional[str], Tuple[dict, float]]

        cached = self._ws_avail_cache.get(cache_key)
        if cached:
            cached_detail, cached_at = cached
            ttl = (
                self.WS_AVAILABLE_CACHE_TTL
                if cached_detail.get("available")
                else self.WS_UNAVAILABLE_CACHE_TTL
            )
            if (now - cached_at) < ttl:
                return cached_detail

        # Lazy-resolve ws_manager from global singleton
        self._resolve_ws_manager()

        available = False
        transport = None
        reason = "unknown"

        if self.strategy == "ws":
            ws_connected = self.ws_manager is not None and (
                hasattr(self.ws_manager, "has_connections")
                and self.ws_manager.has_connections(
                    workspace_id=workspace_id,
                    surface_type=self.RUNTIME_NAME,
                )
            )
            if ws_connected:
                self._last_ws_connected_at[cache_key] = now
                available = True
                transport = "ws"
                reason = "ws_connected"
            else:
                last_connected_at = self._last_ws_connected_at.get(cache_key)
                if (
                    last_connected_at is not None
                    and (now - last_connected_at) <= self.WS_RECONNECT_GRACE_SECONDS
                ):
                    available = True
                    transport = "ws"
                    reason = "recent_reconnect_grace"
                else:
                    available = False
                    transport = None
                    reason = "no_ws_client"
        elif self.strategy == "polling":
            available = self._has_active_polling_runners()
            transport = "polling" if available else None
            reason = "runner_heartbeat_active" if available else "no_active_runner"
        elif self.strategy == "sampling":
            available = self.sampling_gate is not None and self.mcp_server is not None
            transport = "sampling" if available else None
            reason = "mcp_server_injected" if available else "no_mcp_server"
        else:
            logger.warning(f"Unknown strategy: {self.strategy}")
            reason = f"unknown_strategy_{self.strategy}"

        detail = {
            "available": available,
            "transport": transport,
            "reason": reason,
        }

        # Store in per-workspace cache bucket
        self._ws_avail_cache[cache_key] = (detail, now)

        # Also update legacy single-slot cache for backward compat
        self._available_cache = available
        self._available_cache_time = now
        self._available_detail_cache = detail

        if available:
            self._version_cache = "runtime-connected"
            logger.info(
                "%s adapter available via '%s' transport",
                self.RUNTIME_NAME,
                transport,
            )
        else:
            logger.debug("%s adapter not available: %s", self.RUNTIME_NAME, reason)

        return detail

    def _has_active_polling_runners(self) -> bool:
        """Check if the runner container is alive via its PostgreSQL heartbeat.

        The runner writes a heartbeat to the shared PostgreSQL every poll cycle.
        We check the runner_heartbeats table for recent activity.
        """
        try:
            from backend.app.services.stores.tasks_store import TasksStore

            tasks_store = TasksStore()
            return tasks_store.has_active_runner(max_age_seconds=120.0)
        except Exception as e:
            logger.debug(f"Failed to check for active polling runners: {e}")
            return False

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

    def _has_ws_connection(self, workspace_id: Optional[str]) -> bool:
        return self.ws_manager is not None and (
            hasattr(self.ws_manager, "has_connections")
            and self.ws_manager.has_connections(
                workspace_id=workspace_id,
                surface_type=self.RUNTIME_NAME,
            )
        )

    async def _wait_for_ws_reconnect(self, workspace_id: Optional[str]) -> bool:
        if self.WS_RECONNECT_GRACE_SECONDS <= 0:
            return False

        deadline = time.monotonic() + self.WS_RECONNECT_GRACE_SECONDS
        while time.monotonic() < deadline:
            if self._has_ws_connection(workspace_id):
                self._last_ws_connected_at[workspace_id] = time.monotonic()
                return True
            await asyncio.sleep(self.WS_RECONNECT_POLL_INTERVAL)
        return self._has_ws_connection(workspace_id)

    async def execute(self, request: RuntimeExecRequest) -> RuntimeExecResponse:
        """
        Execute a task by dispatching to the host bridge.

        Routes to the appropriate transport strategy.
        """
        logger.info(
            "%s.execute called for workspace=%s task=%s",
            self.__class__.__name__,
            request.workspace_id,
            request.task[:50],
        )
        # Reset availability cache on each execution
        self._available_cache = None

        # Lazy-resolve ws_manager
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
                self._has_ws_connection(request.workspace_id or None),
            )

        self.log_execution_start(request)
        execution_id = str(uuid.uuid4())

        try:
            logger.info("%s: strategy=%s", self.__class__.__name__, self.strategy)

            if self.strategy == "ws":
                # Fail-fast: if no WS client is connected, return an
                # immediate error instead of queuing and timing out.
                workspace_id = request.workspace_id or None
                target_client_id = (request.agent_config or {}).get("target_client_id")
                ws_connected = self._has_ws_connection(workspace_id)
                if not ws_connected:
                    last_connected_at = self._last_ws_connected_at.get(workspace_id)
                    if last_connected_at is not None:
                        logger.warning(
                            "%s: WS client temporarily unavailable for workspace=%s; "
                            "waiting up to %.1fs for reconnect",
                            self.__class__.__name__,
                            workspace_id,
                            self.WS_RECONNECT_GRACE_SECONDS,
                        )
                        ws_connected = await self._wait_for_ws_reconnect(workspace_id)
                if (
                    not ws_connected
                    and target_client_id
                    and self.ws_manager is not None
                    and hasattr(self.ws_manager, "dispatch_and_wait")
                ):
                    # Runner subprocesses and non-socket-owning workers do not
                    # share the in-memory client registry with the socket-owning
                    # backend worker. In that case a direct local WS presence
                    # check is a false negative; we must still allow
                    # dispatch_and_wait() to route via cross-worker pub/sub or
                    # DB fallback to the real worker that owns the client.
                    logger.info(
                        "%s: no direct WS client detected for workspace=%s but "
                        "target_client_id=%s was provided; proceeding via "
                        "dispatch_and_wait cross-worker routing",
                        self.__class__.__name__,
                        workspace_id,
                        target_client_id,
                    )
                    ws_connected = True
                if not ws_connected:
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
                            "Run scripts/start_cli_bridge_supervisor.sh "
                            f"--surfaces {self.RUNTIME_NAME} --all "
                            "to connect the host bridge."
                        ),
                    )
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
        except asyncio.CancelledError as exc:
            logger.warning(
                "%s execution cancelled for workspace=%s: %s",
                self.RUNTIME_NAME,
                request.workspace_id,
                exc or "cancelled",
            )
            response = _build_cancelled_response(
                execution_id=execution_id,
                transport=self.strategy,
                detail=(
                    "Execution cancelled while waiting for runtime response"
                    if not str(exc)
                    else f"Execution cancelled while waiting for runtime response: {exc}"
                ),
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

    # ============================================================
    #  Strategy: WebSocket Push
    # ============================================================

    async def _execute_via_ws(
        self,
        request: RuntimeExecRequest,
        execution_id: str,
    ) -> RuntimeExecResponse:
        """
        Dispatch task via WebSocket Push.

        Flow:
          1. Build dispatch payload
          2. Send via ws_manager
          3. Wait for ack (with ACK_TIMEOUT)
          4. Wait for result (with RESULT_TIMEOUT)
        """
        start_time = time.monotonic()
        payload = build_dispatch_payload(request, execution_id, self.RUNTIME_NAME)

        if not self.ws_manager:
            return RuntimeExecResponse(
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
            target_client_id = (request.agent_config or {}).get("target_client_id")
            # Send and wait for result
            # ws_manager.dispatch_and_wait handles:
            #   - sending the dispatch message
            #   - waiting for ack
            #   - waiting for result with activity-aware timeout
            raw_result = await self.ws_manager.dispatch_and_wait(
                workspace_id=request.workspace_id or "",
                message=ws_message,
                execution_id=execution_id,
                timeout=request.max_duration_seconds or self.RESULT_TIMEOUT,
                target_client_id=target_client_id,
            )

            # Check if dispatch_and_wait returned a timeout status
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

        except asyncio.CancelledError as exc:
            logger.warning(
                "WS dispatch cancelled for exec=%s after %.1fs: %s",
                execution_id,
                time.monotonic() - start_time,
                exc or "cancelled",
            )
            detail = (
                "Execution cancelled while waiting for WS dispatch result"
                if not str(exc)
                else f"Execution cancelled while waiting for WS dispatch result: {exc}"
            )
            return _build_cancelled_response(
                execution_id=execution_id,
                start_time=start_time,
                transport="ws_push",
                detail=detail,
            )
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

    # _execute_via_polling is inherited from PollingRuntimeAdapter

    # ============================================================
    #  Strategy: MCP Sampling (experimental)
    # ============================================================

    async def _execute_via_sampling(
        self,
        request: RuntimeExecRequest,
        execution_id: str,
    ) -> RuntimeExecResponse:
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

        # If fallback returned a RuntimeExecResponse directly
        if isinstance(result.data, RuntimeExecResponse):
            return result.data

        return RuntimeExecResponse(
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
