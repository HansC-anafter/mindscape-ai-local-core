"""
Polling Runtime Adapter

Base class for runtimes dispatched via the REST Polling + DB-primary pipeline.
Concrete adapters only need to set RUNTIME_NAME and optionally override timeouts.

Architecture:
  - DB (TasksStore): source of truth for task state
  - In-memory Future: instant event notification so coroutine doesn't poll
  - submit_result() writes DB first, then resolves Future
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.services.external_agents.core.base_adapter import (
    BaseRuntimeAdapter,
    RuntimeExecRequest,
    RuntimeExecResponse,
)

logger = logging.getLogger(__name__)


def build_dispatch_payload(
    request: RuntimeExecRequest,
    execution_id: str,
    agent_id: str,
) -> Dict[str, Any]:
    """
    Build a transport-agnostic dispatch payload from a RuntimeExecRequest.

    This is the unified contract shared across all polling-based runtimes.
    """
    # Extract conversation context and thread_id from agent_config
    # These are injected by chat_orchestrator_service when routing to agent
    agent_cfg = request.agent_config or {}
    raw_inputs = agent_cfg.get("inputs")
    inputs = dict(raw_inputs) if isinstance(raw_inputs, dict) else {}
    deliverable_targets = inputs.get("deliverable_targets")
    if not isinstance(deliverable_targets, list):
        deliverable_targets = []

    payload = {
        "execution_id": execution_id,
        "workspace_id": request.workspace_id or "",
        "agent_id": agent_id,
        "task": request.task,
        "allowed_tools": request.allowed_tools,
        "max_duration": request.max_duration_seconds,
        "model": agent_cfg.get("model"),  # per-agent model hint (P1.5)
        "context": {
            "project_id": request.project_id,
            "intent_id": request.intent_id,
            "lens_id": request.lens_id,
            "auth_workspace_id": request.auth_workspace_id or request.workspace_id,
            "source_workspace_id": request.source_workspace_id or request.workspace_id,
            "sandbox_path": request.sandbox_path,
            "conversation_context": agent_cfg.get("conversation_context", ""),
            "thread_id": agent_cfg.get("thread_id", ""),
            "meeting_session_id": agent_cfg.get("meeting_session_id", ""),
            "uploaded_files": agent_cfg.get("uploaded_files", []),
            "recommended_pack_codes": agent_cfg.get("recommended_pack_codes", []),
            "file_hint": agent_cfg.get("file_hint", ""),
            "control_action": agent_cfg.get("control_action", ""),
            "inputs": inputs,
        },
        "metadata": {
            "inputs": inputs,
        },
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }

    deliverable_path = inputs.get("deliverable_path")
    if isinstance(deliverable_path, str) and deliverable_path.strip():
        cleaned_path = deliverable_path.strip()
        payload["deliverable_path"] = cleaned_path
        payload["metadata"]["deliverable_path"] = cleaned_path

    deliverable_name = inputs.get("deliverable_name")
    if isinstance(deliverable_name, str) and deliverable_name.strip():
        cleaned_name = deliverable_name.strip()
        payload["deliverable_name"] = cleaned_name
        payload["metadata"]["deliverable_name"] = cleaned_name

    if deliverable_targets:
        payload["deliverable_targets"] = deliverable_targets
        payload["metadata"]["deliverable_targets"] = deliverable_targets

    meeting_session_id = agent_cfg.get("meeting_session_id") or inputs.get(
        "meeting_session_id"
    )
    if isinstance(meeting_session_id, str) and meeting_session_id.strip():
        cleaned_session_id = meeting_session_id.strip()
        payload["meeting_session_id"] = cleaned_session_id
        payload["context"]["meeting_session_id"] = cleaned_session_id
        payload["metadata"]["meeting_session_id"] = cleaned_session_id

    return payload


class PollingRuntimeAdapter(BaseRuntimeAdapter):
    """
    Base class for runtimes dispatched via REST Polling + DB persistence.

    Subclasses only need to set RUNTIME_NAME (and optionally override timeouts).
    All dispatch lifecycle logic is handled here:
      1. Persist task to DB (source of truth)
      2. Enqueue for runner pickup
      3. Wait for result via asyncio.Future (instant event notification)
      4. On timeout, check DB for results landed after restart

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

    async def is_available(self, **kwargs) -> bool:
        """
        Check if this runtime's CLI is actually installed on the host.

        Uses shutil.which() to detect CLI binaries. Results are cached
        for 30 seconds to avoid repeated subprocess lookups.
        """
        import shutil
        import time

        now = time.monotonic()
        if (
            self._available_cache is not None
            and hasattr(self, "_available_cache_time")
            and (now - self._available_cache_time) < 30.0
        ):
            return self._available_cache

        try:
            from backend.app.routes.core.system_settings.governance_tools import (
                AGENT_CLI_MAP,
            )

            agent_info = AGENT_CLI_MAP.get(self.RUNTIME_NAME)
            if not agent_info:
                # Agent not in CLI map — cannot verify installation
                self._available_cache = False
                self._available_cache_time = now
                self._version_cache = "not-in-cli-map"
                return False

            command = agent_info["command"]
            cli_path = shutil.which(command)

            if cli_path:
                self._available_cache = True
                self._available_cache_time = now
                self._version_cache = f"cli-detected:{cli_path}"
                logger.info(f"{self.RUNTIME_NAME} CLI available at {cli_path}")
                return True

            self._available_cache = False
            self._available_cache_time = now
            self._version_cache = "cli-not-found"
            logger.debug(f"{self.RUNTIME_NAME} CLI not found (tried: {command})")
            return False

        except Exception as e:
            logger.warning(f"CLI detection failed for {self.RUNTIME_NAME}: {e}")
            self._available_cache = False
            self._available_cache_time = now
            return False

    async def execute(self, request: RuntimeExecRequest) -> RuntimeExecResponse:
        """
        Execute a task by dispatching via REST polling pipeline.

        Flow: persist to DB → enqueue → wait Future → return result
        """
        # Fail-fast: reject if RUNTIME_NAME is still the base default
        if self.RUNTIME_NAME == "polling_agent":
            return RuntimeExecResponse(
                success=False,
                output="",
                duration_seconds=0,
                error="Cannot dispatch: adapter RUNTIME_NAME not set "
                "(still using base class default).",
                exit_code=-1,
            )

        self.log_execution_start(request)
        execution_id = str(uuid.uuid4())

        try:
            response = await self._execute_via_polling(request, execution_id)
        except Exception as e:
            logger.exception(f"[{self.RUNTIME_NAME}] execution failed")
            response = RuntimeExecResponse(
                success=False,
                output="",
                duration_seconds=0,
                error=str(e),
                exit_code=-1,
            )

        self.log_execution_end(response)
        return response

    async def _execute_via_polling(
        self,
        request: RuntimeExecRequest,
        execution_id: str,
    ) -> RuntimeExecResponse:
        """
        Queue task for REST Polling pickup by runner, then wait for result.

        Flow:
          1. Build dispatch payload
          2. Persist task to DB (source of truth)
          3. Register in-memory inflight (Future for notification)
          4. Enqueue for runner pickup
          5. Wait for submit_result to resolve Future (or timeout → check DB)
        """
        from backend.app.routes.agent_websocket import (
            get_agent_dispatch_manager,
            PendingTask,
            InflightTask,
        )

        start_time = time.monotonic()
        payload = build_dispatch_payload(request, execution_id, self.RUNTIME_NAME)
        dispatch_payload = {"type": "dispatch", **payload}
        workspace_id = request.workspace_id or ""

        manager = get_agent_dispatch_manager()

        # Create a future that submit_result will resolve (event notification)
        loop = asyncio.get_event_loop()
        result_future = loop.create_future()

        # Persist task to DB (survives backend restart)
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.models.workspace import Task, TaskStatus

            payload_context = dispatch_payload.get("context") or {}
            task_record = Task(
                id=execution_id,
                workspace_id=workspace_id,
                message_id=execution_id,
                execution_id=execution_id,
                pack_id=self.RUNTIME_NAME,
                task_type="agent_dispatch",
                status=TaskStatus.PENDING,
                params=dispatch_payload,
                execution_context={
                    "thread_id": payload_context.get("thread_id"),
                    "project_id": payload_context.get("project_id"),
                    "meeting_session_id": payload_context.get("meeting_session_id"),
                    "inputs": payload_context.get("inputs") or {},
                    "agent_id": dispatch_payload.get("agent_id"),
                },
            )
            TasksStore().create_task(task_record)
            logger.info(f"[{self.RUNTIME_NAME}] Persisted task {execution_id} to DB")
        except Exception as e:
            logger.warning(
                f"[{self.RUNTIME_NAME}] Failed to persist task "
                f"{execution_id} to DB: {e}"
            )

        # Register as inflight so submit_result can find and notify the Future
        inflight = InflightTask(
            execution_id=execution_id,
            workspace_id=workspace_id,
            client_id="pending",
            result_future=result_future,
            payload=dispatch_payload,
            thread_id=(dispatch_payload.get("context") or {}).get("thread_id"),
            project_id=(dispatch_payload.get("context") or {}).get("project_id"),
        )
        manager._inflight[execution_id] = inflight

        # Enqueue for polling pickup
        pending = PendingTask(
            execution_id=execution_id,
            workspace_id=workspace_id,
            payload=dispatch_payload,
        )
        manager._enqueue_pending(pending)
        logger.info(
            f"[{self.RUNTIME_NAME}] Enqueued task {execution_id} for workspace "
            f"{workspace_id}, waiting for result..."
        )

        # Wait for runner to submit result.
        #
        # The local Future is the fast path, but another backend process may
        # land the result in DB first. Check the durable task row between wait
        # slices so cross-process completion does not stall for the full timeout.
        timeout = request.max_duration_seconds or self.RESULT_TIMEOUT
        wait_slice = max(0.1, min(float(timeout), self.WAIT_SLICE_SECONDS))
        deadline = start_time + float(timeout)

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                raw_result = await asyncio.wait_for(
                    asyncio.shield(result_future),
                    timeout=min(wait_slice, remaining),
                )
                elapsed = time.monotonic() - start_time
                return self._build_runtime_exec_response(
                    execution_id=execution_id,
                    result_data=raw_result,
                    elapsed=elapsed,
                )
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - start_time
                recovered = self._recover_response_from_db(
                    execution_id=execution_id,
                    elapsed=elapsed,
                )
                if recovered is not None:
                    manager._inflight.pop(execution_id, None)
                    return recovered

        manager._inflight.pop(execution_id, None)
        elapsed = time.monotonic() - start_time
        logger.warning(
            f"[{self.RUNTIME_NAME}] Timed out waiting for result on "
            f"{execution_id} after {elapsed:.1f}s"
        )

        recovered = self._recover_response_from_db(
            execution_id=execution_id,
            elapsed=elapsed,
        )
        if recovered is not None:
            return recovered

        return RuntimeExecResponse(
            success=False,
            output="",
            duration_seconds=elapsed,
            error=f"Task dispatched but timed out after {elapsed:.0f}s. "
            f"Runner may still be executing "
            f"(execution_id={execution_id}).",
            exit_code=-1,
            agent_metadata={
                "transport": "polling",
                "execution_id": execution_id,
                "status": "timeout",
            },
        )

    def _build_runtime_exec_response(
        self,
        *,
        execution_id: str,
        result_data: Dict[str, Any],
        elapsed: float,
        recovered_from_db: bool = False,
    ) -> RuntimeExecResponse:
        output = result_data.get("output", "")
        status = result_data.get("status", "completed")
        error = result_data.get("error")
        agent_metadata = {
            "transport": "polling",
            "execution_id": execution_id,
            "status": status,
        }
        if recovered_from_db:
            agent_metadata["recovered_from_db"] = True

        return RuntimeExecResponse(
            success=(status == "completed"),
            output=output or "Task completed.",
            duration_seconds=elapsed,
            exit_code=0 if status == "completed" else -1,
            error=error,
            agent_metadata=agent_metadata,
        )

    def _recover_response_from_db(
        self,
        *,
        execution_id: str,
        elapsed: float,
    ) -> Optional[RuntimeExecResponse]:
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.models.workspace import TaskStatus

            db_task = TasksStore().get_task(execution_id)
            if db_task and db_task.status == TaskStatus.SUCCEEDED:
                logger.info(
                    f"[{self.RUNTIME_NAME}] DB recovery: found completed "
                    f"task {execution_id}"
                )
                result_data = db_task.result or {}
                return self._build_runtime_exec_response(
                    execution_id=execution_id,
                    result_data=result_data,
                    elapsed=elapsed,
                    recovered_from_db=True,
                )
            if db_task and db_task.status == TaskStatus.FAILED:
                logger.info(
                    f"[{self.RUNTIME_NAME}] DB recovery: found failed "
                    f"task {execution_id}"
                )
                return RuntimeExecResponse(
                    success=False,
                    output="",
                    duration_seconds=elapsed,
                    exit_code=1,
                    error=db_task.error or "Task failed (recovered from DB).",
                    agent_metadata={
                        "transport": "polling",
                        "execution_id": execution_id,
                        "status": "failed",
                        "recovered_from_db": True,
                    },
                )
        except Exception as db_err:
            logger.warning(
                f"[{self.RUNTIME_NAME}] DB recovery check failed for "
                f"{execution_id}: {db_err}"
            )

        return None


# Backward compatibility alias
PollingAgentAdapter = PollingRuntimeAdapter
