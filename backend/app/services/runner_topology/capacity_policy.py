"""Capacity helpers for runner profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .profile_registry import RunnerProfile


@dataclass(frozen=True)
class RunnerCapacitySnapshot:
    max_inflight: int
    inflight: int
    available_slots: int
    poll_batch_limit: int
    saturated: bool


def resolve_runner_poll_batch_limit(
    profile: RunnerProfile,
    configured_limit: Optional[int] = None,
) -> int:
    if isinstance(configured_limit, int) and configured_limit > 0:
        return max(configured_limit, profile.max_inflight)
    return max(50, profile.max_inflight * 10)


def resolve_runner_capacity_snapshot(
    profile: RunnerProfile,
    *,
    inflight: int,
    configured_poll_batch_limit: Optional[int] = None,
) -> RunnerCapacitySnapshot:
    current_inflight = max(0, int(inflight or 0))
    max_inflight = max(1, int(profile.max_inflight or 1))
    available_slots = max(0, max_inflight - current_inflight)
    poll_batch_limit = resolve_runner_poll_batch_limit(
        profile,
        configured_limit=configured_poll_batch_limit,
    )
    return RunnerCapacitySnapshot(
        max_inflight=max_inflight,
        inflight=current_inflight,
        available_slots=available_slots,
        poll_batch_limit=poll_batch_limit,
        saturated=available_slots <= 0,
    )


def runner_profile_has_capacity(profile: RunnerProfile, *, inflight: int) -> bool:
    return not resolve_runner_capacity_snapshot(profile, inflight=inflight).saturated
