"""
TasksStore CRUD core — create, get, update operations + private helpers.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from app.services.stores.base import StoreNotFoundError
from app.models.workspace import Task, TaskStatus
from backend.app.services.runner_topology import (
    BROWSER_LOCAL_QUEUE_PARTITION,
    DEFAULT_LOCAL_QUEUE_PARTITION,
    VISION_LOCAL_QUEUE_PARTITION,
    canonical_queue_partition_for_pack,
    merge_runner_metadata_into_context,
    normalize_queue_partition,
    resolve_installed_playbook_runner_metadata,
)
from backend.app.services.task_admission_service import (
    ADMISSION_DEFERRED_REASON,
    TASK_ADMISSION_SERVICE,
)
from backend.app.services.task_payload_budget import apply_task_payload_budget
from backend.app.services.meeting_command_status_sync import (
    sync_meeting_command_from_task_safely,
)
from backend.app.services.run_attempts_store import RunAttemptsStore
from backend.app.services.task_events_store import TaskEventsStore
from backend.app.services.task_projection_builder import TaskProjectionBuilder

logger = logging.getLogger(__name__)

_RUNNER_TASK_TYPES = {"playbook_execution", "tool_execution"}
_TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED_BY_USER.value,
    TaskStatus.EXPIRED.value,
}


def _normalize_frontier_updates_for_status(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Keep scheduler frontier fields consistent with authoritative task status."""
    normalized = dict(kwargs)
    status_val = normalized.get("status")
    if status_val is None:
        return normalized

    status_raw = status_val.value if hasattr(status_val, "value") else str(status_val)
    status_raw = str(status_raw).strip().lower()

    if status_raw in _TERMINAL_TASK_STATUSES:
        normalized["frontier_state"] = "done"
        normalized["frontier_enqueued_at"] = None
        normalized["runner_id"] = None
        normalized["heartbeat_at"] = None
    elif status_raw == TaskStatus.RUNNING.value:
        normalized["frontier_state"] = "running"
        normalized["frontier_enqueued_at"] = None

    return normalized


def _utc_now() -> datetime:
    """Return timezone-aware UTC now. Fixes Postgres timestamptz offset bug."""
    return datetime.now(timezone.utc)


def _coerce_task_status(status: Any) -> str:
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


def _parse_resume_after(raw_value: Any) -> Optional[datetime]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw_value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_queue_shard(value: Any) -> Optional[str]:
    return normalize_queue_partition(value, fallback=None)


