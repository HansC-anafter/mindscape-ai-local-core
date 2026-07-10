"""Pure normal-service capacity acceptance policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CapacityInputs:
    mode: str
    required_concurrency: int
    claim_gate_state: str
    allocatable_bytes: int
    request_bytes: int
    mem_available_bytes: int
    running_count: int
    running_distinct_locks: int
    runnable_distinct_locks: int
    duplicate_running_lock_count: int
    runner_slot_capacity: int
    processing_count: int
    oom_kill_count: int
    oom_group_kill_count: int


def evaluate_capacity(inputs: CapacityInputs) -> dict[str, Any]:
    """Evaluate one pre-resume or post-resume acceptance snapshot."""

    if inputs.mode not in {"pre-resume", "post-resume"}:
        raise ValueError("mode must be pre-resume or post-resume")
    if inputs.required_concurrency <= 0:
        raise ValueError("required_concurrency must be positive")
    if inputs.request_bytes <= 0:
        raise ValueError("request_bytes must be positive")

    byte_capacity = max(0, inputs.allocatable_bytes // inputs.request_bytes)
    additional_tasks = max(0, inputs.required_concurrency - inputs.running_count)
    required_available_bytes = additional_tasks * inputs.request_bytes
    blockers: list[str] = []

    required_gate_state = "paused" if inputs.mode == "pre-resume" else "open"
    if inputs.claim_gate_state != required_gate_state:
        blockers.append(f"claim_gate_must_be_{required_gate_state}")
    if byte_capacity < inputs.required_concurrency:
        blockers.append("byte_capacity_below_required")
    if inputs.mem_available_bytes < required_available_bytes:
        blockers.append("mem_available_below_required")
    if inputs.runnable_distinct_locks < inputs.required_concurrency:
        blockers.append("distinct_runnable_locks_below_required")
    if inputs.runner_slot_capacity < inputs.required_concurrency:
        blockers.append("runner_slot_capacity_below_required")
    if inputs.duplicate_running_lock_count > 0:
        blockers.append("duplicate_running_profile_lock")
    if inputs.oom_kill_count > 0 or inputs.oom_group_kill_count > 0:
        blockers.append("runner_cgroup_oom_counter_nonzero")
    if inputs.mode == "post-resume":
        if inputs.running_count < inputs.required_concurrency:
            blockers.append("actual_running_below_required")
        if inputs.running_distinct_locks < inputs.required_concurrency:
            blockers.append("running_distinct_locks_below_required")
        if inputs.processing_count < inputs.required_concurrency:
            blockers.append("processing_count_below_required")

    return {
        "verdict": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "mode": inputs.mode,
        "required_concurrency": inputs.required_concurrency,
        "byte_capacity": byte_capacity,
        "required_available_bytes": required_available_bytes,
        "inputs": asdict(inputs),
    }
