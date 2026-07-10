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
    reserved_bytes: int
    additional_request_bytes: tuple[int, ...]
    missing_request_workload_count: int
    mem_available_bytes: int
    running_count: int
    running_physical_profile_count: int
    runnable_physical_profile_count: int
    duplicate_running_physical_profile_count: int
    selected_candidate_count: int
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
    if any(request <= 0 for request in inputs.additional_request_bytes):
        raise ValueError("additional request bytes must be positive")

    required_available_bytes = sum(inputs.additional_request_bytes)
    projected_reserved_bytes = inputs.reserved_bytes + required_available_bytes
    remaining_bytes = max(0, inputs.allocatable_bytes - inputs.reserved_bytes)
    byte_capacity = inputs.running_physical_profile_count
    for request_bytes in inputs.additional_request_bytes:
        if request_bytes > remaining_bytes:
            break
        remaining_bytes -= request_bytes
        byte_capacity += 1
    blockers: list[str] = []

    required_gate_state = "paused" if inputs.mode == "pre-resume" else "open"
    if inputs.claim_gate_state != required_gate_state:
        blockers.append(f"claim_gate_must_be_{required_gate_state}")
    if inputs.missing_request_workload_count > 0:
        blockers.append("request_evidence_incomplete")
    if inputs.runnable_physical_profile_count < inputs.required_concurrency:
        blockers.append("physical_profile_capacity_below_required")
    if byte_capacity < inputs.required_concurrency:
        blockers.append("byte_capacity_below_required")
    if inputs.mem_available_bytes < required_available_bytes:
        blockers.append("mem_available_below_required")
    if inputs.runner_slot_capacity < inputs.required_concurrency:
        blockers.append("runner_slot_capacity_below_required")
    if inputs.duplicate_running_physical_profile_count > 0:
        blockers.append("duplicate_running_physical_profile")
    if inputs.oom_kill_count > 0 or inputs.oom_group_kill_count > 0:
        blockers.append("runner_cgroup_oom_counter_nonzero")
    if inputs.mode == "post-resume":
        if inputs.running_count < inputs.required_concurrency:
            blockers.append("actual_running_below_required")
        if inputs.running_physical_profile_count < inputs.required_concurrency:
            blockers.append("running_physical_profiles_below_required")
        if inputs.processing_count < inputs.required_concurrency:
            blockers.append("processing_count_below_required")

    return {
        "verdict": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "mode": inputs.mode,
        "required_concurrency": inputs.required_concurrency,
        "byte_capacity": byte_capacity,
        "required_available_bytes": required_available_bytes,
        "projected_reserved_bytes": projected_reserved_bytes,
        "inputs": asdict(inputs),
    }
