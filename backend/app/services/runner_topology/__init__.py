"""Runner topology helpers."""

from .capacity_policy import (
    RunnerCapacitySnapshot,
    resolve_runner_capacity_snapshot,
    resolve_runner_poll_batch_limit,
    runner_profile_has_capacity,
)
from .default_local_browser import (
    DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION,
    is_default_local_browser_legacy_partition,
    is_default_local_browser_playbook,
    resolve_default_local_browser_queue_override,
)
from .partitions import (
    BROWSER_LOCAL_QUEUE_PARTITION,
    DEFAULT_LOCAL_QUEUE_PARTITION,
    RUNNER_READY_QUEUE_ORDER,
    VISION_LOCAL_QUEUE_PARTITION,
    build_queue_partition_filter_clause,
    canonical_queue_partition_for_pack,
    normalize_queue_partition,
    queue_partition_aliases,
    queue_partition_env_suffixes,
    queue_partition_matches,
)
from .profile_registry import (
    RESOURCE_CLASS_API,
    RESOURCE_CLASS_BROWSER,
    RESOURCE_CLASS_COMPUTE,
    RunnerProfile,
    get_builtin_runner_profiles,
    resolve_runner_profile_from_env,
)
from .routing import (
    TaskRoutingTarget,
    resolve_target_runner_profile,
    resolve_task_routing_target,
    runner_profile_can_claim_task,
)
from .spec_metadata import (
    merge_runner_metadata_into_context,
    resolve_installed_playbook_runner_metadata,
)
from .runtime_binding import (
    RuntimeBindingTarget,
    resolve_runtime_binding,
    resolve_runtime_dispatch_target,
    resolve_task_runtime_affinity,
)
from .task_family_registry import (
    MANAGED_BROWSER_BATCH_RUNNER_ROLE,
    MANAGED_BROWSER_BATCH_TASK_FAMILY,
    TaskFamilyBinding,
    iter_managed_batch_bindings,
    managed_browser_batch_peer_frontier_lanes,
    resolve_browser_fairness_lane_key,
    resolve_managed_batch_binding,
)

__all__ = [
    "BROWSER_LOCAL_QUEUE_PARTITION",
    "DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION",
    "DEFAULT_LOCAL_QUEUE_PARTITION",
    "RESOURCE_CLASS_API",
    "RESOURCE_CLASS_BROWSER",
    "RESOURCE_CLASS_COMPUTE",
    "RUNNER_READY_QUEUE_ORDER",
    "RunnerCapacitySnapshot",
    "RunnerProfile",
    "TaskRoutingTarget",
    "RuntimeBindingTarget",
    "TaskFamilyBinding",
    "VISION_LOCAL_QUEUE_PARTITION",
    "MANAGED_BROWSER_BATCH_RUNNER_ROLE",
    "MANAGED_BROWSER_BATCH_TASK_FAMILY",
    "build_queue_partition_filter_clause",
    "canonical_queue_partition_for_pack",
    "get_builtin_runner_profiles",
    "normalize_queue_partition",
    "queue_partition_aliases",
    "queue_partition_env_suffixes",
    "queue_partition_matches",
    "resolve_runner_capacity_snapshot",
    "resolve_runner_poll_batch_limit",
    "resolve_runner_profile_from_env",
    "resolve_default_local_browser_queue_override",
    "resolve_installed_playbook_runner_metadata",
    "iter_managed_batch_bindings",
    "managed_browser_batch_peer_frontier_lanes",
    "resolve_browser_fairness_lane_key",
    "resolve_managed_batch_binding",
    "resolve_runtime_binding",
    "resolve_runtime_dispatch_target",
    "resolve_target_runner_profile",
    "resolve_task_runtime_affinity",
    "resolve_task_routing_target",
    "runner_profile_has_capacity",
    "runner_profile_can_claim_task",
    "is_default_local_browser_legacy_partition",
    "is_default_local_browser_playbook",
    "merge_runner_metadata_into_context",
]
