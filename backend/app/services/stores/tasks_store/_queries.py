"""
TasksStore query mixin — all list_* and find_* read-only methods.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus
from backend.app.services.runner_topology import (
    build_queue_partition_filter_clause,
    queue_partition_aliases,
    queue_partition_matches,
)
from backend.app.services.task_admission_service import ADMISSION_DEFERRED_REASON

logger = logging.getLogger(__name__)
_COLD_RELEASE_SCAN_MIN = 4096
_COLD_RELEASE_SCAN_MULTIPLIER = 64
_COLD_RELEASE_SCAN_MAX = 50000


def _cold_release_scan_limit(limit: int) -> int:
    try:
        requested = int(limit)
    except Exception:
        requested = 0
    if requested <= 0:
        requested = 1
    return min(
        max(requested * _COLD_RELEASE_SCAN_MULTIPLIER, _COLD_RELEASE_SCAN_MIN),
        _COLD_RELEASE_SCAN_MAX,
    )

_EXECUTION_LIST_SELECT = """
    SELECT
        id,
        workspace_id,
        message_id,
        execution_id,
        parent_execution_id,
        project_id,
        pack_id,
        task_type,
        status,
        params,
        NULL AS result,
        CASE
            WHEN execution_context IS NULL THEN NULL
            ELSE jsonb_strip_nulls(
                jsonb_build_object(
                    'playbook_code', execution_context->>'playbook_code',
                    'playbook_name', execution_context->>'playbook_name',
                    'project_id', COALESCE(execution_context->>'project_id', project_id),
                    'project_name', execution_context->>'project_name',
                    'paused_at', execution_context->>'paused_at',
                    'thread_id', execution_context->>'thread_id',
                    'timeout_diagnostic', execution_context->'timeout_diagnostic'
                )
            )
        END AS execution_context,
        meeting_session_id,
        storyline_tags,
        created_at,
        next_eligible_at,
        blocked_reason,
        blocked_payload,
        queue_shard,
        concurrency_key,
        frontier_state,
        frontier_enqueued_at,
        started_at,
        completed_at,
        error
    FROM tasks
"""

_TASK_SUMMARY_LIST_SELECT = """
    SELECT
        id,
        workspace_id,
        message_id,
        execution_id,
        parent_execution_id,
        project_id,
        pack_id,
        task_type,
        status,
        params,
        NULL AS result,
        CASE
            WHEN execution_context IS NULL THEN NULL
            ELSE jsonb_strip_nulls(
                jsonb_build_object(
                    'playbook_code', execution_context->>'playbook_code',
                    'playbook_name', execution_context->>'playbook_name',
                    'project_id', COALESCE(execution_context->>'project_id', project_id),
                    'project_name', execution_context->>'project_name',
                    'status', execution_context->>'status',
                    'execution_mode', execution_context->>'execution_mode',
                    'run_mode', execution_context->>'run_mode',
                    'trigger', execution_context->>'trigger',
                    'runner_id', CASE
                        WHEN status = 'running' THEN COALESCE(runner_id, execution_context->>'runner_id')
                        ELSE runner_id
                    END,
                    'heartbeat_at', CASE
                        WHEN status = 'running' THEN COALESCE(heartbeat_at::text, execution_context->>'heartbeat_at')
                        ELSE heartbeat_at::text
                    END,
                    'target_username', COALESCE(
                        execution_context->>'target_username',
                        execution_context->'inputs'->>'target_username'
                    ),
                    'reference_id', COALESCE(
                        execution_context->>'reference_id',
                        execution_context->'inputs'->>'reference_id'
                    ),
                    'source_handle', COALESCE(
                        execution_context->>'source_handle',
                        execution_context->'inputs'->>'source_handle'
                    ),
                    'inputs', jsonb_strip_nulls(
                        jsonb_build_object(
                            'target_username', execution_context->'inputs'->>'target_username',
                            'reference_id', execution_context->'inputs'->>'reference_id',
                            'source_handle', execution_context->'inputs'->>'source_handle',
                            'profile_id', execution_context->'inputs'->>'profile_id',
                            'run_mode', execution_context->'inputs'->>'run_mode',
                            'trigger', execution_context->'inputs'->>'trigger'
                        )
                    )
                )
            )
        END AS execution_context,
        meeting_session_id,
        storyline_tags,
        created_at,
        next_eligible_at,
        blocked_reason,
        blocked_payload,
        queue_shard,
        concurrency_key,
        frontier_state,
        frontier_enqueued_at,
        started_at,
        completed_at,
        error
    FROM tasks
