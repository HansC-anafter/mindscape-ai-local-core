from .base import *
from .payload import build_dispatch_payload


class PollingExecutionMixin:

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
        """Queue task for REST polling pickup and wait for the persisted result."""
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
