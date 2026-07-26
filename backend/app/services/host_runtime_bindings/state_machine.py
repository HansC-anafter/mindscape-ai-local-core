"""Pure generation and lifecycle transitions for device host bindings."""

from __future__ import annotations

from .contracts import BindingDesiredState


FINALIZER = "mindscape.ai/host-runtime-cleanup"
ALLOWED_TRANSITIONS: dict[BindingDesiredState, set[BindingDesiredState]] = {
    "declared": {"materialized", "retiring"},
    "materialized": {"active", "degraded", "retiring"},
    "active": {"degraded", "retiring"},
    "degraded": {"active", "retiring"},
    "retiring": {"retired"},
    "retired": set(),
}


def next_generation(*, current_generation: int, expected_generation: int) -> int:
    if current_generation != expected_generation:
        raise ValueError("host_binding_generation_conflict")
    return current_generation + 1


def transition_binding(
    *,
    current_state: BindingDesiredState,
    requested_state: BindingDesiredState,
    active_grant_count: int,
    supervisor_cleanup_terminal: bool,
) -> tuple[BindingDesiredState, tuple[str, ...]]:
    if requested_state not in ALLOWED_TRANSITIONS[current_state]:
        raise ValueError("host_binding_state_transition_invalid")
    if requested_state == "retired":
        if active_grant_count != 0:
            raise ValueError("host_binding_active_grants_block_retirement")
        if not supervisor_cleanup_terminal:
            raise ValueError("host_binding_cleanup_not_terminal")
        return requested_state, ()
    if requested_state == "retiring":
        return requested_state, (FINALIZER,)
    return requested_state, (FINALIZER,)