"""

_ADMISSION_RELEASE_CANDIDATE_SELECT = """
    SELECT
        id,
        workspace_id,
        message_id,
        execution_id,
        pack_id,
        task_type,
        status,
        execution_context,
        created_at,
        next_eligible_at,
        queue_shard,
        concurrency_key
    FROM tasks
"""

_ADMISSION_RELEASE_CANDIDATE_SELECT_FROM_ALIAS = """
    SELECT
        t.id,
        t.workspace_id,
        t.message_id,
        t.execution_id,
        t.pack_id,
        t.task_type,
        t.status,
        t.execution_context,
        t.created_at,
        t.next_eligible_at,
        t.queue_shard,
        t.concurrency_key
    FROM chosen c
    JOIN tasks t ON t.id = c.id
"""

_ADMISSION_DEFERRED_RELEASE_CANDIDATE_SELECT = """
    SELECT
        id,
        workspace_id,
        message_id,
        execution_id,
        pack_id,
        task_type,
        status,
        NULL::jsonb AS execution_context,
        created_at,
        next_eligible_at,
        blocked_payload,
        queue_shard,
        concurrency_key
    FROM tasks
"""

_COLD_RELEASE_CANDIDATE_SELECT_FROM_ALIAS = """
    SELECT
        t.id,
        t.workspace_id,
        t.message_id,
        t.execution_id,
        t.pack_id,
        t.task_type,
        t.status,
        t.execution_context,
        t.created_at,
        t.next_eligible_at,
        t.queue_shard,
        t.concurrency_key
    FROM chosen c
    JOIN tasks t ON t.id = c.id
"""

_COLD_RELEASE_COMPACT_CANDIDATE_SELECT_FROM_ALIAS = """
    SELECT
        t.id,
        t.workspace_id,
        t.message_id,
        t.execution_id,
        t.pack_id,
        t.task_type,
        t.status,
        NULL::jsonb AS execution_context,
        t.created_at,
        t.next_eligible_at,
        t.queue_shard,
        t.concurrency_key
    FROM chosen c
    JOIN tasks t ON t.id = c.id
