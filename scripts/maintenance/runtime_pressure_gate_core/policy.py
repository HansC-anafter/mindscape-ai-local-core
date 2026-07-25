"""Action-scoped policy for local runtime pressure evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROTECTED_RUNNER_CAPACITY = 9
RUNTIME_OBSERVATION_ACTION = "runtime-observation"
RUNNER_ROLLING_RELOAD_ACTION = "runner-rolling-reload"
BACKEND_RELOAD_ACTION = "backend-reload"
ALLOWED_ACTIONS = {
    RUNTIME_OBSERVATION_ACTION,
    RUNNER_ROLLING_RELOAD_ACTION,
    BACKEND_RELOAD_ACTION,
}


@dataclass(frozen=True)
class GateScope:
    action: str = RUNTIME_OBSERVATION_ACTION
    target_runner_container: str | None = None
    allow_sole_owner_target: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target_runner_container": self.target_runner_container,
            "allow_sole_owner_target": self.allow_sole_owner_target,
        }


def _normalized_lane_identity(row: dict[str, Any]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    profile = str(row.get("profile") or "").strip()
    partitions = tuple(
        sorted(
            item.strip()
            for item in str(row.get("accepted_partitions") or "").split(",")
            if item.strip()
        )
    )
    resource_classes = tuple(
        sorted(
            item.strip()
            for item in str(row.get("accepted_resource_classes") or "").split(",")
            if item.strip()
        )
    )
    return profile, partitions, resource_classes


def runner_scope_evidence(
    runner_capacity: dict[str, Any],
    scope: GateScope,
) -> dict[str, Any]:
    rows = [
        row
        for row in runner_capacity.get("rows") or []
        if isinstance(row, dict)
    ]
    evidence: dict[str, Any] = {
        **scope.to_dict(),
        "protected_runner_capacity": PROTECTED_RUNNER_CAPACITY,
        "aggregate_max_inflight": int(
            runner_capacity.get("aggregate_max_inflight") or 0
        ),
    }
    if scope.action != RUNNER_ROLLING_RELOAD_ACTION:
        return evidence

    target_name = str(scope.target_runner_container or "").strip()
    target = next(
        (
            row
            for row in rows
            if str(row.get("container") or "").strip() == target_name
        ),
        None,
    )
    evidence["target_found"] = target is not None
    if target is None:
        return evidence

    lane_identity = _normalized_lane_identity(target)
    evidence["target_lane_identity"] = {
        "profile": lane_identity[0],
        "accepted_partitions": list(lane_identity[1]),
        "accepted_resource_classes": list(lane_identity[2]),
    }
    compatible_rows = [
        row
        for row in rows
        if row is not target and _normalized_lane_identity(row) == lane_identity
    ]
    evidence["compatible_peer_containers"] = [
        str(row.get("container") or "").strip() for row in compatible_rows
    ]
    evidence["compatible_peer_capacity"] = sum(
        int(row.get("max_inflight") or 0) for row in compatible_rows
    )
    evidence["target_max_inflight"] = int(target.get("max_inflight") or 0)
    return evidence


def evaluate_runner_scope(
    runner_capacity: dict[str, Any],
    scope: GateScope,
) -> list[str]:
    failures: list[str] = []
    aggregate = int(runner_capacity.get("aggregate_max_inflight") or 0)
    if aggregate < PROTECTED_RUNNER_CAPACITY:
        failures.append(f"runner_capacity_below_{PROTECTED_RUNNER_CAPACITY}")

    if scope.action not in ALLOWED_ACTIONS:
        failures.append("runtime_gate_action_invalid")
        return failures
    if scope.action != RUNNER_ROLLING_RELOAD_ACTION:
        return failures

    evidence = runner_scope_evidence(runner_capacity, scope)
    if not str(scope.target_runner_container or "").strip():
        failures.append("target_runner_container_required")
    elif not evidence.get("target_found"):
        failures.append("target_runner_container_not_active")
    elif not (evidence.get("target_lane_identity") or {}).get("profile"):
        failures.append("target_runner_profile_missing")
    elif (
        int(evidence.get("compatible_peer_capacity") or 0) <= 0
        and not scope.allow_sole_owner_target
    ):
        failures.append("target_runner_sole_owner_requires_explicit_flag")
    return failures
