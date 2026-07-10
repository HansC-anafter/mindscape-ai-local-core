"""Controlled resume service for non-destructive runner resource blocks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.models.workspace import TaskStatus
from backend.app.services.runner_topology import (
    DEFAULT_LOCAL_QUEUE_PARTITION,
    normalize_queue_partition,
    resolve_installed_playbook_runner_metadata,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.runner.resource_failure_policy import is_resource_block_reason

from .node_budget import (
    RedisNodeBudgetStore,
    current_node_memory_snapshot,
    resolve_node_budget_policy,
    resource_profile_fingerprint,
)
from .requirements import resolve_resource_requirements


class ResourceBlockResumeError(RuntimeError):
    def __init__(self, reason: str, *, status_code: int = 409):
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


async def _current_fingerprints(
    task: Any,
    *,
    resource_block: dict[str, Any],
    queue: RedisRunnerQueueStore,
) -> tuple[str, str]:
    context = task.execution_context if isinstance(task.execution_context, dict) else {}
    playbook_code = str(context.get("playbook_code") or task.pack_id or "").strip()
    metadata = resolve_installed_playbook_runner_metadata(playbook_code)
    requirements = resolve_resource_requirements(
        task,
        execution_context=context,
        playbook_metadata=metadata,
    )
    local_policy = resolve_node_budget_policy(current_node_memory_snapshot())
    policy_fingerprint = ""
    if local_policy is not None and local_policy.mode == "calibrated":
        policy_fingerprint = local_policy.fingerprint
    if not policy_fingerprint:
        try:
            budget_snapshot = await RedisNodeBudgetStore(queue).snapshot()
        except Exception:
            budget_snapshot = {}
        policy_fingerprint = str(
            budget_snapshot.get("policy_fingerprint") or ""
        ).strip()
    if not policy_fingerprint:
        raise ResourceBlockResumeError("current_node_policy_unavailable")

    if requirements.memory_mb > 0:
        request_bytes = int(requirements.memory_mb) * 1024 * 1024
    else:
        try:
            request_bytes = int(resource_block.get("requested_memory_bytes") or 0)
        except (TypeError, ValueError):
            request_bytes = 0
    if request_bytes <= 0:
        raise ResourceBlockResumeError("current_resource_profile_unavailable")
    return policy_fingerprint, resource_profile_fingerprint(
        requirements,
        request_bytes,
    )


async def resume_resource_blocked_task(
    *,
    workspace_id: str,
    task_id: str,
    reason: str,
    tasks_store: TasksStore | None = None,
) -> dict[str, Any]:
    store = tasks_store or TasksStore()
    task = store.get_task(task_id)
    if not task:
        raise ResourceBlockResumeError("task_not_found", status_code=404)
    if task.workspace_id != workspace_id:
        raise ResourceBlockResumeError("task_workspace_mismatch", status_code=403)
    blocked_reason = str(getattr(task, "blocked_reason", None) or "")
    if task.status != TaskStatus.PENDING or not is_resource_block_reason(
        blocked_reason
    ):
        raise ResourceBlockResumeError("task_not_resource_blocked")

    context = task.execution_context if isinstance(task.execution_context, dict) else {}
    resource_block = context.get("resource_block")
    if not isinstance(resource_block, dict):
        raise ResourceBlockResumeError("resource_block_evidence_missing")
    queue_shard = normalize_queue_partition(
        getattr(task, "queue_shard", None),
        fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
    )
    queue = RedisRunnerQueueStore(pack_id=queue_shard)
    current_policy, current_profile = await _current_fingerprints(
        task,
        resource_block=resource_block,
        queue=queue,
    )
    previous_policy = str(resource_block.get("node_policy_fingerprint") or "")
    previous_profile = str(
        resource_block.get("resource_profile_fingerprint") or ""
    )
    if current_policy == previous_policy and current_profile == previous_profile:
        raise ResourceBlockResumeError("resource_contract_unchanged")

    now = datetime.now(timezone.utc)
    updated_context = dict(context)
    updated_context.pop("resource_block", None)
    updated_context.pop("resource_pressure", None)
    updated_context.pop("resource_pressure_source", None)
    updated_context["status"] = "queued"
    updated_context["resource_resume"] = {
        "reason": str(reason or "").strip() or "operator_resume_after_resource_change",
        "resumed_at": now.isoformat(),
        "previous_node_policy_fingerprint": previous_policy,
        "current_node_policy_fingerprint": current_policy,
        "previous_resource_profile_fingerprint": previous_profile,
        "current_resource_profile_fingerprint": current_profile,
    }
    previous_payload = getattr(task, "blocked_payload", None)
    transitioned = store.try_resume_resource_block(
        task.id,
        expected_blocked_reason=blocked_reason,
        execution_context=updated_context,
        resumed_at=now,
    )
    if not transitioned:
        raise ResourceBlockResumeError("resource_block_changed_concurrently")
    enqueued = await queue.enqueue_task(task.id)
    if not enqueued:
        store.update_task(
            task.id,
            execution_context=context,
            blocked_reason=blocked_reason,
            blocked_payload=previous_payload,
            next_eligible_at=getattr(task, "next_eligible_at", now),
            frontier_state="cold",
            frontier_enqueued_at=None,
        )
        raise ResourceBlockResumeError(
            "resource_resume_queue_unavailable",
            status_code=503,
        )
    return {
        "success": True,
        "task_id": task.id,
        "queue_shard": queue_shard,
        "state": "queued",
        "node_policy_fingerprint": current_policy,
        "resource_profile_fingerprint": current_profile,
    }
