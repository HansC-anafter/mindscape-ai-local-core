"""
Tasks store for managing task execution records

Tasks are derived from MindEvents and represent Pack execution states.
All task writes go through the /chat flow, ensuring single source of truth.
"""

import logging
from datetime import datetime, timezone


def _utc_now() -> datetime:
    """Return timezone-aware UTC now. Fixes Postgres timestamptz offset bug."""
    return datetime.now(timezone.utc)


from typing import List, Optional, Dict, Any

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from app.services.stores.base import StoreNotFoundError
from app.models.workspace import Task, TaskStatus

logger = logging.getLogger(__name__)


class TasksStore(PostgresStoreBase):
    """Postgres-backed store for managing task execution records."""

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
                    storyline_tags, created_at, started_at, completed_at, error
                ) VALUES (
                    :id, :workspace_id, :message_id, :execution_id, :project_id, :pack_id,
                    :task_type, :status, :params, :result, :execution_context,
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
            return self.get_task(task_id)

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
            return self.get_task(task_id)

    def list_tasks_by_workspace(
        self,
        workspace_id: Optional[str],
        status: Optional[TaskStatus] = None,
        limit: Optional[int] = None,
        exclude_cancelled: bool = False,
    ) -> List[Task]:
        """
        List tasks for a workspace

        Args:
            workspace_id: Workspace ID (None to get tasks from all workspaces)
            status: Filter by status (optional)
            limit: Maximum number of tasks to return (optional)
            exclude_cancelled: Exclude cancelled_by_user and expired tasks (default: False)

        Returns:
            List of tasks
        """
        query_parts = ["SELECT * FROM tasks WHERE 1=1"]
        params: Dict[str, Any] = {}

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        if status:
            query_parts.append("AND status = :status")
            params["status"] = status.value

        if exclude_cancelled:
            query_parts.append("AND status NOT IN (:cancelled_status, :expired_status)")
            params["cancelled_status"] = TaskStatus.CANCELLED_BY_USER.value
            params["expired_status"] = TaskStatus.EXPIRED.value

        query_parts.append("ORDER BY created_at DESC")

        if limit:
            query_parts.append("LIMIT :limit")
            params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            tasks = [self._row_to_task(row) for row in rows]

        for task in tasks:
            if task.task_type == "execution":
                task.result = None
                task.execution_context = None

        return tasks

    def list_tasks_by_thread(
        self,
        workspace_id: str,
        thread_id: str,
        status: Optional[TaskStatus] = None,
        limit: Optional[int] = None,
        exclude_cancelled: bool = False,
    ) -> List[Task]:
        """
        List tasks for a specific thread (via mind_events.message_id join)

        Args:
            workspace_id: Workspace ID
            thread_id: Thread ID
            status: Filter by status (optional)
            limit: Maximum number of tasks to return (optional)
            exclude_cancelled: Exclude cancelled_by_user and expired tasks (default: False)

        Returns:
            List of tasks
        """
        query_parts = [
            """
            SELECT t.*
            FROM tasks t
            INNER JOIN mind_events e ON e.id = t.message_id
            WHERE t.workspace_id = :workspace_id AND e.thread_id = :thread_id
            """
        ]
        params: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "thread_id": thread_id,
        }

        if status:
            query_parts.append("AND t.status = :status")
            params["status"] = status.value

        if exclude_cancelled:
            query_parts.append(
                "AND t.status NOT IN (:cancelled_status, :expired_status)"
            )
            params["cancelled_status"] = TaskStatus.CANCELLED_BY_USER.value
            params["expired_status"] = TaskStatus.EXPIRED.value

        query_parts.append("ORDER BY t.created_at DESC")

        if limit:
            query_parts.append("LIMIT :limit")
            params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_pending_tasks_by_thread(
        self, workspace_id: str, thread_id: str, exclude_cancelled: bool = True
    ) -> List[Task]:
        """
        List pending tasks for a specific thread

        Args:
            workspace_id: Workspace ID
            thread_id: Thread ID
            exclude_cancelled: Exclude cancelled_by_user and expired tasks (default: True)

        Returns:
            List of pending tasks
        """
        return self.list_tasks_by_thread(
            workspace_id=workspace_id,
            thread_id=thread_id,
            status=TaskStatus.PENDING,
            exclude_cancelled=exclude_cancelled,
        )

    def list_running_tasks_by_thread(
        self, workspace_id: str, thread_id: str
    ) -> List[Task]:
        """
        List running tasks for a specific thread

        Args:
            workspace_id: Workspace ID
            thread_id: Thread ID

        Returns:
            List of running tasks
        """
        return self.list_tasks_by_thread(
            workspace_id=workspace_id, thread_id=thread_id, status=TaskStatus.RUNNING
        )

    def list_executions_by_project(
        self, workspace_id: str, project_id: str, limit: Optional[int] = None
    ) -> List[Task]:
        """
        List execution tasks for a specific project

        Args:
            workspace_id: Workspace ID
            project_id: Project ID
            limit: Maximum number of tasks to return (optional)

        Returns:
            List of execution tasks for the project
        """
        query = """
            SELECT * FROM tasks
            WHERE workspace_id = :workspace_id
            AND project_id = :project_id
            AND task_type = 'execution'
            ORDER BY created_at DESC
        """
        params: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "project_id": project_id,
        }

        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            tasks = [self._row_to_task(row) for row in rows]

        for task in tasks:
            task.result = None
            task.execution_context = None

        return tasks

    def list_executions_by_workspace(
        self, workspace_id: str, limit: Optional[int] = None
    ) -> List[Task]:
        """
        List all Playbook execution tasks (tasks with execution_context) for a workspace

        Args:
            workspace_id: Workspace ID
            limit: Maximum number of tasks to return (optional)

        Returns:
            List of execution tasks (tasks with execution_context)
        """
        query = """
            SELECT * FROM tasks
            WHERE workspace_id = :workspace_id AND execution_context IS NOT NULL
            ORDER BY created_at DESC
        """
        params: Dict[str, Any] = {"workspace_id": workspace_id}

        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            tasks = [self._row_to_task(row) for row in rows]

        for task in tasks:
            task.result = None

        return tasks

    def list_pending_tasks(
        self, workspace_id: str, exclude_cancelled: bool = True
    ) -> List[Task]:
        """
        List pending tasks for a workspace

        Args:
            workspace_id: Workspace ID
            exclude_cancelled: Exclude cancelled_by_user and expired tasks (default: True)

        Returns:
            List of pending tasks
        """
        tasks = self.list_tasks_by_workspace(
            workspace_id=workspace_id, status=TaskStatus.PENDING
        )
        if exclude_cancelled:
            return [
                t
                for t in tasks
                if t.status not in (TaskStatus.CANCELLED_BY_USER, TaskStatus.EXPIRED)
            ]
        return tasks

    def list_running_tasks(self, workspace_id: str) -> List[Task]:
        """
        List running tasks for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            List of running tasks
        """
        return self.list_tasks_by_workspace(
            workspace_id=workspace_id, status=TaskStatus.RUNNING
        )

    def find_existing_suggestion_tasks(
        self, workspace_id: str, pack_id: str, created_within_hours: int = 1
    ) -> List[Task]:
        """
        Find existing suggestion tasks with same pack_id within time window

        Args:
            workspace_id: Workspace ID
            pack_id: Pack ID to search for
            created_within_hours: Hours to look back for existing tasks (default: 1)

        Returns:
            List of existing suggestion tasks
        """
        from datetime import timedelta

        time_threshold = _utc_now() - timedelta(hours=created_within_hours)

        query = """
            SELECT * FROM tasks
            WHERE workspace_id = :workspace_id
            AND pack_id = :pack_id
            AND task_type = :task_type
            AND status IN (:pending_status, :running_status)
            AND created_at >= :time_threshold
            ORDER BY created_at DESC
        """
        params = {
            "workspace_id": workspace_id,
            "pack_id": pack_id,
            "task_type": "suggestion",
            "pending_status": TaskStatus.PENDING.value,
            "running_status": TaskStatus.RUNNING.value,
            "time_threshold": time_threshold,
        }

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_recently_completed_tasks(
        self,
        workspace_id: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Task]:
        """
        List recently completed tasks that haven't been displayed yet

        Args:
            workspace_id: Workspace ID
            since: Only return tasks completed after this time (optional)
            limit: Maximum number of tasks to return (optional)

        Returns:
            List of recently completed tasks
        """
        query_parts = [
            """
            SELECT * FROM tasks
            WHERE workspace_id = :workspace_id
            AND status IN (:succeeded_status, :failed_status)
            AND displayed_at IS NULL
            """
        ]
        params: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "succeeded_status": TaskStatus.SUCCEEDED.value,
            "failed_status": TaskStatus.FAILED.value,
        }

        if since:
            query_parts.append("AND completed_at >= :since")
            params["since"] = since

        query_parts.append("ORDER BY completed_at DESC")

        if limit:
            query_parts.append("LIMIT :limit")
            params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_runnable_playbook_execution_tasks(
        self, workspace_id: Optional[str] = None, limit: int = 1
    ) -> List[Task]:
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type = :task_type
            AND status = :status
            """
        ]
        params: Dict[str, Any] = {
            "task_type": "playbook_execution",
            "status": TaskStatus.PENDING.value,
        }

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        query_parts.append("ORDER BY created_at ASC")
        query_parts.append("LIMIT :limit")
        params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_runnable_agent_dispatch_tasks(
        self, workspace_id: Optional[str] = None, limit: int = 5
    ) -> List[Task]:
        """List pending agent_dispatch tasks for the runner to consume."""
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type = :task_type
            AND status = :status
            """
        ]
        params: Dict[str, Any] = {
            "task_type": "agent_dispatch",
            "status": TaskStatus.PENDING.value,
        }

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        query_parts.append("ORDER BY created_at ASC")
        query_parts.append("LIMIT :limit")
        params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_running_playbook_execution_tasks(
        self, workspace_id: Optional[str] = None, limit: int = 200
    ) -> List[Task]:
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type = :task_type
            AND status = :status
            """
        ]
        params: Dict[str, Any] = {
            "task_type": "playbook_execution",
            "status": TaskStatus.RUNNING.value,
        }

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        query_parts.append("ORDER BY created_at ASC")
        query_parts.append("LIMIT :limit")
        params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def try_claim_task(self, task_id: str, runner_id: str) -> bool:
        now = _utc_now()

        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT status, execution_context
                    FROM tasks
                    WHERE id = :task_id
                """
                ),
                {"task_id": task_id},
            ).fetchone()
            if not row:
                return False

            current_status = getattr(row, "status", None)
            if current_status != TaskStatus.PENDING.value:
                return False

            existing_ctx: Dict[str, Any] = {}
            raw_ctx = getattr(row, "execution_context", None)
            if raw_ctx:
                existing_ctx = self.deserialize_json(raw_ctx, {})

            ctx = dict(existing_ctx) if isinstance(existing_ctx, dict) else {}
            ctx["runner_id"] = runner_id
            ctx["heartbeat_at"] = now.isoformat()

            result = conn.execute(
                text(
                    """
                    UPDATE tasks
                    SET status = :running_status,
                        started_at = :started_at,
                        execution_context = :execution_context
                    WHERE id = :task_id AND status = :pending_status
                """
                ),
                {
                    "running_status": TaskStatus.RUNNING.value,
                    "pending_status": TaskStatus.PENDING.value,
                    "started_at": now,
                    "execution_context": self.serialize_json(ctx),
                    "task_id": task_id,
                },
            )
            return result.rowcount == 1

    def update_task_heartbeat(
        self, task_id: str, runner_id: Optional[str] = None
    ) -> bool:
        """Update heartbeat and return True if the task should be aborted.

        Returns:
            should_abort: True if the DB task status indicates the runner
            should stop (cancelled, expired, or externally failed).
        """
        now = _utc_now()
        now_iso = now.isoformat()
        task = self.get_task(task_id)
        if not task:
            return True  # task deleted — abort

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        ctx = dict(ctx)
        ctx["heartbeat_at"] = now_iso
        if runner_id:
            ctx["runner_id"] = runner_id

        try:
            exec_mode = (ctx.get("execution_mode") or "").strip().lower()
        except Exception:
            exec_mode = ""

        should_revive = False
        if runner_id and exec_mode == "runner":
            try:
                if (
                    task.status == TaskStatus.FAILED
                    and (task.error or "") == "Execution interrupted by server restart"
                ):
                    hb = None
                    ca = getattr(task, "completed_at", None)
                    try:
                        hb_raw = ctx.get("heartbeat_at")
                        hb = (
                            datetime.fromisoformat(hb_raw)
                            if isinstance(hb_raw, str) and hb_raw.strip()
                            else None
                        )
                    except Exception:
                        hb = None
                    try:
                        ca_dt = ca if isinstance(ca, datetime) else None
                    except Exception:
                        ca_dt = None
                    if hb and ca_dt and hb > ca_dt:
                        should_revive = True
                    elif hb and not ca_dt:
                        should_revive = True
            except Exception:
                should_revive = False

        if should_revive:
            ctx["status"] = "running"
            self.update_task(
                task_id,
                execution_context=ctx,
                status=TaskStatus.RUNNING,
                error=None,
            )
        else:
            self.update_task(task_id, execution_context=ctx)
        logger.info("Updated heartbeat for task %s (runner=%s)", task_id, runner_id)

        # ── Abort detection ──────────────────────────────────────
        # Re-read status after write to catch external cancellation.
        if should_revive:
            return False  # just revived — keep running

        abort_statuses = {
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.EXPIRED,
        }
        # Handle string-based statuses as fallback
        status_str = str(task.status).lower() if task.status else ""
        if task.status in abort_statuses:
            logger.warning(
                "Task %s status=%s — signalling abort to runner", task_id, task.status
            )
            return True
        if (
            task.status == TaskStatus.FAILED
            and (task.error or "") != "Execution interrupted by server restart"
        ):
            logger.warning(
                "Task %s externally failed (%s) — signalling abort", task_id, task.error
            )
            return True
        return False

    def reap_zombie_tasks(
        self,
        heartbeat_ttl_minutes: int = 10,
        no_heartbeat_ttl_minutes: int = 30,
    ) -> List[str]:
        """Reap zombie tasks that have stale or missing heartbeats.

        A task is considered zombie if:
        - It has a heartbeat older than heartbeat_ttl_minutes, OR
        - It has no heartbeat and has been running for > no_heartbeat_ttl_minutes

        Args:
            heartbeat_ttl_minutes: Max age of heartbeat before task is reaped
            no_heartbeat_ttl_minutes: Max running time without any heartbeat

        Returns:
            List of reaped task IDs
        """
        from datetime import timedelta

        now = _utc_now()
        tasks = self.list_tasks_by_workspace(
            workspace_id=None, status=TaskStatus.RUNNING
        )

        reaped_ids: List[str] = []
        for task in tasks:
            ctx = (
                task.execution_context
                if isinstance(task.execution_context, dict)
                else {}
            )
            hb_raw = ctx.get("heartbeat_at")
            hb_dt = None
            if hb_raw and isinstance(hb_raw, str):
                try:
                    hb_dt = datetime.fromisoformat(hb_raw)
                    if hb_dt.tzinfo is None:
                        hb_dt = hb_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    hb_dt = None

            is_zombie = False
            reason = ""

            if hb_dt:
                age = now - hb_dt
                if age > timedelta(minutes=heartbeat_ttl_minutes):
                    is_zombie = True
                    reason = (
                        f"Zombie: heartbeat stale for {int(age.total_seconds())}s "
                        f"(threshold {heartbeat_ttl_minutes}m)"
                    )
            else:
                # No heartbeat — check how long the task has been running
                started = task.started_at or task.created_at
                if started:
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    age = now - started
                    if age > timedelta(minutes=no_heartbeat_ttl_minutes):
                        is_zombie = True
                        reason = (
                            f"Zombie: no heartbeat, running for {int(age.total_seconds())}s "
                            f"(threshold {no_heartbeat_ttl_minutes}m)"
                        )

            if is_zombie:
                try:
                    self.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=reason,
                        completed_at=now,
                    )
                    reaped_ids.append(task.id)
                    logger.warning("Reaped zombie task %s: %s", task.id, reason)
                except Exception as e:
                    logger.error("Failed to reap zombie task %s: %s", task.id, e)

        if reaped_ids:
            logger.info("Zombie reaper: reaped %d tasks", len(reaped_ids))
        else:
            logger.debug("Zombie reaper: no zombie tasks found")

        return reaped_ids

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task by setting its status to CANCELLED_BY_USER.

        Works on PENDING or RUNNING tasks. For RUNNING tasks, the runner
        will detect the cancellation via the heartbeat abort check.

        Args:
            task_id: Task ID to cancel

        Returns:
            True if the task was cancelled, False if not found or
            already in a terminal state.
        """
        task = self.get_task(task_id)
        if not task:
            return False

        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False

        now = _utc_now()
        try:
            self.update_task_status(
                task_id=task_id,
                status=TaskStatus.CANCELLED_BY_USER,
                error="Cancelled by user",
                completed_at=now,
            )
            logger.info("Task %s cancelled by user", task_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel task %s: %s", task_id, e)
            return False

    def ensure_runner_heartbeats_table(self) -> None:
        """Create runner_heartbeats table if it does not exist."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS runner_heartbeats (
                        runner_id TEXT PRIMARY KEY,
                        heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )

    def upsert_runner_heartbeat(self, runner_id: str) -> None:
        """Record that a runner is alive (called every poll cycle)."""
        try:
            with self.transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO runner_heartbeats (runner_id, heartbeat_at)
                        VALUES (:runner_id, NOW())
                        ON CONFLICT (runner_id)
                        DO UPDATE SET heartbeat_at = NOW()
                        """
                    ),
                    {"runner_id": runner_id},
                )
        except Exception:
            # Table might not exist yet; create it and retry.
            try:
                self.ensure_runner_heartbeats_table()
                with self.transaction() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO runner_heartbeats (runner_id, heartbeat_at)
                            VALUES (:runner_id, NOW())
                            ON CONFLICT (runner_id)
                            DO UPDATE SET heartbeat_at = NOW()
                            """
                        ),
                        {"runner_id": runner_id},
                    )
            except Exception:
                pass

    def has_active_runner(self, max_age_seconds: float = 120.0) -> bool:
        """Check if any runner has sent a heartbeat within max_age_seconds."""
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT COUNT(*) AS cnt
                        FROM runner_heartbeats
                        WHERE heartbeat_at > NOW() - INTERVAL '1 second' * :max_age
                        """
                    ),
                    {"max_age": max_age_seconds},
                ).fetchone()
                if row:
                    cnt = (
                        row[0] if not hasattr(row, "_mapping") else row._mapping["cnt"]
                    )
                    return int(cnt) > 0
        except Exception:
            pass
        return False

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
            storyline_tags=storyline_tags,
            created_at=self._coerce_datetime(row.created_at),
            started_at=self._coerce_datetime(row.started_at),
            completed_at=self._coerce_datetime(row.completed_at),
            error=row.error,
        )
