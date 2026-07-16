"""Canonical exact-owner release for task resource ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .leases import RedisResourceLeaseStore, resource_lease_keys_from_context
from .node_budget import RedisNodeBudgetStore, reservation_from_context
from .node_budget_contract import NodeBudgetReservation, NodeBudgetStore


@dataclass(frozen=True)
class TaskResourceOwnershipReleaseResult:
    owner_id: str
    requested_lease_keys: tuple[str, ...]
    released_lease_keys: tuple[str, ...]
    unreleased_lease_keys: tuple[str, ...]
    node_reservation_requested: bool
    node_reservation_released: Optional[bool]
    node_reservation_owner_mismatch: bool
    errors: tuple[str, ...]

    @property
    def complete(self) -> bool:
        node_complete = (
            not self.node_reservation_requested
            or self.node_reservation_released is True
        )
        return bool(
            not self.errors
            and not self.unreleased_lease_keys
            and not self.node_reservation_owner_mismatch
            and node_complete
        )


def _normalize_lease_keys(lease_keys: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_key in lease_keys:
        key = str(raw_key or "").strip()
        if key and key not in seen:
            normalized.append(key)
            seen.add(key)
    return tuple(normalized)


async def release_task_resource_ownership(
    redis_queue: Any,
    *,
    owner_id: str,
    lease_keys: Iterable[str] = (),
    node_budget_reservation: Optional[NodeBudgetReservation] = None,
    lease_store: Any = None,
    node_budget_store: Optional[NodeBudgetStore] = None,
) -> TaskResourceOwnershipReleaseResult:
    """Release only resource ownership held by the supplied exact owner."""

    normalized_owner = str(owner_id or "").strip()
    requested_lease_keys = _normalize_lease_keys(lease_keys)
    released_lease_keys: list[str] = []
    unreleased_lease_keys: list[str] = []
    errors: list[str] = []
    reservation_requested = node_budget_reservation is not None
    reservation_released: Optional[bool] = None
    reservation_owner_mismatch = False

    if not normalized_owner:
        errors.append("owner_id_required")
        unreleased_lease_keys.extend(requested_lease_keys)
        if reservation_requested:
            reservation_released = False
    elif redis_queue is None and lease_store is None and node_budget_store is None:
        errors.append("redis_queue_required")
        unreleased_lease_keys.extend(requested_lease_keys)
        if reservation_requested:
            reservation_released = False
    else:
        resolved_lease_store = lease_store
        if requested_lease_keys and resolved_lease_store is None:
            try:
                resolved_lease_store = RedisResourceLeaseStore(redis_queue)
            except Exception as exc:
                errors.append(f"lease_store:{type(exc).__name__}:{exc}")
        for lease_key in requested_lease_keys:
            if resolved_lease_store is None:
                unreleased_lease_keys.append(lease_key)
                continue
            try:
                released = bool(
                    await resolved_lease_store.release(lease_key, normalized_owner)
                )
            except Exception as exc:
                errors.append(
                    f"lease:{lease_key}:{type(exc).__name__}:{exc}"
                )
                released = False
            if released:
                released_lease_keys.append(lease_key)
            else:
                unreleased_lease_keys.append(lease_key)

        if node_budget_reservation is not None:
            if node_budget_reservation.owner_id != normalized_owner:
                reservation_owner_mismatch = True
                reservation_released = False
            else:
                try:
                    resolved_node_store = node_budget_store or RedisNodeBudgetStore(
                        redis_queue
                    )
                    reservation_released = bool(
                        await resolved_node_store.release(node_budget_reservation)
                    )
                except Exception as exc:
                    errors.append(
                        f"node_reservation:{type(exc).__name__}:{exc}"
                    )
                    reservation_released = False

    return TaskResourceOwnershipReleaseResult(
        owner_id=normalized_owner,
        requested_lease_keys=requested_lease_keys,
        released_lease_keys=tuple(released_lease_keys),
        unreleased_lease_keys=tuple(unreleased_lease_keys),
        node_reservation_requested=reservation_requested,
        node_reservation_released=reservation_released,
        node_reservation_owner_mismatch=reservation_owner_mismatch,
        errors=tuple(errors),
    )


async def release_task_resource_ownership_from_context(
    redis_queue: Any,
    *,
    task_id: str,
    runner_id: str,
    execution_context: Optional[dict[str, Any]],
    lease_store: Any = None,
    node_budget_store: Optional[NodeBudgetStore] = None,
) -> TaskResourceOwnershipReleaseResult:
    """Resolve persisted task ownership and release it with the exact owner."""

    normalized_task_id = str(task_id or "").strip()
    normalized_runner_id = str(runner_id or "").strip()
    owner_id = (
        f"{normalized_runner_id}:{normalized_task_id}"
        if normalized_runner_id and normalized_task_id
        else ""
    )
    context = execution_context if isinstance(execution_context, dict) else {}
    return await release_task_resource_ownership(
        redis_queue,
        owner_id=owner_id,
        lease_keys=resource_lease_keys_from_context(context),
        node_budget_reservation=reservation_from_context(context),
        lease_store=lease_store,
        node_budget_store=node_budget_store,
    )


__all__ = [
    "TaskResourceOwnershipReleaseResult",
    "release_task_resource_ownership",
    "release_task_resource_ownership_from_context",
]
