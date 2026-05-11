"""Resource-aware runner admission facade."""

from .admission import (
    RESOURCE_WAIT_REASON,
    ResourceAdmissionDecision,
    acquire_task_resource_admission,
    build_resource_wait_task_update,
    release_acquired_resource_leases,
)
from .heartbeat import (
    RUNNER_RESOURCE_HEARTBEAT_TTL_SECONDS,
    build_runner_resource_heartbeat,
    list_active_runner_resource_heartbeats,
    publish_runner_resource_heartbeat,
)
from .leases import (
    InMemoryResourceLeaseStore,
    RedisResourceLeaseStore,
    ResourceLease,
    ResourceLeaseStore,
    build_resource_lease_key,
    resource_lease_keys_from_context,
    release_resource_lease_keys,
    renew_resource_lease_keys,
)
from .requirements import (
    DB_WRITE_BUDGETS,
    DURATION_CLASSES,
    ResourceRequirements,
    resolve_resource_requirements,
)
from .snapshots import (
    InMemoryTtlSnapshotStore,
    PROGRESS_SNAPSHOT_TTL_SECONDS,
    RedisTtlSnapshotStore,
    RUN_LOG_COUNT_SNAPSHOT_TTL_SECONDS,
    build_progress_snapshot_key,
    build_run_log_count_snapshot_key,
    get_ttl_snapshot,
    set_ttl_snapshot,
)

__all__ = [
    "DB_WRITE_BUDGETS",
    "DURATION_CLASSES",
    "PROGRESS_SNAPSHOT_TTL_SECONDS",
    "RUNNER_RESOURCE_HEARTBEAT_TTL_SECONDS",
    "RUN_LOG_COUNT_SNAPSHOT_TTL_SECONDS",
    "RESOURCE_WAIT_REASON",
    "InMemoryResourceLeaseStore",
    "InMemoryTtlSnapshotStore",
    "RedisResourceLeaseStore",
    "RedisTtlSnapshotStore",
    "ResourceAdmissionDecision",
    "ResourceLease",
    "ResourceLeaseStore",
    "ResourceRequirements",
    "acquire_task_resource_admission",
    "build_resource_lease_key",
    "build_resource_wait_task_update",
    "build_progress_snapshot_key",
    "build_run_log_count_snapshot_key",
    "build_runner_resource_heartbeat",
    "get_ttl_snapshot",
    "list_active_runner_resource_heartbeats",
    "publish_runner_resource_heartbeat",
    "release_acquired_resource_leases",
    "release_resource_lease_keys",
    "renew_resource_lease_keys",
    "resolve_resource_requirements",
    "resource_lease_keys_from_context",
    "set_ttl_snapshot",
]
