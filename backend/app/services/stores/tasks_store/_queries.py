"""
TasksStore query mixin — all list_* and find_* read-only methods.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus

logger = logging.getLogger(__name__)


class TasksStoreQueryMixin:
    """Read-only query methods for TasksStore."""

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

        from ._base import _utc_now

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
        self,
        workspace_id: Optional[str] = None,
        limit: int = 500,
        queue_shard: Optional[str] = None,
    ) -> List[Task]:
        from datetime import timezone
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
            AND status = :status
            AND next_eligible_at <= :now
            """
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "now": datetime.now(timezone.utc),
        }

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        if queue_shard:
            query_parts.append("AND COALESCE(queue_shard, 'default') = :queue_shard")
            params["queue_shard"] = queue_shard

        query_parts.append("ORDER BY next_eligible_at ASC, created_at ASC, id ASC")
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

    def list_tasks_by_meeting_session(
        self, session_id: str, limit: int = 200
    ) -> List[Task]:
        """List tasks spawned by a specific meeting session.

        Checks the meeting_session_id column first, falling back to
        execution_context/params JSON columns for backward compatibility.
        """
        query = text(
            """
            SELECT *
            FROM tasks
            WHERE meeting_session_id = :sid
               OR execution_context->>'meeting_session_id' = :sid
               OR params->>'meeting_session_id' = :sid
            ORDER BY created_at ASC
            LIMIT :limit
        """
        )
        with self.get_connection() as conn:
            rows = conn.execute(query, {"sid": session_id, "limit": limit}).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_running_playbook_execution_tasks(
        self, workspace_id: Optional[str] = None, limit: int = 200
    ) -> List[Task]:
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
            AND status = :status
            """
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
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
