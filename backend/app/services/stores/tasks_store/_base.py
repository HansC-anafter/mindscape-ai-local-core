"""
TasksStore CRUD core — create, get, update operations + private helpers.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from app.services.stores.base import StoreNotFoundError
from app.models.workspace import Task, TaskStatus

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return timezone-aware UTC now. Fixes Postgres timestamptz offset bug."""
    return datetime.now(timezone.utc)


class TasksStoreCrudMixin:
    """CRUD operations and private helpers for TasksStore."""

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
        with self.transaction() as conn:
            project_id = task.project_id
            if not project_id and task.execution_context:
                project_id = task.execution_context.get("project_id")
            if not project_id and task.params:
                project_id = task.params.get("project_id")

            query = text(
                """
                INSERT INTO tasks (
                    id, workspace_id, message_id, execution_id, project_id, pack_id,
                    task_type, status, params, result, execution_context,
                    meeting_session_id,
                    storyline_tags, created_at, started_at, completed_at, error
                ) VALUES (
                    :id, :workspace_id, :message_id, :execution_id, :project_id, :pack_id,
                    :task_type, :status, :params, :result, :execution_context,
                    :meeting_session_id,
                    :storyline_tags, :created_at, :started_at, :completed_at, :error
                )
            """
            )
            params = {
                "id": task.id,
                "workspace_id": task.workspace_id,
                "message_id": task.message_id,
                "execution_id": task.execution_id,
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
            if key in ["params", "result", "storyline_tags"]:
                updates.append(f"{key} = :{key}")
                params[key] = self.serialize_json(value)
            elif key in ["status"]:
                updates.append(f"{key} = :{key}")
                params[key] = value.value if hasattr(value, "value") else value
            elif key in ["started_at", "completed_at", "created_at"]:
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

            logger.info("Updated task %s", task_id)
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

        return Task(
            id=row.id,
            workspace_id=row.workspace_id,
            message_id=row.message_id,
            execution_id=row.execution_id,
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
            started_at=self._coerce_datetime(row.started_at),
            completed_at=self._coerce_datetime(row.completed_at),
            error=row.error,
        )


def _publish_terminal_event(
    task_id: str, status_raw: str, task_obj: Optional["Task"] = None
) -> None:
    """Fire-and-forget publish to activity stream on terminal status."""
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
        import asyncio

        from backend.app.services.cache.async_redis import publish_meeting_chunk

        ws_id = task_obj.workspace_id if task_obj else ""
        if not ws_id:
            return
        coro = publish_meeting_chunk(
            ws_id,
            {
                "type": "task_completed",
                "task_id": task_id,
                "execution_id": task_obj.execution_id if task_obj else None,
                "status": status_raw,
                "pack_id": task_obj.pack_id if task_obj else None,
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            pass  # no event loop
    except Exception:
        pass  # non-fatal
