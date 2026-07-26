import pytest

from backend.app.services.host_runtime_bindings.state_machine import (
    FINALIZER,
    next_generation,
    transition_binding,
)


def test_generation_is_compare_and_swap_only():
    assert next_generation(current_generation=3, expected_generation=3) == 4
    with pytest.raises(ValueError, match="generation_conflict"):
        next_generation(current_generation=3, expected_generation=2)


def test_retirement_keeps_finalizer_until_grants_and_cleanup_are_terminal():
    state, finalizers = transition_binding(
        current_state="active",
        requested_state="retiring",
        active_grant_count=2,
        supervisor_cleanup_terminal=False,
    )
    assert state == "retiring"
    assert finalizers == (FINALIZER,)

    with pytest.raises(ValueError, match="active_grants"):
        transition_binding(
            current_state="retiring",
            requested_state="retired",
            active_grant_count=1,
            supervisor_cleanup_terminal=True,
        )
    with pytest.raises(ValueError, match="cleanup_not_terminal"):
        transition_binding(
            current_state="retiring",
            requested_state="retired",
            active_grant_count=0,
            supervisor_cleanup_terminal=False,
        )
    assert transition_binding(
        current_state="retiring",
        requested_state="retired",
        active_grant_count=0,
        supervisor_cleanup_terminal=True,
    ) == ("retired", ())
