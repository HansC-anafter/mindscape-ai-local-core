"""TasksStore runner lifecycle compatibility facade."""

from app.models.workspace import TaskStatus
from backend.app.services.runner_live_state import RunnerLiveStateStore

from ._runner_claims import TasksStoreRunnerClaimMixin
from ._runner_heartbeats import TasksStoreRunnerHeartbeatMixin
from ._runner_helpers import (
    _CLAIM_CONTEXT_STALE_KEYS,
    _WORKSPACE_QUOTA_RELEASE_REASONS,
    _build_claim_execution_context,
    _clean_int,
    _clean_string,
    _decision_to_payload,
    _effective_runner_heartbeat_at,
    _json_mapping,
    _normalize_concurrency_keys,
    _parse_heartbeat_datetime,
    _quota_selectors,
    _running_concurrency_conflict_clause,
    _workspace_quota_allows_claim,
    _workspace_quota_selector_sql,
    _workspace_quota_task_selector_sql,
)
from ._runner_lifecycle import TasksStoreRunnerLifecycleMixin


class TasksStoreRunnerMixin(
    TasksStoreRunnerClaimMixin,
    TasksStoreRunnerLifecycleMixin,
    TasksStoreRunnerHeartbeatMixin,
):
    """Runner lifecycle operations for TasksStore."""

    pass


__all__ = [
    "RunnerLiveStateStore",
    "TaskStatus",
    "TasksStoreRunnerMixin",
    "_CLAIM_CONTEXT_STALE_KEYS",
    "_WORKSPACE_QUOTA_RELEASE_REASONS",
    "_build_claim_execution_context",
    "_clean_int",
    "_clean_string",
    "_decision_to_payload",
    "_effective_runner_heartbeat_at",
    "_json_mapping",
    "_normalize_concurrency_keys",
    "_parse_heartbeat_datetime",
    "_quota_selectors",
    "_running_concurrency_conflict_clause",
    "_workspace_quota_allows_claim",
    "_workspace_quota_selector_sql",
    "_workspace_quota_task_selector_sql",
]
