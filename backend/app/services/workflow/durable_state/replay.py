"""Bounded, effect-free replay and comparison for execution history."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable


class ReplayCompatibilityError(ValueError):
    """Raised when bounded history cannot be replayed exactly."""


@dataclass(frozen=True)
class ReplayResult:
    sequence: int
    event_hash: str | None
    state: dict
    reducer_version: str
    compatibility_identity: dict[str, str] = field(default_factory=dict)


def reduce_as_of(
    *,
    initial_state: dict,
    events: list[dict],
    target_sequence: int,
    reducer: Callable[[dict, dict], dict],
    reducer_version: str,
) -> ReplayResult:
    state = deepcopy(initial_state)
    previous_sequence = int(state.get("last_sequence", 0))
    previous_hash = state.get("last_event_hash")
    for event in events:
        sequence = int(event["sequence"])
        if sequence > target_sequence:
            break
        if sequence != previous_sequence + 1:
            raise ReplayCompatibilityError("event sequence is not contiguous")
        if event["previous_event_hash"] != previous_hash:
            raise ReplayCompatibilityError("event predecessor hash is invalid")
        state = reducer(state, event)
        previous_sequence = sequence
        previous_hash = event["event_hash"]
    if previous_sequence != target_sequence:
        raise ReplayCompatibilityError("target exceeds the bounded replay window")
    return ReplayResult(
        sequence=previous_sequence,
        event_hash=previous_hash,
        state=state,
        reducer_version=reducer_version,
    )


def compare_results(left: ReplayResult, right: ReplayResult) -> dict:
    bookkeeping = {"last_sequence", "last_event_hash"}
    differing = sorted(
        key
        for key in set(left.state) | set(right.state)
        if key not in bookkeeping
        if left.state.get(key) != right.state.get(key)
    )
    compatibility_reasons = []
    if left.reducer_version != right.reducer_version:
        compatibility_reasons.append("reducer_version")
    for key in sorted(
        set(left.compatibility_identity) | set(right.compatibility_identity)
    ):
        if (
            left.compatibility_identity.get(key)
            != right.compatibility_identity.get(key)
        ):
            compatibility_reasons.append(key)
    return {
        "left_sequence": left.sequence,
        "right_sequence": right.sequence,
        "left_event_hash": left.event_hash,
        "right_event_hash": right.event_hash,
        "compatible": not compatibility_reasons,
        "compatibility_reasons": compatibility_reasons,
        "differing_fields": differing,
    }
