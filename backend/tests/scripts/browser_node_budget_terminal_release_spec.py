from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.maintenance.browser_node_budget_terminal_release import (
    validate_terminal_release_identity,
)


OWNER = "runner-1:task-1"
RESERVATION = {
    "owner_id": OWNER,
    "bytes": 1024,
    "revision": 7,
    "expires_at_epoch": 1000.0,
    "policy_fingerprint": "policy",
    "resource_profile_fingerprint": "profile",
    "allocatable_bytes": 4096,
    "policy_mode": "calibrated",
}


def _task(status: str = "failed") -> SimpleNamespace:
    return SimpleNamespace(
        id="task-1",
        status=status,
        execution_context={"runner_node_budget_reservation": RESERVATION},
    )


def test_terminal_exact_absent_live_owner_passes() -> None:
    reservation = validate_terminal_release_identity(
        task=_task(),
        task_id="task-1",
        expected_owner=OWNER,
        expected_revision=7,
        live_reservation=RESERVATION,
        task_live_ttl=-2,
        runner_task_live_ttl=-2,
    )
    assert reservation.owner_id == OWNER
    assert reservation.revision == 7


@pytest.mark.parametrize(
    ("status", "revision", "task_ttl", "runner_ttl", "error"),
    [
        ("running", 7, -2, -2, "task_not_terminal"),
        ("failed", 8, -2, -2, "task_reservation_revision_mismatch"),
        ("failed", 7, 60, -2, "live_owner_still_present"),
        ("failed", 7, -2, 60, "live_owner_still_present"),
    ],
)
def test_terminal_release_identity_fails_closed(
    status: str,
    revision: int,
    task_ttl: int,
    runner_ttl: int,
    error: str,
) -> None:
    with pytest.raises(RuntimeError, match=error):
        validate_terminal_release_identity(
            task=_task(status),
            task_id="task-1",
            expected_owner=OWNER,
            expected_revision=revision,
            live_reservation=RESERVATION,
            task_live_ttl=task_ttl,
            runner_task_live_ttl=runner_ttl,
        )
