"""
Tasks store for managing task execution records

Tasks are derived from MindEvents and represent Pack execution states.
All task writes go through the /chat flow, ensuring single source of truth.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from .base import StoreBase, StoreNotFoundError
from ...models.workspace import Task, TaskStatus

logger = logging.getLogger(__name__)


class TasksStore(StoreBase):
    """Store for managing task execution records"""

    def create_task(self, task: Task) -> Task:
        """
        Create a new task record

        Args:
            task: Task model instance

        Returns:
            Created task
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tasks (
                    id, workspace_id, message_id, execution_id, pack_id,
                    task_type, status, params, result, execution_context,
                    created_at, started_at, completed_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task.id,
                task.workspace_id,
                task.message_id,
                task.execution_id,
                task.pack_id,
                task.task_type,
                task.status.value,
                self.serialize_json(task.params),
                self.serialize_json(task.result),
                self.serialize_json(task.execution_context) if task.execution_context else None,
                self.to_isoformat(task.created_at),
                self.to_isoformat(task.started_at),
                self.to_isoformat(task.completed_at),
                task.error
            ))
            logger.info(f"Created task: {task.id} (workspace: {task.workspace_id}, pack: {task.pack_id})")
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
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
            row = cursor.fetchone()
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
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tasks WHERE execution_id = ? ORDER BY created_at DESC LIMIT 1', (execution_id,))
            row = cursor.fetchone()
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
        completed_at: Optional[datetime] = None
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
        with self.transaction() as conn:
            cursor = conn.cursor()

            # Build update query dynamically
            updates = ['status = ?']
            values = [status.value]

            if result is not None:
                updates.append('result = ?')
                values.append(self.serialize_json(result))

            if error is not None:
                updates.append('error = ?')
                values.append(error)

            if started_at is not None:
                updates.append('started_at = ?')
                values.append(self.to_isoformat(started_at))

            if completed_at is not None:
                updates.append('completed_at = ?')
                values.append(self.to_isoformat(completed_at))

            values.append(task_id)

            cursor.execute(
                f'UPDATE tasks SET {", ".join(updates)} WHERE id = ?',
                values
            )

            if cursor.rowcount == 0:
                raise StoreNotFoundError(f"Task not found: {task_id}")

            logger.info(f"Updated task {task_id} status to {status.value}")

            # Return updated task
            return self.get_task(task_id)

    def update_task(
        self,
        task_id: str,
        execution_context: Optional[Dict[str, Any]] = None,
        **kwargs
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
        with self.transaction() as conn:
            cursor = conn.cursor()

            updates = []
            values = []

            if execution_context is not None:
                updates.append('execution_context = ?')
                values.append(self.serialize_json(execution_context))

            for key, value in kwargs.items():
                if key in ['params', 'result']:
                    updates.append(f'{key} = ?')
                    values.append(self.serialize_json(value))
                elif key in ['status']:
                    updates.append(f'{key} = ?')
                    values.append(value.value if hasattr(value, 'value') else value)
                elif key in ['started_at', 'completed_at', 'created_at']:
                    updates.append(f'{key} = ?')
                    values.append(self.to_isoformat(value))
                else:
                    updates.append(f'{key} = ?')
                    values.append(value)

            if not updates:
                return self.get_task(task_id)

            values.append(task_id)

            cursor.execute(
                f'UPDATE tasks SET {", ".join(updates)} WHERE id = ?',
                values
            )

            if cursor.rowcount == 0:
                raise StoreNotFoundError(f"Task not found: {task_id}")

            logger.info(f"Updated task {task_id}")
            return self.get_task(task_id)

    def list_tasks_by_workspace(
        self,
        workspace_id: Optional[str],
        status: Optional[TaskStatus] = None,
        limit: Optional[int] = None,
        exclude_cancelled: bool = False
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
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if workspace_id:
                query = 'SELECT * FROM tasks WHERE workspace_id = ?'
                params = [workspace_id]
            else:
                query = 'SELECT * FROM tasks WHERE 1=1'
                params = []

            if status:
                query += ' AND status = ?'
                params.append(status.value)

            if exclude_cancelled:
                query += ' AND status NOT IN (?, ?)'
                params.extend([TaskStatus.CANCELLED_BY_USER.value, TaskStatus.EXPIRED.value])

            query += ' ORDER BY created_at DESC'

            if limit:
                query += ' LIMIT ?'
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_executions_by_workspace(
        self,
        workspace_id: str,
        limit: Optional[int] = None
    ) -> List[Task]:
        """
        List all Playbook execution tasks (tasks with execution_context) for a workspace

        Args:
            workspace_id: Workspace ID
            limit: Maximum number of tasks to return (optional)

        Returns:
            List of execution tasks (tasks with execution_context)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT * FROM tasks
                WHERE workspace_id = ? AND execution_context IS NOT NULL
                ORDER BY created_at DESC
            '''
            params = [workspace_id]

            if limit:
                query += ' LIMIT ?'
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_pending_tasks(self, workspace_id: str, exclude_cancelled: bool = True) -> List[Task]:
        """
        List pending tasks for a workspace

        Args:
            workspace_id: Workspace ID
            exclude_cancelled: Exclude cancelled_by_user and expired tasks (default: True)

        Returns:
            List of pending tasks
        """
        tasks = self.list_tasks_by_workspace(
            workspace_id=workspace_id,
            status=TaskStatus.PENDING
        )
        if exclude_cancelled:
            return [t for t in tasks if t.status not in (TaskStatus.CANCELLED_BY_USER, TaskStatus.EXPIRED)]
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
            workspace_id=workspace_id,
            status=TaskStatus.RUNNING
        )

    def find_existing_suggestion_tasks(
        self,
        workspace_id: str,
        pack_id: str,
        created_within_hours: int = 1
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
        with self.get_connection() as conn:
            cursor = conn.cursor()

            time_threshold = datetime.utcnow() - timedelta(hours=created_within_hours)

            query = '''
                SELECT * FROM tasks
                WHERE workspace_id = ?
                AND pack_id = ?
                AND task_type = ?
                AND status IN (?, ?)
                AND created_at >= ?
                ORDER BY created_at DESC
            '''

            cursor.execute(query, (
                workspace_id,
                pack_id,
                'suggestion',
                TaskStatus.PENDING.value,
                TaskStatus.RUNNING.value,
                self.to_isoformat(time_threshold)
            ))

            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_recently_completed_tasks(
        self,
        workspace_id: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None
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
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT * FROM tasks
                WHERE workspace_id = ?
                AND status IN ('succeeded', 'failed')
                AND displayed_at IS NULL
            '''
            params = [workspace_id]

            if since:
                query += ' AND completed_at >= ?'
                params.append(self.to_isoformat(since))

            query += ' ORDER BY completed_at DESC'

            if limit:
                query += ' LIMIT ?'
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task model"""
        # Handle optional execution_context field
        execution_context = None
        try:
            if 'execution_context' in row.keys() and row['execution_context']:
                execution_context = self.deserialize_json(row['execution_context'])
        except (KeyError, TypeError):
            pass

        return Task(
            id=row['id'],
            workspace_id=row['workspace_id'],
            message_id=row['message_id'],
            execution_id=row['execution_id'],
            pack_id=row['pack_id'],
            task_type=row['task_type'],
            status=TaskStatus(row['status']),
            params=self.deserialize_json(row['params'], {}),
            result=self.deserialize_json(row['result']),
            execution_context=execution_context,
            created_at=self.from_isoformat(row['created_at']),
            started_at=self.from_isoformat(row['started_at']),
            completed_at=self.from_isoformat(row['completed_at']),
            error=row['error']
        )
