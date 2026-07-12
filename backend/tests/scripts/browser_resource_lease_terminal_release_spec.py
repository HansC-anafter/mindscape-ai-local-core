from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.maintenance.browser_resource_lease_terminal_release import (
    validate_terminal_lease_release_identity,
)


OWNER = "runner-1:task-1"
LEASE_KEY = "mindscape:runner_resources:lease:v1:ig_profile_lock:profile:key"


def _task(status: str = "failed", lease_key: str = LEASE_KEY) -> SimpleNamespace:
    return SimpleNamespace(
        id="task-1",
        status=status,
        execution_context={
            "runner_resource_leases": [
                {
                    "lease_key": lease_key,
                    "resource_type": "ig_profile_lock",
                    "resource_id": "profile",
                }
            ]
        },
    )


def test_terminal_exact_absent_live_owner_passes() -> None:
    validate_terminal_lease_release_identity(
        task=_task(),
        task_id="task-1",
        expected_owner=OWNER,
        expected_lease_key=LEASE_KEY,
        live_lease_owner=OWNER,
        task_live_ttl=-2,
        runner_task_live_ttl=-2,
    )


@pytest.mark.parametrize(
    ("task", "owner", "task_ttl", "runner_ttl", "error"),
    [
        (_task("running"), OWNER, -2, -2, "task_not_terminal"),
        (_task(lease_key="different"), OWNER, -2, -2, "task_lease_key_mismatch"),
        (_task(), "different", -2, -2, "live_lease_owner_mismatch"),
        (_task(), OWNER, 60, -2, "live_owner_still_present"),
        (_task(), OWNER, -2, 60, "live_owner_still_present"),
    ],
)
def test_terminal_lease_release_identity_fails_closed(
    task: SimpleNamespace,
    owner: str,
    task_ttl: int,
    runner_ttl: int,
    error: str,
) -> None:
    with pytest.raises(RuntimeError, match=error):
        validate_terminal_lease_release_identity(
            task=task,
            task_id="task-1",
            expected_owner=OWNER,
            expected_lease_key=LEASE_KEY,
            live_lease_owner=owner,
            task_live_ttl=task_ttl,
            runner_task_live_ttl=runner_ttl,
        )