def _clean_queue_shard(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _resolve_queue_shard(
    pack_id: str, execution_context: Optional[Dict[str, Any]] = None
) -> str:
    explicit_queue_shard = None
    if isinstance(execution_context, dict):
        explicit_queue_shard = _normalize_queue_shard(
            execution_context.get("queue_partition")
        ) or _clean_queue_shard(
            execution_context.get("queue_shard")
        )
    if explicit_queue_shard:
        return explicit_queue_shard
    spec_metadata = resolve_installed_playbook_runner_metadata(pack_id)
    if spec_metadata:
        metadata_queue_shard = _normalize_queue_shard(
            spec_metadata.get("queue_partition")
        ) or _normalize_queue_shard(
            spec_metadata.get("queue_shard")
        )
        if metadata_queue_shard:
            return metadata_queue_shard
    if isinstance(execution_context, dict):
        resource_class = str(execution_context.get("resource_class") or "").strip().lower()
        if resource_class == "browser":
            return BROWSER_LOCAL_QUEUE_PARTITION
        if resource_class == "compute":
            return VISION_LOCAL_QUEUE_PARTITION
    return canonical_queue_partition_for_pack(pack_id)


def _resolve_hydrated_queue_shard(
    pack_id: str, execution_context: Optional[Dict[str, Any]] = None
) -> str:
    if isinstance(execution_context, dict):
        resource_class = str(execution_context.get("resource_class") or "").strip().lower()
        if resource_class == "browser":
            return BROWSER_LOCAL_QUEUE_PARTITION
        if resource_class == "compute":
            return VISION_LOCAL_QUEUE_PARTITION
    return _resolve_queue_shard(pack_id, execution_context)


def _enrich_runner_task_context(task: Task) -> None:
    if task.task_type not in _RUNNER_TASK_TYPES:
        return
    playbook_code = ""
    if isinstance(task.execution_context, dict):
        playbook_code = str(task.execution_context.get("playbook_code") or "").strip()
    playbook_code = playbook_code or str(task.pack_id or "").strip()
    if not playbook_code:
        return

    metadata = resolve_installed_playbook_runner_metadata(playbook_code)
    if not metadata:
        return
    task.execution_context = merge_runner_metadata_into_context(
        task.execution_context,
        metadata,
        playbook_code=playbook_code,
    )


def _resolve_concurrency_key(
    execution_context: Optional[Dict[str, Any]], pack_id: str
) -> Optional[str]:
    try:
        from backend.app.runner.concurrency import _resolve_lock_key

        return _resolve_lock_key(execution_context, pack_id)
    except Exception:
        return None


def _derive_blocked_payload(
    execution_context: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(execution_context, dict):
        return None

    payload: Dict[str, Any] = {}

    dependency_hold = execution_context.get("dependency_hold")
    if isinstance(dependency_hold, dict) and dependency_hold:
        payload["dependency_hold"] = dependency_hold

    if execution_context.get("runner_skip_lock_key"):
        payload["lock_key"] = execution_context.get("runner_skip_lock_key")
    if execution_context.get("runner_skip_conflict_lock_key"):
        payload["conflicting_lock_key"] = execution_context.get(
            "runner_skip_conflict_lock_key"
        )

    return payload or None


def _derive_scheduler_fields(task: Task) -> Dict[str, Any]:
    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    now = _utc_now()
    status_value = _coerce_task_status(task.status)
    explicit_fields = getattr(task, "model_fields_set", set()) or set()

    next_eligible_at = (
        (task.next_eligible_at if "next_eligible_at" in explicit_fields else None)
        or _parse_resume_after(ctx.get("resume_after"))
        or task.created_at
        or now
    )

    blocked_reason = (task.blocked_reason if "blocked_reason" in explicit_fields else None) or ctx.get(
        "runner_skip_reason"
    )
    if not blocked_reason and isinstance(ctx.get("dependency_hold"), dict):
        blocked_reason = "dependency_hold"

    blocked_payload = task.blocked_payload if "blocked_payload" in explicit_fields else None
    if blocked_payload is None:
        blocked_payload = _derive_blocked_payload(ctx)

    queue_shard = (
        task.queue_shard if "queue_shard" in explicit_fields and task.queue_shard else None
    ) or _resolve_queue_shard(task.pack_id, ctx)
    concurrency_key = (
        task.concurrency_key
        if "concurrency_key" in explicit_fields and task.concurrency_key
        else None
    ) or _resolve_concurrency_key(
        ctx, task.pack_id
    )

    frontier_state = (
        task.frontier_state
        if "frontier_state" in explicit_fields and task.frontier_state
        else None
    )
    if not frontier_state:
        if status_value == TaskStatus.RUNNING.value:
            frontier_state = "running"
        elif status_value in _TERMINAL_TASK_STATUSES:
            frontier_state = "done"
        elif (
            blocked_reason
            or next_eligible_at > now
            or task.task_type not in _RUNNER_TASK_TYPES
        ):
            frontier_state = "cold"
        else:
            frontier_state = "ready"

    frontier_enqueued_at = (
        task.frontier_enqueued_at
        if "frontier_enqueued_at" in explicit_fields
        else None
    )
    if frontier_enqueued_at is None and frontier_state == "ready":
        frontier_enqueued_at = task.created_at or now

    return {
        "next_eligible_at": next_eligible_at,
        "blocked_reason": blocked_reason,
        "blocked_payload": blocked_payload,
        "queue_shard": queue_shard,
        "concurrency_key": concurrency_key,
        "frontier_state": frontier_state,
        "frontier_enqueued_at": frontier_enqueued_at,
    }


class TasksStoreCrudMixin:
    """CRUD operations and private helpers for TasksStore."""

    def _enqueue_runner_task_after_commit(self, task: Task) -> None:
        """Best-effort Redis enqueue after the DB transaction has committed."""
        if os.getenv(
            "LOCAL_CORE_TASK_POST_COMMIT_ENQUEUE_ENABLED",
            "true",
        ).lower() in {"0", "false", "no", "off"}:
            return
        if task.status != TaskStatus.PENDING:
            return
        if task.task_type not in ("playbook_execution", "tool_execution"):
            return
        if getattr(task, "frontier_state", "ready") != "ready":
            return
        if getattr(task, "next_eligible_at", None) and task.next_eligible_at > _utc_now():
            return

        try:
            from backend.app.services.stores.redis.runner_queue_store import (
                RedisRunnerQueueStore,
            )
            from backend.app.services.host_resources.route_identity_projection import (
                build_route_identity_projection,
            )

            q_store = RedisRunnerQueueStore(
                pack_id=normalize_queue_partition(
                    getattr(task, "queue_shard", None),
                    fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
                )
            )
            success = q_store.enqueue_task_sync(
                task.id,
                route_identity=build_route_identity_projection(task),
            )
            if not success:
                logger.warning(
                    f"[DB Bridge] Failed post-commit enqueue for task {task.id}. "
                    "Will rely on Reaper Sync."
                )
        except Exception as e:
            logger.error(
                f"[DB Bridge] Exception during post-commit enqueue for task {task.id}: {e}"
            )

    def _sync_playbook_execution_status(
        self,
        conn,
        execution_id: Optional[str],
        status: TaskStatus,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not execution_id:
            return
        is_auto_resumed = bool(
            execution_context and execution_context.get("auto_resumed")
        )
        if status in (
            TaskStatus.FAILED,
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.EXPIRED,
        ):
            # Skip auto-resume placeholder failures to avoid clobbering retries
            # that were already queued by the lifecycle hook.
            if is_auto_resumed:
                return
            target_status = "failed"
        elif status == TaskStatus.SUCCEEDED:
            target_status = "done"
        elif status == TaskStatus.PENDING:
            target_status = "queued"
        elif status == TaskStatus.RUNNING:
            target_status = "running"
        else:
            return
        try:
            params = {
                "status": target_status,
                "updated_at": _utc_now(),
                "id": execution_id,
            }
            if target_status == "failed":
                conn.execute(
                    text(
                        """
                        UPDATE playbook_executions
                        SET status = :status, updated_at = :updated_at
                        WHERE id = :id
                          AND NOT EXISTS (
                            SELECT 1 FROM tasks
                            WHERE execution_id = :id
                              AND status IN ('pending', 'running')
                          )
                        """
                    ),
                    params,
                )
            elif target_status == "queued":
                conn.execute(
                    text(
                        """
                        UPDATE playbook_executions
                        SET status = :status, updated_at = :updated_at
                        WHERE id = :id
                          AND status NOT IN ('done', 'failed')
                          AND NOT EXISTS (
                            SELECT 1 FROM tasks
                            WHERE execution_id = :id
                              AND status = 'running'
                          )
                        """
                    ),
                    params,
                )
            elif target_status == "running":
                conn.execute(
                    text(
                        """
                        UPDATE playbook_executions
                        SET status = :status, updated_at = :updated_at
                        WHERE id = :id
                          AND status NOT IN ('done', 'failed')
                        """
                    ),
                    params,
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE playbook_executions
                        SET status = :status, updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    params,
                )
        except Exception as e:
            logger.warning(
                "Failed to sync playbook_executions status for %s: %s",
                execution_id,
                e,
            )

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path
        self._run_attempts_store_instance: Optional[RunAttemptsStore] = None
        self._task_events_store_instance: Optional[TaskEventsStore] = None
        self._task_projection_builder_instance: Optional[TaskProjectionBuilder] = None

    def _task_events_store(self) -> TaskEventsStore:
        store = self._task_events_store_instance
        if store is None:
            store = TaskEventsStore(db_role=self.db_role)
            self._task_events_store_instance = store
        return store

    def _run_attempts_store(self) -> RunAttemptsStore:
        store = self._run_attempts_store_instance
        if store is None:
            store = RunAttemptsStore(db_role=self.db_role)
            self._run_attempts_store_instance = store
        return store

    def _task_projection_builder(self) -> TaskProjectionBuilder:
        builder = self._task_projection_builder_instance
        if builder is None:
            builder = TaskProjectionBuilder(db_role=self.db_role)
            self._task_projection_builder_instance = builder
        return builder

    def _run_id_for_task(self, task_id: str, execution_id: Optional[str]) -> str:
        return execution_id or task_id

    def _record_run_control_from_task(
        self,
        conn,
        task: Task,
        *,
        status: Optional[str] = None,
    ) -> str:
        run_id = self._run_id_for_task(task.id, task.execution_id)
        self._run_attempts_store().upsert_run(
            run_id=run_id,
            execution_id=task.execution_id or task.id,
            workspace_id=task.workspace_id,
            task_id=task.id,
            pack_id=task.pack_id,
            status=status or _coerce_task_status(task.status),
            started_at=task.started_at,
            completed_at=task.completed_at,
            conn=conn,
        )
        return run_id

    def _record_task_control_event(
        self,
        conn,
        *,
        task_id: str,
        workspace_id: str,
        event_type: str,
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
        run_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        summary: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> str:
        return self._task_events_store().record_task_event(
            task_id=task_id,
            workspace_id=workspace_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            run_id=run_id,
            attempt_id=attempt_id,
            summary=summary,
            payload=payload,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
            conn=conn,
        )

    def _refresh_task_projection(self, conn, task_id: str) -> None:
        self._task_projection_builder().upsert_task_summary_from_task_id(
            task_id,
            conn=conn,
        )

    def _record_latest_attempt_completion(
        self,
        conn,
        *,
        task_id: str,
        status: str,
        completed_at: Optional[datetime] = None,
        error_summary: Optional[str] = None,
    ) -> Optional[str]:
        return self._run_attempts_store().complete_latest_attempt_for_task(
            task_id=task_id,
            status=status,
            completed_at=completed_at,
            error_summary=error_summary,
            conn=conn,
        )

    def _record_task_claim(
        self,
        conn,
        *,
        task_id: str,
        runner_id: str,
        started_at: datetime,
    ) -> Optional[str]:
        row = conn.execute(
            text(
                """
                SELECT id, workspace_id, execution_id, pack_id, status
                FROM tasks
                WHERE id = :task_id
                """
            ),
            {"task_id": task_id},
        ).fetchone()
        if not row:
            return None
        mapping = row._mapping if hasattr(row, "_mapping") else None
        workspace_id = mapping["workspace_id"] if mapping is not None else row[1]
        execution_id = mapping["execution_id"] if mapping is not None else row[2]
        pack_id = mapping["pack_id"] if mapping is not None else row[3]
        status = mapping["status"] if mapping is not None else row[4]
        run_id = self._run_id_for_task(task_id, execution_id)
        self._run_attempts_store().upsert_run(
            run_id=run_id,
            execution_id=execution_id or task_id,
            workspace_id=workspace_id,
            task_id=task_id,
            pack_id=pack_id,
            status=status,
            started_at=started_at,
            conn=conn,
        )
        attempt_id = self._run_attempts_store().create_attempt(
            run_id=run_id,
            task_id=task_id,
            runner_id=runner_id,
            status=status,
            started_at=started_at,
            idempotency_key=(
                f"task:{task_id}:runner:{runner_id}:claim:{started_at.isoformat()}"
            ),
            conn=conn,
        )
        self._record_task_control_event(
            conn,
            task_id=task_id,
            workspace_id=workspace_id,
            event_type="task.claimed",
            from_status=TaskStatus.PENDING.value,
            to_status=status,
            run_id=run_id,
            attempt_id=attempt_id,
            payload={"runner_id": runner_id},
            idempotency_key=f"task:{task_id}:claimed:{attempt_id}",
            occurred_at=started_at,
        )
        self._refresh_task_projection(conn, task_id)
        return attempt_id

    def create_task(self, task: Task) -> Task:
        """
        Create a new task record

        Args:
            task: Task model instance

        Returns:
            Created task
        """
        _enrich_runner_task_context(task)
        scheduler_fields = _derive_scheduler_fields(task)
        for key, value in scheduler_fields.items():
            setattr(task, key, value)

        admission_decision = TASK_ADMISSION_SERVICE.evaluate_on_create(self, task)
        if not admission_decision.allow:
            task.execution_context = admission_decision.execution_context
            task.next_eligible_at = admission_decision.next_eligible_at or task.next_eligible_at
            task.blocked_reason = ADMISSION_DEFERRED_REASON
            task.blocked_payload = admission_decision.blocked_payload
            task.frontier_state = "cold"
            task.frontier_enqueued_at = None
            task.queue_shard = admission_decision.queue_shard or task.queue_shard

        with self.transaction() as conn:
            project_id = task.project_id
            if not project_id and task.execution_context:
                project_id = task.execution_context.get("project_id")
            if not project_id and task.params:
                project_id = task.params.get("project_id")

            query = text(
                """
                INSERT INTO tasks (
                    id, workspace_id, message_id, execution_id, parent_execution_id,
                    project_id, pack_id,
                    task_type, status, params, result, execution_context,
                    meeting_session_id,
                    storyline_tags, created_at, next_eligible_at, blocked_reason,
                    blocked_payload, queue_shard, concurrency_key, frontier_state,
                    frontier_enqueued_at, started_at, completed_at, error
                ) VALUES (
                    :id, :workspace_id, :message_id, :execution_id, :parent_execution_id,
                    :project_id, :pack_id,
                    :task_type, :status, :params, :result, :execution_context,
                    :meeting_session_id,
                    :storyline_tags, :created_at, :next_eligible_at, :blocked_reason,
                    :blocked_payload, :queue_shard, :concurrency_key, :frontier_state,
                    :frontier_enqueued_at, :started_at, :completed_at, :error
                )
            """
            )
            # Auto-inject parent_execution_id from ContextVar if not set
            resolved_parent_id = getattr(task, "parent_execution_id", None)
            if not resolved_parent_id:
                try:
                    from backend.app.services.parameter_adapter.context import (
                        active_parent_execution_id,
                    )
                    ctx_parent = active_parent_execution_id.get()
                    # Pre-mortem guard: prevent self-parenting
                    if ctx_parent and ctx_parent != task.execution_id:
                        resolved_parent_id = ctx_parent
                except Exception:
                    pass  # ContextVar not available — safe to ignore

            task_params = apply_task_payload_budget("params", task.params)
            task_result = apply_task_payload_budget("result", task.result)
            task_execution_context = apply_task_payload_budget(
                "execution_context",
                task.execution_context,
            )
            task_blocked_payload = apply_task_payload_budget(
                "blocked_payload",
                task.blocked_payload,
            )

            params = {
                "id": task.id,
                "workspace_id": task.workspace_id,
                "message_id": task.message_id,
                "execution_id": task.execution_id,
                "parent_execution_id": resolved_parent_id,
                "project_id": project_id,
                "pack_id": task.pack_id,
                "task_type": task.task_type,
                "status": task.status.value,
                "params": self.serialize_json(task_params),
                "result": self.serialize_json(task_result),
                "execution_context": (
                    self.serialize_json(task_execution_context)
                    if task_execution_context
                    else None
                ),
                "meeting_session_id": task.meeting_session_id,
                "storyline_tags": self.serialize_json(task.storyline_tags),
                "created_at": task.created_at,
                "next_eligible_at": task.next_eligible_at,
                "blocked_reason": task.blocked_reason,
                "blocked_payload": self.serialize_json(task_blocked_payload),
                "queue_shard": task.queue_shard,
                "concurrency_key": task.concurrency_key,
                "frontier_state": task.frontier_state,
                "frontier_enqueued_at": task.frontier_enqueued_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "error": task.error,
            }
            conn.execute(query, params)
            if task.task_type in ("playbook_execution", "tool_execution"):
                self._sync_playbook_execution_status(
                    conn,
                    task.execution_id,
                    task.status,
                    task_execution_context,
                )
            task.parent_execution_id = resolved_parent_id
            run_id = self._record_run_control_from_task(conn, task)
            self._record_task_control_event(
                conn,
                task_id=task.id,
                workspace_id=task.workspace_id,
                event_type="task.created",
                to_status=task.status.value,
                run_id=run_id,
                payload={
                    "pack_id": task.pack_id,
                    "task_type": task.task_type,
                    "queue_shard": task.queue_shard,
                },
                idempotency_key=f"task:{task.id}:created",
                occurred_at=task.created_at,
            )
            self._refresh_task_projection(conn, task.id)
            logger.info(
                "Created task: %s (workspace: %s, pack: %s)",
                task.id,
                task.workspace_id,
                task.pack_id,
            )

        sync_meeting_command_from_task_safely(task)
        self._enqueue_runner_task_after_commit(task)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get task by ID

        Args:
            task_id: Task ID

        Returns:
            Task model or None if not found
        """
        with self.get_connection() as conn:
            query = text("SELECT * FROM tasks WHERE id = :task_id")
            row = conn.execute(query, {"task_id": task_id}).fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def get_task_by_execution_id(self, execution_id: str) -> Optional[Task]:
        """
        Get task by execution_id

        Args:
            execution_id: Execution ID

        Returns:
            Task model or None if not found
        """
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM tasks
                    WHERE execution_id = :execution_id
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                ),
                {"execution_id": execution_id},
            ).fetchone()
            if not row:
                row = conn.execute(
                    text(
                        """
                        SELECT * FROM tasks
                        WHERE id = :execution_id
                        ORDER BY created_at DESC
                        LIMIT 1
                    """
                    ),
                    {"execution_id": execution_id},
                ).fetchone()
                if not row:
                    return None
            return self._row_to_task(row)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> Task:
        """
        Update task status and related fields

        Args:
            task_id: Task ID
            status: New status
            result: Task result (optional)
            error: Error message (optional)
            started_at: Start timestamp (optional)
            completed_at: Completion timestamp (optional)

        Returns:
            Updated task when requested

        Raises:
            StoreNotFoundError: If task not found
        """
        updates = ["status = :status"]
        params: Dict[str, Any] = {"status": status.value, "task_id": task_id}

        if status == TaskStatus.RUNNING:
            updates.extend(
                [
                    "blocked_reason = NULL",
                    "blocked_payload = NULL",
                    "frontier_state = :frontier_state",
                    "frontier_enqueued_at = NULL",
                ]
            )
            params["frontier_state"] = "running"
        elif status.value in _TERMINAL_TASK_STATUSES:
            updates.extend(
                [
                    "blocked_reason = NULL",
                    "blocked_payload = NULL",
                    "runner_id = NULL",
                    "heartbeat_at = NULL",
                    "frontier_state = :frontier_state",
                    "frontier_enqueued_at = NULL",
                ]
            )
            params["frontier_state"] = "done"

        if result is not None:
            updates.append("result = :result")
            params["result"] = self.serialize_json(
                apply_task_payload_budget("result", result)
            )

        if error is not None:
            updates.append("error = :error")
            params["error"] = error

        if started_at is not None:
            updates.append("started_at = :started_at")
            params["started_at"] = started_at

        if completed_at is not None:
            updates.append("completed_at = :completed_at")
            params["completed_at"] = completed_at

        with self.transaction() as conn:
            existing_row = conn.execute(
                text(
                    """
                    SELECT
                        status,
                        pack_id,
                        task_type,
                        created_at,
                        next_eligible_at,
                        blocked_reason,
                        frontier_state,
                        frontier_enqueued_at
                    FROM tasks
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).fetchone()
            existing_status = None
            if existing_row:
                existing_status = (
                    existing_row._mapping["status"]
                    if hasattr(existing_row, "_mapping")
                    else existing_row[0]
                )
            query = text(f"UPDATE tasks SET {', '.join(updates)} WHERE id = :task_id")
            result_row = conn.execute(query, params)
            if result_row.rowcount == 0:
                raise StoreNotFoundError(f"Task not found: {task_id}")

            # Sync playbook_executions status (best effort)
            try:
                row = conn.execute(
                    text(
                        "SELECT execution_id, execution_context FROM tasks WHERE id = :task_id"
                    ),
                    {"task_id": task_id},
                ).fetchone()
                if row:
                    execution_id = (
                        row._mapping["execution_id"]
                        if hasattr(row, "_mapping")
                        else row[0]
                    )
                    execution_context = self.deserialize_json(
                        row._mapping["execution_context"]
                        if hasattr(row, "_mapping")
                        else row[1]
                    )
                    self._sync_playbook_execution_status(
                        conn, execution_id, status, execution_context
                    )
            except Exception:
                pass

            control_row = conn.execute(
                text(
                    """
                    SELECT workspace_id, execution_id, pack_id, started_at, completed_at
                    FROM tasks
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).fetchone()
            if control_row:
                mapping = (
                    control_row._mapping
                    if hasattr(control_row, "_mapping")
                    else None
                )
                workspace_id = (
                    mapping["workspace_id"] if mapping is not None else control_row[0]
                )
                execution_id = (
                    mapping["execution_id"] if mapping is not None else control_row[1]
                )
                pack_id = mapping["pack_id"] if mapping is not None else control_row[2]
                persisted_started_at = (
                    mapping["started_at"] if mapping is not None else control_row[3]
                )
                persisted_completed_at = (
                    mapping["completed_at"] if mapping is not None else control_row[4]
                )
                event_time = completed_at or started_at or _utc_now()
                run_id = self._run_id_for_task(task_id, execution_id)
                self._run_attempts_store().upsert_run(
                    run_id=run_id,
                    execution_id=execution_id or task_id,
                    workspace_id=workspace_id,
                    task_id=task_id,
                    pack_id=pack_id,
                    status=status.value,
                    started_at=persisted_started_at,
                    completed_at=persisted_completed_at,
                    conn=conn,
                )
                attempt_id = None
                if status.value in _TERMINAL_TASK_STATUSES:
                    attempt_id = self._record_latest_attempt_completion(
                        conn,
                        task_id=task_id,
                        status=status.value,
                        completed_at=persisted_completed_at or completed_at,
                        error_summary=error,
                    )
                self._record_task_control_event(
                    conn,
                    task_id=task_id,
                    workspace_id=workspace_id,
                    event_type="task.status_changed",
                    from_status=existing_status,
                    to_status=status.value,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    summary=error,
                    payload={"has_result": result is not None},
                    idempotency_key=(
                        f"task:{task_id}:status:{status.value}:{event_time.isoformat()}"
                    ),
                    occurred_at=event_time,
                )
                self._refresh_task_projection(conn, task_id)

            logger.info("Updated task %s status to %s", task_id, status.value)
            updated_task = self.get_task(task_id)

        sync_meeting_command_from_task_safely(updated_task)
        # Activity stream: push terminal status change
        _publish_terminal_event(task_id, status.value, updated_task)

        return updated_task

    def update_task(
        self,
        task_id: str,
        execution_context: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        *,
        return_updated: bool = True,
        **kwargs,
    ) -> Optional[Task]:
        """
        Update task fields

        Args:
            task_id: Task ID
            execution_context: Execution context dict to update
            **kwargs: Other fields to update

        Returns:
            Updated task

        Raises:
            StoreNotFoundError: If task not found
        """
        kwargs = _normalize_frontier_updates_for_status(kwargs)

        updates = []
        params: Dict[str, Any] = {"task_id": task_id}

        if execution_context is not None:
            updates.append("execution_context = :execution_context")
            params["execution_context"] = self.serialize_json(
                apply_task_payload_budget("execution_context", execution_context)
            )
            if project_id is None and execution_context.get("project_id"):
                project_id = execution_context.get("project_id")

        if project_id is not None:
            updates.append("project_id = :project_id")
            params["project_id"] = project_id

        for key, value in kwargs.items():
            if key in ["params", "result", "storyline_tags", "blocked_payload"]:
                updates.append(f"{key} = :{key}")
                if key in ["params", "result", "blocked_payload"]:
                    value = apply_task_payload_budget(key, value)
                params[key] = self.serialize_json(value)
            elif key in ["status"]:
                updates.append(f"{key} = :{key}")
                params[key] = value.value if hasattr(value, "value") else value
            elif key in [
                "started_at",
                "completed_at",
                "created_at",
                "next_eligible_at",
                "frontier_enqueued_at",
                "heartbeat_at",
            ]:
                updates.append(f"{key} = :{key}")
                params[key] = value
            else:
                updates.append(f"{key} = :{key}")
                params[key] = value

        if not updates:
            return self.get_task(task_id)

        with self.transaction() as conn:
            existing_row = conn.execute(
                text(
                    """
                    SELECT
                        status,
                        pack_id,
                        task_type,
                        created_at,
                        next_eligible_at,
                        blocked_reason,
                        frontier_state,
                        frontier_enqueued_at
                    FROM tasks
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).fetchone()
            existing_status = None
            existing_mapping = None
            if existing_row:
                existing_mapping = (
                    existing_row._mapping if hasattr(existing_row, "_mapping") else None
                )
                existing_status = (
                    existing_mapping["status"]
                    if existing_mapping is not None
                    else existing_row[0]
                )
            if execution_context is not None and existing_row:
                explicit_update_keys = set(kwargs.keys())
                status_source = kwargs.get("status", existing_status)
                status_raw = _coerce_task_status(status_source)
                existing_task_type = (
                    existing_mapping["task_type"]
                    if existing_mapping is not None
                    else existing_row[2]
                )
                if (
                    existing_task_type in _RUNNER_TASK_TYPES
                    and status_raw == TaskStatus.PENDING.value
                ):
                    now = _utc_now()
                    existing_next_eligible_at = self._coerce_datetime(
                        existing_mapping["next_eligible_at"]
                        if existing_mapping is not None
                        else existing_row[4]
                    )
                    effective_next_eligible_at = existing_next_eligible_at
                    parsed_resume_after = _parse_resume_after(
                        execution_context.get("resume_after")
                    )
                    if (
                        parsed_resume_after is not None
                        and "next_eligible_at" not in explicit_update_keys
                    ):
                        updates.append("next_eligible_at = :next_eligible_at")
                        params["next_eligible_at"] = parsed_resume_after
                        effective_next_eligible_at = parsed_resume_after

                    existing_blocked_reason = (
                        existing_mapping["blocked_reason"]
                        if existing_mapping is not None
                        else existing_row[5]
                    )
                    effective_blocked_reason = existing_blocked_reason
                    derived_blocked_reason = execution_context.get("runner_skip_reason")
                    if (
                        not derived_blocked_reason
                        and isinstance(execution_context.get("dependency_hold"), dict)
                    ):
                        derived_blocked_reason = "dependency_hold"
                    if (
                        derived_blocked_reason
                        and "blocked_reason" not in explicit_update_keys
                    ):
                        updates.append("blocked_reason = :blocked_reason")
                        params["blocked_reason"] = derived_blocked_reason
                        effective_blocked_reason = derived_blocked_reason

                    if effective_blocked_reason:
                        derived_frontier_state = "cold"
                    elif effective_next_eligible_at and effective_next_eligible_at > now:
                        derived_frontier_state = "cold"
                    else:
                        derived_frontier_state = "ready"

                    if "frontier_state" not in explicit_update_keys:
                        updates.append("frontier_state = :frontier_state")
                        params["frontier_state"] = derived_frontier_state

                    if "frontier_enqueued_at" not in explicit_update_keys:
                        existing_frontier_enqueued_at = self._coerce_datetime(
                            existing_mapping["frontier_enqueued_at"]
                            if existing_mapping is not None
                            else existing_row[7]
                        )
                        existing_created_at = self._coerce_datetime(
                            existing_mapping["created_at"]
                            if existing_mapping is not None
                            else existing_row[3]
                        )
                        if derived_frontier_state == "ready":
                            frontier_enqueued_at = (
                                existing_frontier_enqueued_at
                                or existing_created_at
                                or now
                            )
                        else:
                            frontier_enqueued_at = None
                        updates.append("frontier_enqueued_at = :frontier_enqueued_at")
                        params["frontier_enqueued_at"] = frontier_enqueued_at
            query = text(f"UPDATE tasks SET {', '.join(updates)} WHERE id = :task_id")
            result_row = conn.execute(query, params)
            if result_row.rowcount == 0:
                raise StoreNotFoundError(f"Task not found: {task_id}")

            # Sync playbook_executions status when task status is set.
            try:
                status_val = kwargs.get("status")
                if status_val is not None:
                    status_obj = (
                        status_val
                        if isinstance(status_val, TaskStatus)
                        else TaskStatus(status_val)
                    )
                    row = conn.execute(
                        text("SELECT execution_id FROM tasks WHERE id = :task_id"),
                        {"task_id": task_id},
                    ).fetchone()
                    execution_id = None
                    if row:
                        execution_id = (
                            row._mapping["execution_id"]
                            if hasattr(row, "_mapping")
                            else row[0]
                        )
                    self._sync_playbook_execution_status(
                        conn, execution_id, status_obj, execution_context
                    )
            except Exception:
                pass

            status_val = kwargs.get("status")
            projection_keys = {
                "status",
                "started_at",
                "completed_at",
                "error",
                "pack_id",
                "task_type",
                "queue_shard",
            }
            should_refresh_projection = (
                project_id is not None
                or bool(projection_keys.intersection(kwargs.keys()))
            )
            if status_val is not None:
                status_raw = (
                    status_val.value if hasattr(status_val, "value") else str(status_val)
                )
                control_row = conn.execute(
                    text(
                        """
                        SELECT workspace_id, execution_id, pack_id, started_at, completed_at, error
                        FROM tasks
                        WHERE id = :task_id
                        """
                    ),
                    {"task_id": task_id},
                ).fetchone()
                if control_row:
                    mapping = (
                        control_row._mapping
                        if hasattr(control_row, "_mapping")
                        else None
                    )
                    workspace_id = (
                        mapping["workspace_id"]
                        if mapping is not None
                        else control_row[0]
                    )
                    execution_id = (
                        mapping["execution_id"]
                        if mapping is not None
                        else control_row[1]
                    )
                    pack_id = (
                        mapping["pack_id"] if mapping is not None else control_row[2]
                    )
                    persisted_started_at = (
                        mapping["started_at"] if mapping is not None else control_row[3]
                    )
                    persisted_completed_at = (
                        mapping["completed_at"]
                        if mapping is not None
                        else control_row[4]
                    )
                    persisted_error = (
                        mapping["error"] if mapping is not None else control_row[5]
                    )
                    event_time = persisted_completed_at or persisted_started_at or _utc_now()
                    run_id = self._run_id_for_task(task_id, execution_id)
                    self._run_attempts_store().upsert_run(
                        run_id=run_id,
                        execution_id=execution_id or task_id,
                        workspace_id=workspace_id,
                        task_id=task_id,
                        pack_id=pack_id,
                        status=status_raw,
                        started_at=persisted_started_at,
                        completed_at=persisted_completed_at,
                        conn=conn,
                    )
                    attempt_id = None
                    if status_raw in _TERMINAL_TASK_STATUSES:
                        attempt_id = self._record_latest_attempt_completion(
                            conn,
                            task_id=task_id,
                            status=status_raw,
                            completed_at=persisted_completed_at,
                            error_summary=persisted_error,
                        )
                    self._record_task_control_event(
                        conn,
                        task_id=task_id,
                        workspace_id=workspace_id,
                        event_type="task.status_changed",
                        from_status=existing_status,
                        to_status=status_raw,
                        run_id=run_id,
                        attempt_id=attempt_id,
                        summary=persisted_error,
                        payload={"source": "update_task"},
                        idempotency_key=(
                            f"task:{task_id}:update_status:{status_raw}:{event_time.isoformat()}"
                        ),
                        occurred_at=event_time,
                    )
                    should_refresh_projection = True
            if should_refresh_projection:
                self._refresh_task_projection(conn, task_id)

            logger.debug("Updated task %s", task_id)
            updated_task = self.get_task(task_id) if return_updated else None

        if updated_task is not None:
            sync_meeting_command_from_task_safely(updated_task)
        # Activity stream: push terminal status change
        status_val = kwargs.get("status")
        if status_val is not None:
            raw = status_val.value if hasattr(status_val, "value") else str(status_val)
            _publish_terminal_event(task_id, raw, updated_task)

        return updated_task

    # ── Private helpers ──────────────────────────────────────────

    def _coerce_datetime(self, value: Optional[Any]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return self.from_isoformat(value)

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task model"""
        execution_context = None
        try:
            raw_ctx = getattr(row, "execution_context", None)
            if raw_ctx:
                execution_context = self.deserialize_json(raw_ctx)
        except Exception:
            execution_context = None

        storyline_tags = []
        try:
            raw_tags = getattr(row, "storyline_tags", None)
            if raw_tags:
                storyline_tags = self.deserialize_json(raw_tags, [])
        except Exception:
            storyline_tags = []

        project_id = getattr(row, "project_id", None)
        blocked_payload = None
        try:
            raw_blocked_payload = getattr(row, "blocked_payload", None)
            if raw_blocked_payload is not None:
                blocked_payload = self.deserialize_json(raw_blocked_payload, None)
        except Exception:
            blocked_payload = None

        return Task(
            id=row.id,
            workspace_id=row.workspace_id,
            message_id=row.message_id,
            execution_id=row.execution_id,
            parent_execution_id=getattr(row, "parent_execution_id", None),
            project_id=project_id,
            pack_id=row.pack_id,
            task_type=row.task_type,
            status=TaskStatus(row.status),
            params=self.deserialize_json(row.params, {}),
            result=self.deserialize_json(row.result),
            execution_context=execution_context,
            meeting_session_id=getattr(row, "meeting_session_id", None),
            storyline_tags=storyline_tags,
            created_at=self._coerce_datetime(row.created_at),
            next_eligible_at=self._coerce_datetime(
                getattr(row, "next_eligible_at", None)
            )
            or self._coerce_datetime(row.created_at)
            or _utc_now(),
            blocked_reason=getattr(row, "blocked_reason", None),
            blocked_payload=blocked_payload,
            queue_shard=(
                normalize_queue_partition(
                    getattr(row, "queue_shard", None),
                    fallback=None,
                )
                or _resolve_hydrated_queue_shard(row.pack_id, execution_context)
            ),
            concurrency_key=getattr(row, "concurrency_key", None),
            frontier_state=getattr(row, "frontier_state", "cold") or "cold",
            frontier_enqueued_at=self._coerce_datetime(
                getattr(row, "frontier_enqueued_at", None)
            ),
            runner_id=getattr(row, "runner_id", None),
            heartbeat_at=self._coerce_datetime(getattr(row, "heartbeat_at", None)),
            started_at=self._coerce_datetime(row.started_at),
            completed_at=self._coerce_datetime(row.completed_at),
            error=row.error,
        )


def _publish_terminal_event(
    task_id: str, status_raw: str, task_obj: Optional["Task"] = None
) -> None:
    """Fire-and-forget publish to activity stream on terminal status.

    Uses sync Redis because this function is called from sync DB threads
    where asyncio event loops are not running.
    """
    _TERMINAL = {
        "completed",
        "succeeded",
        "failed",
        "cancelled",
        "cancelled_by_user",
        "expired",
    }
    if status_raw.lower() not in _TERMINAL:
        return
    try:
        import json
        import os

        ws_id = task_obj.workspace_id if task_obj else ""
        if not ws_id:
            return

        enabled = os.getenv("REDIS_ENABLED", "true").lower() == "true"
        if not enabled:
            return

        thread_id = ""
        if task_obj and task_obj.execution_context:
            thread_id = task_obj.execution_context.get("thread_id", "")
        if not thread_id and task_obj and task_obj.meeting_session_id:
            thread_id = task_obj.meeting_session_id

        payload = {
            "type": "task_completed",
            "task_id": task_id,
            "execution_id": task_obj.execution_id if task_obj else None,
            "status": status_raw,
            "pack_id": task_obj.pack_id if task_obj else None,
            "thread_id": thread_id,
        }

        channel = f"workspace:{ws_id}:stream"
        message = json.dumps(payload, ensure_ascii=False)

        # Use sync Redis — we're already in a sync thread
        from redis import Redis

        client = Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", "0")),
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            client.publish(channel, message)
        finally:
            client.close()
    except Exception:
        pass  # non-fatal