"""


class TasksStoreQueryMixin:
    """Read-only query methods for TasksStore."""

    def _resolve_effective_concurrency_key(self, task: Task) -> Optional[str]:
        """Recompute the current lock key from task context.

        This lets the scheduler honor updated lock semantics without waiting for
        every persisted task row to be rewritten.
        """
        try:
            from backend.app.runner.concurrency import _resolve_lock_key

            ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
            resolved = _resolve_lock_key(ctx, task.pack_id)
            if isinstance(resolved, str) and resolved.strip():
                return resolved.strip()
        except Exception:
            pass

        if isinstance(task.concurrency_key, str) and task.concurrency_key.strip():
            return task.concurrency_key.strip()
        return None

    def _select_fair_runnable_tasks(
        self,
        *,
        candidates: List[Task],
        limit: int,
        active_keys: set[str],
    ) -> List[Task]:
        """Pick at most one pending task per effective lock key.

        This keeps a single hot queue from being saturated by hundreds of tasks
        that all compete for the same mutex, while still allowing different
        playbooks with distinct lock keys to make progress concurrently.
        """
        selected: List[Task] = []
        seen_keys: set[str] = set()

        for task in candidates:
            lock_key = self._resolve_effective_concurrency_key(task)
            if lock_key:
                if lock_key in active_keys:
                    continue
                if lock_key in seen_keys:
                    continue
                seen_keys.add(lock_key)
            selected.append(task)
            if len(selected) >= limit:
                break

        return selected

    def _row_to_blocked_release_candidate(self, row, *, blocked_reason: str) -> Task:
        execution_context = None
        try:
            raw_ctx = getattr(row, "execution_context", None)
            if raw_ctx:
                execution_context = self.deserialize_json(raw_ctx)
        except Exception:
            execution_context = None

        created_at = self._coerce_datetime(getattr(row, "created_at", None)) or _utc_now()
        next_eligible_at = (
            self._coerce_datetime(getattr(row, "next_eligible_at", None)) or created_at
        )

        return Task(
            id=row.id,
            workspace_id=row.workspace_id,
            message_id=row.message_id,
            execution_id=getattr(row, "execution_id", None),
            pack_id=row.pack_id,
            task_type=row.task_type,
            status=TaskStatus(row.status),
            params={},
            result=None,
            execution_context=execution_context,
            created_at=created_at,
            next_eligible_at=next_eligible_at,
            blocked_reason=blocked_reason,
            blocked_payload=getattr(row, "blocked_payload", None),
            queue_shard=getattr(row, "queue_shard", None) or "default",
            concurrency_key=getattr(row, "concurrency_key", None),
            frontier_state="cold",
            runner_id=getattr(row, "runner_id", None),
            heartbeat_at=self._coerce_datetime(getattr(row, "heartbeat_at", None)),
        )

    def _row_to_admission_release_candidate(self, row) -> Task:
        return self._row_to_blocked_release_candidate(
            row, blocked_reason=ADMISSION_DEFERRED_REASON
        )

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

    def list_runnable_playbook_execution_tasks(
        self,
        workspace_id: Optional[str] = None,
        limit: int = 500,
        queue_shard: Optional[str] = None,
    ) -> List[Task]:
        scan_limit = min(max(limit * 64, 512), 4096)
        query_parts = [
            _ADMISSION_RELEASE_CANDIDATE_SELECT,
            """
            WHERE task_type IN (:task_type_pb, :task_type_tool)
            AND status = :status
            AND frontier_state = :frontier_state
            AND next_eligible_at <= :now
            AND COALESCE(blocked_reason, '') <> :admission_blocked_reason
            """
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "frontier_state": "ready",
            "now": datetime.now(timezone.utc),
            "admission_blocked_reason": ADMISSION_DEFERRED_REASON,
        }

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        if queue_shard:
            queue_clause, queue_params = build_queue_partition_filter_clause(
                "queue_shard",
                queue_shard,
                param_prefix="queue_partition",
            )
            query_parts.append(f"AND {queue_clause}")
            params.update(queue_params)

        query_parts.append(
            "ORDER BY frontier_enqueued_at ASC NULLS LAST, created_at ASC, id ASC"
        )
        query_parts.append("LIMIT :limit")
        params["limit"] = scan_limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            candidates = [
                self._row_to_blocked_release_candidate(row, blocked_reason="")
                for row in rows
            ]

        running_tasks = self.list_running_playbook_execution_tasks(
            workspace_id=None,
            limit=scan_limit,
        )
        active_keys = {
            key
            for task in running_tasks
            if (
                not queue_shard
                or queue_partition_matches(getattr(task, "queue_shard", None), queue_shard)
            )
            for key in [self._resolve_effective_concurrency_key(task)]
            if key
        }

        return self._select_fair_runnable_tasks(
            candidates=candidates,
            limit=limit,
            active_keys=active_keys,
        )

    def list_due_admission_deferred_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
              AND status = :status
              AND blocked_reason = :blocked_reason
              AND next_eligible_at <= :now
            """
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "blocked_reason": ADMISSION_DEFERRED_REASON,
            "now": datetime.now(timezone.utc),
            "limit": limit,
        }

        if queue_shard:
            queue_clause, queue_params = build_queue_partition_filter_clause(
                "queue_shard",
                queue_shard,
                param_prefix="queue_partition",
            )
            query_parts.append(f"AND {queue_clause}")
            params.update(queue_params)

        query_parts.append(
            """
            ORDER BY
                CASE
                    WHEN COALESCE(blocked_payload->>'visibility', '') = 'visible' THEN 0
                    ELSE 1
                END ASC,
                next_eligible_at ASC,
                created_at ASC,
                id ASC
            """
        )
        query_parts.append("LIMIT :limit")

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_due_admission_deferred_release_candidates(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        """List due admission-deferred tasks with only fields needed for release evaluation."""
        base_params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "blocked_reason": ADMISSION_DEFERRED_REASON,
            "now": datetime.now(timezone.utc),
            "limit": limit,
        }

        def build_query(queue_clause: Optional[str] = None) -> str:
            query_parts = [
                _ADMISSION_DEFERRED_RELEASE_CANDIDATE_SELECT,
                """
                WHERE task_type IN (:task_type_pb, :task_type_tool)
                  AND status = :status
                  AND blocked_reason = :blocked_reason
                  AND next_eligible_at <= :now
                """,
            ]
            if queue_clause:
                query_parts.append(f"AND {queue_clause}")
            query_parts.append(
                """
                ORDER BY
                    CASE
                        WHEN COALESCE(blocked_payload->>'visibility', '') = 'visible' THEN 0
                        ELSE 1
                    END ASC,
                    next_eligible_at ASC,
                    created_at ASC,
                    id ASC
                """
            )
            query_parts.append("LIMIT :limit")
            return " ".join(query_parts)

        def sort_key(task: Task) -> tuple[int, datetime, datetime, str]:
            blocked_payload = task.blocked_payload or {}
            visibility = (
                blocked_payload.get("visibility")
                if isinstance(blocked_payload, dict)
                else None
            )
            next_eligible_at = task.next_eligible_at or datetime.max.replace(
                tzinfo=timezone.utc
            )
            created_at = task.created_at or datetime.max.replace(tzinfo=timezone.utc)
            return (
                0 if visibility == "visible" else 1,
                next_eligible_at,
                created_at,
                str(task.id),
            )

        with self.get_connection() as conn:
            if not queue_shard:
                rows = conn.execute(text(build_query()), base_params).fetchall()
                return [self._row_to_admission_release_candidate(row) for row in rows]

            aliases = queue_partition_aliases(queue_shard)
            if not aliases:
                return []

            candidates_by_id: dict[str, Task] = {}
            clauses: list[tuple[str, Dict[str, Any]]] = []
            for index, alias in enumerate(aliases):
                key = f"queue_partition_exact_{index}"
                clauses.append((f"queue_shard = :{key}", {key: alias}))
            if "default" in aliases:
                clauses.append(("queue_shard IS NULL", {}))

            for queue_clause, queue_params in clauses:
                params = dict(base_params)
                params.update(queue_params)
                rows = conn.execute(text(build_query(queue_clause)), params).fetchall()
                for row in rows:
                    task = self._row_to_admission_release_candidate(row)
                    candidates_by_id[str(task.id)] = task

            candidates = sorted(candidates_by_id.values(), key=sort_key)
            return candidates[:limit]

    def list_due_concurrency_locked_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        return self._list_ranked_cold_release_candidates(
            blocked_reason="concurrency_locked",
            queue_shard=queue_shard,
            limit=limit,
            include_execution_context=False,
        )

    def _list_ranked_cold_release_candidates(
        self,
        *,
        blocked_reason: str,
        queue_shard: Optional[str],
        limit: int,
        include_execution_context: bool = True,
    ) -> List[Task]:
        query_parts = [
            """
            WITH sampled AS (
                SELECT
                    id,
                    pack_id,
                    next_eligible_at,
                    created_at
                FROM tasks
                WHERE task_type IN (:task_type_pb, :task_type_tool)
                  AND status = :status
                  AND frontier_state = :frontier_state
                  AND next_eligible_at <= :now
            """,
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "frontier_state": "cold",
            "now": datetime.now(timezone.utc),
            "limit": limit,
            "scan_limit": _cold_release_scan_limit(limit),
        }

        if blocked_reason:
            query_parts.append("AND blocked_reason = :blocked_reason")
            params["blocked_reason"] = blocked_reason
        else:
            query_parts.append("AND (blocked_reason IS NULL OR blocked_reason = '')")

        if queue_shard:
            queue_clause, queue_params = build_queue_partition_filter_clause(
                "queue_shard",
                queue_shard,
                param_prefix="queue_partition",
            )
            query_parts.append(f"AND {queue_clause}")
            params.update(queue_params)

        query_parts.append(
            """
                ORDER BY next_eligible_at ASC, created_at ASC, id ASC
                LIMIT :scan_limit
            ),
            ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY pack_id
                        ORDER BY next_eligible_at ASC, created_at ASC, id ASC
                    ) AS pack_rank,
                    next_eligible_at,
                    created_at
                FROM sampled
            """,
        )

        query_parts.append(
            """
            ),
            chosen AS (
                SELECT id, pack_rank, next_eligible_at, created_at
                FROM ranked
                ORDER BY pack_rank ASC, next_eligible_at ASC, created_at ASC, id ASC
                LIMIT :limit
            )
            """
        )
        query_parts.append(
            _COLD_RELEASE_CANDIDATE_SELECT_FROM_ALIAS
            if include_execution_context
            else _COLD_RELEASE_COMPACT_CANDIDATE_SELECT_FROM_ALIAS
        )
        query_parts.append(
            "ORDER BY c.pack_rank ASC, c.next_eligible_at ASC, c.created_at ASC, c.id ASC"
        )

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [
                self._row_to_blocked_release_candidate(
                    row, blocked_reason=blocked_reason
                )
                for row in rows
            ]

    def _list_ordered_cold_release_candidates(
        self,
        *,
        blocked_reason: str,
        queue_shard: Optional[str],
        limit: int,
        include_execution_context: bool = True,
    ) -> List[Task]:
        query_parts = [
            """
            WITH chosen AS (
                SELECT id, next_eligible_at, created_at
                FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
              AND status = :status
              AND blocked_reason = :blocked_reason
              AND frontier_state = :frontier_state
              AND next_eligible_at <= :now
            """,
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "blocked_reason": blocked_reason,
            "frontier_state": "cold",
            "now": datetime.now(timezone.utc),
            "limit": limit,
        }

        if queue_shard:
            queue_clause, queue_params = build_queue_partition_filter_clause(
                "queue_shard",
                queue_shard,
                param_prefix="queue_partition",
            )
            query_parts.append(f"AND {queue_clause}")
            params.update(queue_params)

        query_parts.append(
            """
                ORDER BY next_eligible_at ASC, created_at ASC, id ASC
                LIMIT :limit
            )
            """
        )
        query_parts.append(
            _COLD_RELEASE_CANDIDATE_SELECT_FROM_ALIAS
            if include_execution_context
            else _COLD_RELEASE_COMPACT_CANDIDATE_SELECT_FROM_ALIAS
        )
        query_parts.append("ORDER BY c.next_eligible_at ASC, c.created_at ASC, c.id ASC")

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [
                self._row_to_blocked_release_candidate(
                    row, blocked_reason=blocked_reason
                )
                for row in rows
            ]

    def list_due_dependency_hold_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        return self._list_ordered_cold_release_candidates(
            blocked_reason="dependency_hold",
            queue_shard=queue_shard,
            limit=limit,
            include_execution_context=False,
        )

    def list_due_resource_wait_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        return self._list_ranked_cold_release_candidates(
            blocked_reason="resource_wait",
            queue_shard=queue_shard,
            limit=limit,
        )

    def list_due_unblocked_cold_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        return self._list_ranked_cold_release_candidates(
            blocked_reason="",
            queue_shard=queue_shard,
            limit=limit,
            include_execution_context=False,
        )

    def _list_due_blocked_cold_tasks(
        self,
        *,
        blocked_reason: str,
        queue_shard: Optional[str],
        limit: int,
    ) -> List[Task]:
        query_parts = [
            _ADMISSION_RELEASE_CANDIDATE_SELECT,
            """
            WHERE task_type IN (:task_type_pb, :task_type_tool)
              AND status = :status
              AND blocked_reason = :blocked_reason
              AND frontier_state = :frontier_state
              AND next_eligible_at <= :now
            """,
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "blocked_reason": blocked_reason,
            "frontier_state": "cold",
            "now": datetime.now(timezone.utc),
            "limit": limit,
        }

        if queue_shard:
            queue_clause, queue_params = build_queue_partition_filter_clause(
                "queue_shard",
                queue_shard,
                param_prefix="queue_partition",
            )
            query_parts.append(f"AND {queue_clause}")
            params.update(queue_params)

        query_parts.append("ORDER BY next_eligible_at ASC, created_at ASC, id ASC")
        query_parts.append("LIMIT :limit")

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [
                self._row_to_blocked_release_candidate(
                    row, blocked_reason=blocked_reason
                )
                for row in rows
            ]

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
        self,
        session_id: Optional[str] = None,
        limit: int = 200,
        workspace_id: Optional[str] = None,
        meeting_session_id: Optional[str] = None,
    ) -> List[Task]:
        """List tasks spawned by a specific meeting session.

        Checks the meeting_session_id column first, falling back to
        execution_context/params JSON columns for backward compatibility.
        """
        effective_session_id = meeting_session_id or session_id
        if not effective_session_id:
            return []

        normalized_limit = max(1, min(int(limit or 200), 500))
        lookup_clauses = [
            "meeting_session_id = :sid",
            "execution_context->>'meeting_session_id' = :sid",
            "execution_context->>'thread_id' = :sid",
            "params->>'meeting_session_id' = :sid",
            "params->>'thread_id' = :sid",
        ]
        base_params: Dict[str, Any] = {"sid": effective_session_id}
        if workspace_id:
            base_params["workspace_id"] = workspace_id

        tasks: List[Task] = []
        seen_ids: set[str] = set()
        with self.get_connection() as conn:
            try:
                conn.execute(text("SET statement_timeout TO '1500ms'"))
            except Exception:
                logger.debug("Unable to set statement_timeout for meeting task lookup", exc_info=True)

            try:
                for clause in lookup_clauses:
                    remaining = normalized_limit - len(tasks)
                    if remaining <= 0:
                        break
                    query_parts = [
                        "SELECT * FROM tasks WHERE",
                        clause,
                    ]
                    params = dict(base_params)
                    if workspace_id:
                        query_parts.append("AND workspace_id = :workspace_id")
                    query_parts.append("ORDER BY created_at ASC")
                    query_parts.append("LIMIT :limit")
                    params["limit"] = remaining

                    try:
                        rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
                    except Exception as exc:
                        logger.warning(
                            "Meeting task lookup clause skipped after query failure: session=%s clause=%s error=%s",
                            effective_session_id,
                            clause,
                            exc,
                        )
                        try:
                            conn.rollback()
                        except Exception:
                            logger.debug("Unable to rollback failed meeting task lookup", exc_info=True)
                        continue

                    for row in rows:
                        task = self._row_to_task(row)
                        if task.id in seen_ids:
                            continue
                        seen_ids.add(task.id)
                        tasks.append(task)
            finally:
                try:
                    conn.execute(text("RESET statement_timeout"))
                except Exception:
                    logger.debug("Unable to reset statement_timeout for meeting task lookup", exc_info=True)

        return tasks

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

    def list_frontier_running_pending_tasks(
        self, workspace_id: Optional[str] = None, limit: int = 200
    ) -> List[Task]:
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
            AND status = :status
            AND frontier_state = :frontier_state
            """
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "frontier_state": "running",
        }

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        query_parts.append("ORDER BY started_at ASC NULLS LAST, created_at ASC, id ASC")
        query_parts.append("LIMIT :limit")
        params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]
