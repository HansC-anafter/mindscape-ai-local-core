
"""General task list read-only query methods for TasksStore."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus

from ._query_common import _EXECUTION_LIST_SELECT, _TASK_SUMMARY_LIST_SELECT


class TasksStoreListQueryMixin:
    """Workspace, thread, execution, and dispatch list query methods."""

    def list_tasks_by_workspace(
        self,
        workspace_id: Optional[str],
        status: Optional[TaskStatus] = None,
        limit: Optional[int] = None,
        exclude_cancelled: bool = False,
        task_type: Optional[str] = None,
        compact: bool = False,
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
        base_select = _TASK_SUMMARY_LIST_SELECT if compact else "SELECT * FROM tasks"
        query_parts = [base_select, "WHERE 1=1"]
        params: Dict[str, Any] = {}

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        if status:
            query_parts.append("AND status = :status")
            params["status"] = status.value

        if task_type:
            normalized_task_type = str(task_type).strip().lower()
            if normalized_task_type == "execution":
                query_parts.append("AND execution_context IS NOT NULL")
            else:
                query_parts.append("AND task_type = :task_type")
                params["task_type"] = task_type

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
        self,
        workspace_id: str,
        project_id: str,
        limit: Optional[int] = None,
        include_completed: bool = True,
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
        query = f"""
            {_EXECUTION_LIST_SELECT}
            WHERE workspace_id = :workspace_id
            AND project_id = :project_id
            AND execution_context IS NOT NULL
        """
        params: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "project_id": project_id,
        }

        if not include_completed:
            query += """
            AND status IN (:pending_status, :running_status)
            """
            params["pending_status"] = TaskStatus.PENDING.value
            params["running_status"] = TaskStatus.RUNNING.value

        query += """
            ORDER BY created_at DESC
        """

        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_executions_by_workspace(
        self,
        workspace_id: str,
        limit: Optional[int] = None,
        include_completed: bool = True,
    ) -> List[Task]:
        """
        List all Playbook execution tasks (tasks with execution_context) for a workspace

        Args:
            workspace_id: Workspace ID
            limit: Maximum number of tasks to return (optional)

        Returns:
            List of execution tasks (tasks with execution_context)
        """
        query = f"""
            {_EXECUTION_LIST_SELECT}
            WHERE workspace_id = :workspace_id
            AND execution_context IS NOT NULL
        """
        params: Dict[str, Any] = {"workspace_id": workspace_id}

        if not include_completed:
            query += """
            AND status IN (:pending_status, :running_status)
            """
            params["pending_status"] = TaskStatus.PENDING.value
            params["running_status"] = TaskStatus.RUNNING.value

        query += """
            ORDER BY created_at DESC
        """

        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_pending_tasks(
        self,
        workspace_id: str,
        exclude_cancelled: bool = True,
        limit: Optional[int] = None,
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
            workspace_id=workspace_id, status=TaskStatus.PENDING, limit=limit
        )
        if exclude_cancelled:
            return [
                t
                for t in tasks
                if t.status not in (TaskStatus.CANCELLED_BY_USER, TaskStatus.EXPIRED)
            ]
        return tasks

    def list_running_tasks(
        self,
        workspace_id: str,
        limit: Optional[int] = None,
    ) -> List[Task]:
        """
        List running tasks for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            List of running tasks
        """
        return self.list_tasks_by_workspace(
            workspace_id=workspace_id, status=TaskStatus.RUNNING, limit=limit
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
