"""Task-family bindings derived from installed playbook runner metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .spec_metadata import (
    iter_installed_playbook_runner_metadata,
    resolve_installed_playbook_runner_metadata,
)


DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION = "default_local_browser"
MANAGED_BROWSER_BATCH_TASK_FAMILY = "browser_batch"
MANAGED_BROWSER_BATCH_RUNNER_ROLE = "managed_browser_batch"
RESOURCE_CLASS_BROWSER = "browser"


@dataclass(frozen=True)
class TaskFamilyBinding:
    playbook_code: str
    queue_shard: str
    resource_class: str
    task_family: str
    managed_runner_role: Optional[str] = None
    fairness_lane_key: Optional[str] = None
    capability_code: Optional[str] = None
    runner_profile_hint: Optional[str] = None


def _clean_token(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    token = value.strip()
    return token or None


def _context_mapping(execution_context: Any) -> Mapping[str, Any]:
    return execution_context if isinstance(execution_context, Mapping) else {}


def _mapping_value(mapping: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        token = _clean_token(mapping.get(key))
        if token:
            return token
    return None


def _playbook_code(pack_id: Any, execution_context: Any = None) -> Optional[str]:
    context = _context_mapping(execution_context)
    return _mapping_value(context, "playbook_code", "pack_id") or _clean_token(pack_id)


def _metadata_with_context(
    metadata: Mapping[str, Any],
    execution_context: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(metadata)
    for key in (
        "task_family",
        "managed_runner_role",
        "fairness_lane_key",
        "capability_code",
        "runner_profile_hint",
    ):
        token = execution_context.get(key)
        if token is not None:
            merged[key] = token
    for key in ("queue_partition", "queue_shard", "resource_class"):
        if merged.get(key) is None and execution_context.get(key) is not None:
            merged[key] = execution_context.get(key)
    return merged


def _binding_from_metadata(
    *,
    playbook_code: str,
    metadata: Mapping[str, Any],
) -> Optional[TaskFamilyBinding]:
    task_family = _clean_token(metadata.get("task_family"))
    runner_role = _clean_token(metadata.get("managed_runner_role"))
    queue_shard = _mapping_value(metadata, "queue_partition", "queue_shard")
    resource_class = (_clean_token(metadata.get("resource_class")) or "").lower()

    if task_family == MANAGED_BROWSER_BATCH_TASK_FAMILY:
        queue_shard = DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION
        resource_class = resource_class or RESOURCE_CLASS_BROWSER
    elif (
        queue_shard == DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION
        and resource_class == RESOURCE_CLASS_BROWSER
    ):
        task_family = MANAGED_BROWSER_BATCH_TASK_FAMILY
        runner_role = runner_role or MANAGED_BROWSER_BATCH_RUNNER_ROLE

    if task_family != MANAGED_BROWSER_BATCH_TASK_FAMILY:
        return None
    if queue_shard != DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION:
        return None
    if resource_class != RESOURCE_CLASS_BROWSER:
        return None

    normalized_playbook_code = _clean_token(playbook_code)
    if not normalized_playbook_code:
        return None

    fairness_lane_key = (
        _clean_token(metadata.get("fairness_lane_key"))
        or normalized_playbook_code
    )
    return TaskFamilyBinding(
        playbook_code=normalized_playbook_code,
        queue_shard=queue_shard,
        resource_class=resource_class,
        task_family=task_family,
        managed_runner_role=runner_role or MANAGED_BROWSER_BATCH_RUNNER_ROLE,
        fairness_lane_key=fairness_lane_key,
        capability_code=_clean_token(metadata.get("capability_code")),
        runner_profile_hint=_clean_token(metadata.get("runner_profile_hint")),
    )


def resolve_managed_batch_binding(
    pack_id: Any,
    execution_context: Any = None,
) -> Optional[TaskFamilyBinding]:
    """Return the managed browser batch binding declared by the playbook metadata."""
    context = _context_mapping(execution_context)
    playbook_code = _playbook_code(pack_id, context)
    if not playbook_code:
        return None
    metadata = resolve_installed_playbook_runner_metadata(playbook_code)
    merged = _metadata_with_context(metadata, context)
    return _binding_from_metadata(playbook_code=playbook_code, metadata=merged)


def iter_managed_batch_bindings() -> tuple[TaskFamilyBinding, ...]:
    """Return all installed playbook bindings for the managed browser batch family."""
    bindings: list[TaskFamilyBinding] = []
    for playbook_code, metadata in iter_installed_playbook_runner_metadata():
        binding = _binding_from_metadata(
            playbook_code=playbook_code,
            metadata=metadata,
        )
        if binding is not None:
            bindings.append(binding)
    return tuple(bindings)


def is_managed_browser_batch_task(
    pack_id: Any,
    execution_context: Any = None,
) -> bool:
    return resolve_managed_batch_binding(pack_id, execution_context) is not None


def resolve_managed_browser_batch_queue_override(
    pack_id: Any,
    execution_context: Any = None,
) -> Optional[str]:
    binding = resolve_managed_batch_binding(pack_id, execution_context)
    return binding.queue_shard if binding else None


def resolve_browser_fairness_lane_key(
    pack_id: Any,
    playbook_code: Any = None,
) -> Optional[str]:
    context = {}
    playbook_token = _clean_token(playbook_code)
    if playbook_token:
        context["playbook_code"] = playbook_token
    binding = resolve_managed_batch_binding(pack_id, context)
    if binding is None and playbook_token:
        binding = resolve_managed_batch_binding(pack_id, None)
    if binding is not None and binding.fairness_lane_key:
        return binding.fairness_lane_key
    return playbook_token or _clean_token(pack_id)


def managed_browser_batch_peer_frontier_lanes() -> frozenset[str]:
    lanes = {
        binding.fairness_lane_key
        for binding in iter_managed_batch_bindings()
        if binding.fairness_lane_key
    }
    return frozenset(lanes)
