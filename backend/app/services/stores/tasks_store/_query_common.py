
"""Shared helpers and SQL fragments for TasksStore read-only queries."""

from __future__ import annotations

from typing import List, Optional

from app.models.workspace import Task, TaskStatus
from backend.app.services.task_admission_service import ADMISSION_DEFERRED_REASON

from ._base import _utc_now

_WORKSPACE_QUOTA_EXHAUSTED_REASON = "workspace_allocation_quota_exhausted"
_WORKSPACE_ALLOCATION_REQUIRED_REASON = "workspace_allocation_required"
_WORKSPACE_ALLOCATION_DISABLED_REASON = "workspace_allocation_disabled"
_WORKSPACE_QUOTA_RELEASE_REASONS = (
    _WORKSPACE_QUOTA_EXHAUSTED_REASON,
    _WORKSPACE_ALLOCATION_REQUIRED_REASON,
    _WORKSPACE_ALLOCATION_DISABLED_REASON,
)
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
        t.blocked_reason,
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
        t.blocked_reason,
        t.queue_shard,
        t.concurrency_key
    FROM chosen c
    JOIN tasks t ON t.id = c.id
"""



class TasksStoreQueryCommonMixin:
    """Shared helper methods for TasksStore query mixins."""

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
