"""
TasksStore CRUD core — create, get, update operations + private helpers.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from app.services.stores.base import StoreNotFoundError
from app.models.workspace import Task, TaskStatus
from backend.app.services.runner_topology import (
    DEFAULT_LOCAL_QUEUE_PARTITION,
    canonical_queue_partition_for_pack,
    normalize_queue_partition,
)
from backend.app.services.task_admission_service import (
    ADMISSION_DEFERRED_REASON,
    TASK_ADMISSION_SERVICE,
)

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


def _resolve_queue_shard(
    pack_id: str, execution_context: Optional[Dict[str, Any]] = None
) -> str:
    explicit_queue_shard = None
    if isinstance(execution_context, dict):
        explicit_queue_shard = _normalize_queue_shard(
            execution_context.get("queue_partition")
        ) or _normalize_queue_shard(
            execution_context.get("queue_shard")
        )
    if explicit_queue_shard:
        return explicit_queue_shard
    return canonical_queue_partition_for_pack(pack_id)


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

            q_store = RedisRunnerQueueStore(
                pack_id=normalize_queue_partition(
                    getattr(task, "queue_shard", None),
                    fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
                )
            )
            success = q_store.enqueue_task_sync(task.id)
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
        # Skip sync for auto-resume placeholder failures to avoid clobbering running retries.
        if execution_context and execution_context.get("auto_resumed"):
            return
        if status in (
            TaskStatus.FAILED,
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.EXPIRED,
        ):
            target_status = "failed"
        elif status == TaskStatus.SUCCEEDED:
            target_status = "done"
        else:
            return
        try:
            conn.execute(
                text(
                    "UPDATE playbook_executions SET status = :status, updated_at = :updated_at WHERE id = :id"
                ),
                {"status": target_status, "updated_at": _utc_now(), "id": execution_id},
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

    def create_task(self, task: Task) -> Task:
        """
        Create a new task record

        Args:
            task: Task model instance

        Returns:
            Created task
        """
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
                "params": self.serialize_json(task.params),
                "result": self.serialize_json(task.result),
                "execution_context": (
                    self.serialize_json(task.execution_context)
                    if task.execution_context
                    else None
                ),
                "meeting_session_id": task.meeting_session_id,
                "storyline_tags": self.serialize_json(task.storyline_tags),
                "created_at": task.created_at,
                "next_eligible_at": task.next_eligible_at,
                "blocked_reason": task.blocked_reason,
                "blocked_payload": self.serialize_json(task.blocked_payload),
                "queue_shard": task.queue_shard,
                "concurrency_key": task.concurrency_key,
                "frontier_state": task.frontier_state,
                "frontier_enqueued_at": task.frontier_enqueued_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "error": task.error,
            }
            conn.execute(query, params)
            logger.info(
                "Created task: %s (workspace: %s, pack: %s)",
                task.id,
                task.workspace_id,
                task.pack_id,
            )

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
            Updated task

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
                    "frontier_state = :frontier_state",
                    "frontier_enqueued_at = NULL",
                ]
            )
            params["frontier_state"] = "done"

        if result is not None:
            updates.append("result = :result")
            params["result"] = self.serialize_json(result)

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

            logger.info("Updated task %s status to %s", task_id, status.value)
            updated_task = self.get_task(task_id)

        # Activity stream: push terminal status change
        _publish_terminal_event(task_id, status.value, updated_task)

        return updated_task

    def update_task(
        self,
        task_id: str,
        execution_context: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> Task:
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
            params["execution_context"] = self.serialize_json(execution_context)
            if project_id is None and execution_context.get("project_id"):
                project_id = execution_context.get("project_id")

        if project_id is not None:
            updates.append("project_id = :project_id")
            params["project_id"] = project_id

        for key, value in kwargs.items():
            if key in ["params", "result", "storyline_tags", "blocked_payload"]:
                updates.append(f"{key} = :{key}")
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
            ]:
                updates.append(f"{key} = :{key}")
                params[key] = value
            else:
                updates.append(f"{key} = :{key}")
                params[key] = value

        if not updates:
            return self.get_task(task_id)

        with self.transaction() as conn:
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

            logger.debug("Updated task %s", task_id)
            updated_task = self.get_task(task_id)

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
            queue_shard=normalize_queue_partition(
                getattr(row, "queue_shard", None),
                fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
            ),
            concurrency_key=getattr(row, "concurrency_key", None),
            frontier_state=getattr(row, "frontier_state", "cold") or "cold",
            frontier_enqueued_at=self._coerce_datetime(
                getattr(row, "frontier_enqueued_at", None)
            ),
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
