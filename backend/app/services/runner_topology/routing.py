"""Task-to-runner routing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .partitions import (
    BROWSER_LOCAL_QUEUE_PARTITION,
    DEFAULT_LOCAL_QUEUE_PARTITION,
    VISION_LOCAL_QUEUE_PARTITION,
    normalize_queue_partition,
)
from .profile_registry import (
    RESOURCE_CLASS_BROWSER,
    RESOURCE_CLASS_COMPUTE,
    RunnerProfile,
)


@dataclass(frozen=True)
class TaskRoutingTarget:
    queue_partition: str
    resource_class: str
    capability_code: Optional[str]
    runner_profile_hint: Optional[str]
    pack_id: Optional[str]


def _normalized_string(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _default_resource_class_for_queue_partition(queue_partition: Optional[str]) -> str:
    normalized_partition = normalize_queue_partition(queue_partition, fallback=None)
    if normalized_partition == BROWSER_LOCAL_QUEUE_PARTITION:
        return RESOURCE_CLASS_BROWSER
    return RESOURCE_CLASS_COMPUTE


def resolve_task_routing_target(task: Any) -> TaskRoutingTarget:
    ctx = {}
    if isinstance(task, dict):
        ctx = task.get("execution_context") if isinstance(task.get("execution_context"), dict) else {}
        pack_id = _normalized_string(task.get("pack_id")) or _normalized_string(
            task.get("playbook_code")
        )
        queue_hint = (
            task.get("queue_partition")
            or task.get("queue_shard")
            or ctx.get("queue_partition")
            or ctx.get("queue_shard")
        )
        queue_partition = normalize_queue_partition(
            queue_hint,
            fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
        )
        resource_class = (
            _normalized_string(task.get("resource_class"))
            or _normalized_string(ctx.get("resource_class"))
            or _default_resource_class_for_queue_partition(queue_partition)
        )
        capability_code = (
            _normalized_string(task.get("capability_code"))
            or _normalized_string(ctx.get("capability_code"))
        )
        runner_profile_hint = (
            _normalized_string(task.get("runner_profile_hint"))
            or _normalized_string(ctx.get("runner_profile_hint"))
        )
    else:
        ctx = getattr(task, "execution_context", None)
        if not isinstance(ctx, dict):
            ctx = {}
        pack_id = _normalized_string(getattr(task, "pack_id", None))
        queue_hint = (
            ctx.get("queue_partition")
            or ctx.get("queue_shard")
            or getattr(task, "queue_shard", None)
        )
        queue_partition = normalize_queue_partition(
            queue_hint,
            fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
        )
        resource_class = (
            _normalized_string(ctx.get("resource_class"))
            or _default_resource_class_for_queue_partition(queue_partition)
        )
        capability_code = _normalized_string(ctx.get("capability_code"))
        runner_profile_hint = _normalized_string(ctx.get("runner_profile_hint"))

    return TaskRoutingTarget(
        queue_partition=queue_partition,
        resource_class=(resource_class or RESOURCE_CLASS_COMPUTE).strip().lower(),
        capability_code=capability_code,
        runner_profile_hint=runner_profile_hint,
        pack_id=pack_id,
    )


def resolve_target_runner_profile(task: Any) -> str:
    target = resolve_task_routing_target(task)
    if target.runner_profile_hint:
        return target.runner_profile_hint
    if target.queue_partition == BROWSER_LOCAL_QUEUE_PARTITION:
        return "browser_local"
    if target.queue_partition == VISION_LOCAL_QUEUE_PARTITION:
        return "vision_local"
    return "default_local"


def runner_profile_can_claim_task(profile: RunnerProfile, task: Any) -> bool:
    if not profile.enabled:
        return False

    target = resolve_task_routing_target(task)
    if (
        profile.accepted_queue_partitions
        and target.queue_partition not in profile.accepted_queue_partitions
    ):
        return False

    if (
        profile.accepted_resource_classes
        and target.resource_class not in profile.accepted_resource_classes
    ):
        return False

    if (
        target.runner_profile_hint
        and target.runner_profile_hint != profile.profile_code
    ):
        return False

    if profile.accepted_capability_codes:
        capability_tokens = {
            token
            for token in (target.capability_code, target.pack_id)
            if isinstance(token, str) and token.strip()
        }
        if not capability_tokens.intersection(profile.accepted_capability_codes):
            return False

    return True
