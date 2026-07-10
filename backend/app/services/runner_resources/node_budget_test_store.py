"""Deterministic in-memory node-budget store for contract tests."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .node_budget_contract import (
    NODE_BUDGET_ID,
    NodeBudgetAcquireResult,
    NodeBudgetPolicy,
    NodeBudgetReservation,
)


class InMemoryNodeBudgetStore:
    def __init__(self, *, now_epoch: float = 0.0):
        self.now_epoch = float(now_epoch)
        self.revision = 0
        self.reservations: dict[str, NodeBudgetReservation] = {}
        self.policy: NodeBudgetPolicy | None = None

    def advance(self, seconds: float) -> None:
        self.now_epoch += max(0.0, float(seconds))

    def _purge(self) -> None:
        self.reservations = {
            owner: reservation
            for owner, reservation in self.reservations.items()
            if reservation.expires_at_epoch > self.now_epoch
        }

    async def acquire(
        self,
        *,
        owner_id: str,
        request_bytes: int,
        policy: NodeBudgetPolicy,
        profile_fingerprint: str,
        ttl_seconds: int,
    ) -> NodeBudgetAcquireResult:
        self._purge()
        self.policy = policy
        existing = self.reservations.get(owner_id)
        reserved = sum(item.bytes for item in self.reservations.values())
        if existing:
            if (
                existing.bytes != request_bytes
                or existing.policy_fingerprint != policy.fingerprint
                or existing.resource_profile_fingerprint != profile_fingerprint
            ):
                return NodeBudgetAcquireResult(
                    False,
                    "node_budget_owner_conflict",
                    None,
                    reserved,
                    request_bytes,
                    policy,
                )
            refreshed = NodeBudgetReservation(
                **{
                    **asdict(existing),
                    "expires_at_epoch": self.now_epoch + max(1, int(ttl_seconds)),
                }
            )
            self.reservations[owner_id] = refreshed
            return NodeBudgetAcquireResult(
                True,
                None,
                refreshed,
                reserved,
                request_bytes,
                policy,
            )
        if request_bytes <= 0 or reserved + request_bytes > policy.allocatable_bytes:
            return NodeBudgetAcquireResult(
                False,
                "node_budget_exhausted",
                None,
                reserved,
                request_bytes,
                policy,
            )
        self.revision += 1
        reservation = NodeBudgetReservation(
            owner_id=owner_id,
            bytes=request_bytes,
            revision=self.revision,
            expires_at_epoch=self.now_epoch + max(1, int(ttl_seconds)),
            policy_fingerprint=policy.fingerprint,
            resource_profile_fingerprint=profile_fingerprint,
            allocatable_bytes=policy.allocatable_bytes,
            policy_mode=policy.mode,
        )
        self.reservations[owner_id] = reservation
        return NodeBudgetAcquireResult(
            True,
            None,
            reservation,
            reserved + request_bytes,
            request_bytes,
            policy,
        )

    async def renew(
        self,
        reservation: NodeBudgetReservation,
        *,
        ttl_seconds: int,
    ) -> bool:
        self._purge()
        current = self.reservations.get(reservation.owner_id)
        if not current or current.revision != reservation.revision:
            return False
        self.reservations[reservation.owner_id] = NodeBudgetReservation(
            **{
                **asdict(current),
                "expires_at_epoch": self.now_epoch + max(1, int(ttl_seconds)),
            }
        )
        return True

    async def release(self, reservation: NodeBudgetReservation) -> bool:
        self._purge()
        current = self.reservations.get(reservation.owner_id)
        if not current or current.revision != reservation.revision:
            return False
        self.reservations.pop(reservation.owner_id, None)
        return True

    async def snapshot(self) -> dict[str, Any]:
        self._purge()
        reservations = [item.to_context() for item in self.reservations.values()]
        policy = self.policy
        return {
            "available": True,
            "budget_id": NODE_BUDGET_ID,
            "reserved_bytes": sum(item["bytes"] for item in reservations),
            "active_reservations": len(reservations),
            "revision": self.revision,
            "allocatable_bytes": (
                policy.allocatable_bytes if policy is not None else None
            ),
            "policy_mode": policy.mode if policy is not None else None,
            "policy_fingerprint": (
                policy.fingerprint if policy is not None else None
            ),
            "reservations": reservations,
        }
