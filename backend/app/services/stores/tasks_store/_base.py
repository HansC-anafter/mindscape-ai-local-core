"""TasksStore CRUD compatibility facade."""

from __future__ import annotations

from ._crud_control import TasksStoreControlMixin, _publish_terminal_event
from ._crud_create_read import TasksStoreCreateReadMixin
from ._crud_frontier_release import TasksStoreFrontierReleaseMixin
from ._crud_helpers import (
    _RUNNER_TASK_TYPES,
    _TERMINAL_TASK_STATUSES,
    _clean_queue_shard,
    _coerce_task_status,
    _derive_blocked_payload,
    _derive_scheduler_fields,
    _enrich_runner_task_context,
    _normalize_frontier_updates_for_status,
    _normalize_queue_shard,
    _parse_resume_after,
    _resolve_concurrency_key,
    _resolve_hydrated_queue_shard,
    _resolve_queue_shard,
    _utc_now,
)
from ._crud_status import TasksStoreStatusUpdateMixin
from ._crud_update import TasksStoreUpdateMixin
from ._task_row_projection import TasksStoreRowProjectionMixin


class TasksStoreCrudMixin(
    TasksStoreControlMixin,
    TasksStoreCreateReadMixin,
    TasksStoreFrontierReleaseMixin,
    TasksStoreStatusUpdateMixin,
    TasksStoreUpdateMixin,
    TasksStoreRowProjectionMixin,
):
    """CRUD operations and private helpers for TasksStore."""


__all__ = [
    "TasksStoreCrudMixin",
    "_RUNNER_TASK_TYPES",
    "_TERMINAL_TASK_STATUSES",
    "_clean_queue_shard",
    "_coerce_task_status",
    "_derive_blocked_payload",
    "_derive_scheduler_fields",
    "_enrich_runner_task_context",
    "_normalize_frontier_updates_for_status",
    "_normalize_queue_shard",
    "_parse_resume_after",
    "_publish_terminal_event",
    "_resolve_concurrency_key",
    "_resolve_hydrated_queue_shard",
    "_resolve_queue_shard",
    "_utc_now",
]
