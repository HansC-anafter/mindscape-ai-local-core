"""Resource-aware task admission."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .leases import (
    LEASE_CONTEXT_KEY,
    ResourceLease,
    ResourceLeaseStore,
    build_resource_lease_key,
)
from .requirements import ResourceRequirements
from .node_budget import (
    NODE_BUDGET_CONTEXT_KEY,
    NodeBudgetReservation,
    NodeBudgetStore,
    current_node_memory_snapshot,
    resolve_browser_request_bytes,
    resolve_node_budget_policy,
    resource_profile_fingerprint,
)

RESOURCE_WAIT_REASON = "resource_wait"


@dataclass(frozen=True)
class ResourceAdmissionDecision:
    allow: bool
    requirements: ResourceRequirements
    blocked_reason: Optional[str] = None
    blocked_payload: Optional[dict[str, Any]] = None
    next_eligible_at: Optional[datetime] = None
    acquired_leases: list[ResourceLease] = field(default_factory=list)
    node_budget_reservation: Optional[NodeBudgetReservation] = None
    execution_context_updates: dict[str, Any] = field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _profile_code(profile: Any) -> str:
    return str(getattr(profile, "profile_code", "") or "runner").strip() or "runner"


def _available_slots(capacity: Any) -> int:
    return max(0, int(getattr(capacity, "available_slots", 0) or 0))


def _task_id(task: Any) -> str:
    if isinstance(task, dict):
        return str(task.get("id") or "").strip()
    return str(getattr(task, "id", "") or "").strip()


def _host_resource_admission_enabled() -> bool:
    raw = os.getenv("LOCAL_CORE_HOST_RESOURCE_ADMISSION_ENABLED", "true")
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _requires_host_resource_gate(requirements: ResourceRequirements) -> bool:
    if requirements.resource_class == "browser" or requirements.browser_contexts > 0:
        return False
    return bool(
        requirements.memory_mb > 0
        or requirements.vision_lane
        or requirements.llm_lane
    )


def _evaluate_host_resource_gate(requirements: ResourceRequirements) -> Optional[Any]:
    if not _host_resource_admission_enabled() or not _requires_host_resource_gate(requirements):
        return None
    try:
        from backend.app.services.host_resources import evaluate_runner_requirements

        return evaluate_runner_requirements(requirements)
    except Exception:
        return None


def _resource_entries(requirements: ResourceRequirements) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if requirements.ig_profile_lock:
        entries.append(("ig_profile_lock", requirements.ig_profile_lock))
    return entries


async def acquire_task_resource_admission(
    *,
    task: Any,
    requirements: ResourceRequirements,
    runner_profile: Any,
    capacity: Any,
    lease_store: ResourceLeaseStore,
    node_budget_store: Optional[NodeBudgetStore] = None,
    node_memory_snapshot: Optional[dict[str, Any]] = None,
    owner_id: str,
    ttl_seconds: int,
    delay_seconds: int = 30,
    now: Optional[datetime] = None,
) -> ResourceAdmissionDecision:
    base_now = now or _utc_now()

    if requirements.browser_contexts > _available_slots(capacity):
        return _blocked_decision(
            requirements=requirements,
            reason="browser_contexts_unavailable",
            delay_seconds=delay_seconds,
            now=base_now,
            task=task,
            runner_profile=runner_profile,
        )

    host_advice = _evaluate_host_resource_gate(requirements)
    if host_advice is not None and not bool(getattr(host_advice, "allow", False)):
        host_payload = getattr(host_advice, "payload", {}) or {}
        lane_id = host_payload.get("lane_id") if isinstance(host_payload, dict) else None
        resource_key = f"host_resource:{lane_id or 'requirements'}"
        return _blocked_decision(
            requirements=requirements,
            reason=str(getattr(host_advice, "reason", None) or getattr(host_advice, "decision", "host_resource_blocked")),
            delay_seconds=delay_seconds,
            now=base_now,
            task=task,
            runner_profile=runner_profile,
            resource_key=resource_key,
            extra_payload={
                "blocked_resource": "host_resource",
                "host_decision": getattr(host_advice, "decision", "defer"),
                "host_advisor": host_payload,
            },
        )

    node_reservation: Optional[NodeBudgetReservation] = None
    is_browser = (
        requirements.resource_class == "browser"
        or requirements.browser_contexts > 0
    )
    node_policy = None
    resolved_request_bytes = 0
    resolved_request_source = requirements.memory_reservation_source
    profile_fingerprint = ""
    if is_browser:
        snapshot = node_memory_snapshot or current_node_memory_snapshot()
        node_policy = resolve_node_budget_policy(snapshot)
        request_resolution = resolve_browser_request_bytes(requirements, snapshot)
        if node_policy is None or request_resolution is None:
            return _blocked_decision(
                requirements=requirements,
                reason="browser_memory_requirement_unavailable",
                delay_seconds=delay_seconds,
                now=base_now,
                task=task,
                runner_profile=runner_profile,
                extra_payload={
                    "blocked_resource": "node_memory",
                    "node_memory_snapshot": snapshot,
                },
            )
        resolved_request_bytes, resolved_request_source = request_resolution
        try:
            available_bytes = int(snapshot.get("available_bytes") or 0)
        except (TypeError, ValueError):
            available_bytes = 0
        if available_bytes < resolved_request_bytes:
            return _blocked_decision(
                requirements=requirements,
                reason="node_memory_headroom_unavailable",
                delay_seconds=delay_seconds,
                now=base_now,
                task=task,
                runner_profile=runner_profile,
                extra_payload={
                    "blocked_resource": "node_memory",
                    "requested_bytes": resolved_request_bytes,
                    "available_bytes": available_bytes,
                    "node_policy_fingerprint": node_policy.fingerprint,
                },
            )
        if node_budget_store is None:
            return _blocked_decision(
                requirements=requirements,
                reason="node_budget_unavailable",
                delay_seconds=delay_seconds,
                now=base_now,
                task=task,
                runner_profile=runner_profile,
                extra_payload={"blocked_resource": "node_budget"},
            )
        profile_fingerprint = resource_profile_fingerprint(
            requirements,
            resolved_request_bytes,
        )
        node_decision = await node_budget_store.acquire(
            owner_id=owner_id,
            request_bytes=resolved_request_bytes,
            policy=node_policy,
            profile_fingerprint=profile_fingerprint,
            ttl_seconds=ttl_seconds,
        )
        if not node_decision.allow or node_decision.reservation is None:
            return _blocked_decision(
                requirements=requirements,
                reason=node_decision.reason or "node_budget_exhausted",
                delay_seconds=delay_seconds,
                now=base_now,
                task=task,
                runner_profile=runner_profile,
                extra_payload={
                    "blocked_resource": "node_budget",
                    "requested_bytes": resolved_request_bytes,
                    "reserved_bytes": node_decision.reserved_bytes,
                    "allocatable_bytes": node_policy.allocatable_bytes,
                    "node_policy_fingerprint": node_policy.fingerprint,
                    "resource_profile_fingerprint": profile_fingerprint,
                },
            )
        node_reservation = node_decision.reservation

    acquired: list[ResourceLease] = []
    for resource_type, resource_id in _resource_entries(requirements):
        lease_key = build_resource_lease_key(resource_type, resource_id)
        lease = ResourceLease(
            lease_key=lease_key,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        ok = await lease_store.acquire(lease_key, owner_id, ttl_seconds)
        if not ok:
            await release_acquired_resource_leases(
                lease_store,
                acquired,
                owner_id=owner_id,
            )
            if node_reservation is not None and node_budget_store is not None:
                await node_budget_store.release(node_reservation)
            return _blocked_decision(
                requirements=requirements,
                reason=f"{resource_type}_leased",
                delay_seconds=delay_seconds,
                now=base_now,
                task=task,
                runner_profile=runner_profile,
                resource_key=lease_key,
            )
        acquired.append(lease)

    context_updates: dict[str, Any] = {}
    if acquired or node_reservation is not None:
        context_updates[LEASE_CONTEXT_KEY] = [
            lease.to_context() for lease in acquired
        ]
        if node_reservation is not None:
            context_updates[NODE_BUDGET_CONTEXT_KEY] = (
                node_reservation.to_context()
            )
        context_updates["resource_admission"] = {
            "state": "admitted",
            "task_id": _task_id(task),
            "runner_profile": _profile_code(runner_profile),
            "requirements": requirements.to_dict(),
            "lease_keys": [lease.lease_key for lease in acquired],
            "requested_memory_bytes": resolved_request_bytes,
            "memory_reservation_source": resolved_request_source,
            "node_policy_fingerprint": (
                node_policy.fingerprint if node_policy is not None else None
            ),
            "resource_profile_fingerprint": profile_fingerprint or None,
            "admitted_at": base_now.isoformat(),
        }

    return ResourceAdmissionDecision(
        allow=True,
        requirements=requirements,
        acquired_leases=acquired,
        node_budget_reservation=node_reservation,
        execution_context_updates=context_updates,
    )


async def release_acquired_resource_leases(
    lease_store: ResourceLeaseStore,
    leases: list[ResourceLease],
    *,
    owner_id: str,
) -> None:
    for lease in leases:
        await lease_store.release(lease.lease_key, owner_id)


async def release_acquired_resource_admission(
    *,
    lease_store: ResourceLeaseStore,
    node_budget_store: Optional[NodeBudgetStore],
    decision: ResourceAdmissionDecision,
    owner_id: str,
) -> None:
    await release_acquired_resource_leases(
        lease_store,
        decision.acquired_leases,
        owner_id=owner_id,
    )
    if decision.node_budget_reservation is not None and node_budget_store is not None:
        await node_budget_store.release(decision.node_budget_reservation)


def _blocked_decision(
    *,
    requirements: ResourceRequirements,
    reason: str,
    delay_seconds: int,
    now: datetime,
    task: Any,
    runner_profile: Any,
    resource_key: Optional[str] = None,
    extra_payload: Optional[dict[str, Any]] = None,
) -> ResourceAdmissionDecision:
    next_eligible_at = now + timedelta(seconds=max(1, int(delay_seconds or 1)))
    payload = {
        "policy": RESOURCE_WAIT_REASON,
        "reason": reason,
        "task_id": _task_id(task),
        "runner_profile": _profile_code(runner_profile),
        "requirements": requirements.to_dict(),
        "defer_until": next_eligible_at.isoformat(),
        "evaluated_at": now.isoformat(),
    }
    if extra_payload:
        payload.update(extra_payload)
    if resource_key:
        payload["resource_key"] = resource_key
        payload["resource_keys"] = [resource_key]
    return ResourceAdmissionDecision(
        allow=False,
        requirements=requirements,
        blocked_reason=RESOURCE_WAIT_REASON,
        blocked_payload=payload,
        next_eligible_at=next_eligible_at,
    )


def build_resource_wait_task_update(
    task_ctx: Optional[dict[str, Any]],
    decision: ResourceAdmissionDecision,
    *,
    current_queue_shard: Optional[str],
) -> dict[str, Any]:
    ctx2 = dict(task_ctx) if isinstance(task_ctx, dict) else {}
    blocked_payload = decision.blocked_payload or {}
    resource_keys = blocked_payload.get("resource_keys")
    if not isinstance(resource_keys, list):
        resource_keys = []
    resource_key = blocked_payload.get("resource_key")
    if isinstance(resource_key, str) and resource_key.strip():
        resource_keys = [resource_key.strip(), *resource_keys]
    resource_keys = list(
        dict.fromkeys(str(key).strip() for key in resource_keys if str(key).strip())
    )
    previous_runner_id = ctx2.pop("runner_id", None)
    ctx2.pop("heartbeat_at", None)
    if previous_runner_id and not ctx2.get("last_runner_id"):
        ctx2["last_runner_id"] = previous_runner_id
    next_eligible_at = decision.next_eligible_at or (_utc_now() + timedelta(seconds=30))
    ctx2["resume_after"] = next_eligible_at.isoformat()
    ctx2["resource_admission"] = {
        "state": "waiting",
        "reason": blocked_payload.get("reason"),
        "defer_until": next_eligible_at.isoformat(),
        "requirements": decision.requirements.to_dict(),
    }
    if resource_keys:
        ctx2["resource_admission"]["resource_keys"] = resource_keys
    ctx2.pop(LEASE_CONTEXT_KEY, None)
    ctx2.pop(NODE_BUDGET_CONTEXT_KEY, None)
    return {
        "execution_context": ctx2,
        "next_eligible_at": next_eligible_at,
        "blocked_reason": RESOURCE_WAIT_REASON,
        "blocked_payload": decision.blocked_payload,
        "frontier_state": "cold",
        "frontier_enqueued_at": None,
        "queue_shard": current_queue_shard,
    }
