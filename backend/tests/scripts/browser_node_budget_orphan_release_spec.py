from types import SimpleNamespace

import pytest

from scripts.maintenance.browser_node_budget_orphan_release import (
    validate_pending_orphan_release_identity,
)


def _reservation():
    return {
        "owner_id": "dead-runner:task-1",
        "bytes": 192,
        "revision": 9,
        "expires_at_epoch": 1000.0,
        "policy_fingerprint": "policy",
        "resource_profile_fingerprint": "profile",
        "allocatable_bytes": 4096,
        "policy_mode": "calibrated",
    }


def test_pending_orphan_release_requires_every_owner_signal_absent():
    reservation = validate_pending_orphan_release_identity(
        task=SimpleNamespace(
            id="task-1",
            status="pending",
            runner_id=None,
            execution_context={},
        ),
        task_id="task-1",
        expected_owner="dead-runner:task-1",
        expected_revision=9,
        live_reservation=_reservation(),
        task_live_ttl=-2,
        runner_task_live_ttl=-2,
        runner_heartbeat_ttl=-2,
        processing_score=None,
    )

    assert reservation.owner_id == "dead-runner:task-1"
    assert reservation.revision == 9


@pytest.mark.parametrize(
    "status",
    ["succeeded", "failed", "cancelled_by_user", "expired"],
)
def test_terminal_orphan_release_requires_every_owner_signal_absent(status):
    reservation = validate_pending_orphan_release_identity(
        task=SimpleNamespace(
            id="task-1",
            status=status,
            runner_id=None,
            execution_context={"runner_id": "dead-runner"},
        ),
        task_id="task-1",
        expected_owner="dead-runner:task-1",
        expected_revision=9,
        live_reservation=_reservation(),
        task_live_ttl=-2,
        runner_task_live_ttl=-2,
        runner_heartbeat_ttl=-2,
        processing_score=None,
    )

    assert reservation.owner_id == "dead-runner:task-1"


def test_terminal_orphan_release_rejects_different_context_runner():
    with pytest.raises(RuntimeError, match="task_runner_owner_still_present"):
        validate_pending_orphan_release_identity(
            task=SimpleNamespace(
                id="task-1",
                status="failed",
                runner_id=None,
                execution_context={"runner_id": "other-runner"},
            ),
            task_id="task-1",
            expected_owner="dead-runner:task-1",
            expected_revision=9,
            live_reservation=_reservation(),
            task_live_ttl=-2,
            runner_task_live_ttl=-2,
            runner_heartbeat_ttl=-2,
            processing_score=None,
        )


def test_orphan_release_rejects_running_task():
    with pytest.raises(RuntimeError, match="task_not_inactive"):
        validate_pending_orphan_release_identity(
            task=SimpleNamespace(
                id="task-1",
                status="running",
                runner_id=None,
                execution_context={},
            ),
            task_id="task-1",
            expected_owner="dead-runner:task-1",
            expected_revision=9,
            live_reservation=_reservation(),
            task_live_ttl=-2,
            runner_task_live_ttl=-2,
            runner_heartbeat_ttl=-2,
            processing_score=None,
        )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("task_live_ttl", 30, "live_owner_still_present"),
        ("runner_task_live_ttl", 30, "live_owner_still_present"),
        ("runner_heartbeat_ttl", 30, "runner_heartbeat_still_present"),
        ("processing_score", 1.0, "task_processing_owner_still_present"),
    ],
)
def test_pending_orphan_release_fails_closed_on_active_signal(field, value, reason):
    kwargs = {
        "task": SimpleNamespace(
            id="task-1",
            status="pending",
            runner_id=None,
            execution_context={},
        ),
        "task_id": "task-1",
        "expected_owner": "dead-runner:task-1",
        "expected_revision": 9,
        "live_reservation": _reservation(),
        "task_live_ttl": -2,
        "runner_task_live_ttl": -2,
        "runner_heartbeat_ttl": -2,
        "processing_score": None,
    }
    kwargs[field] = value

    with pytest.raises(RuntimeError, match=reason):
        validate_pending_orphan_release_identity(**kwargs)
