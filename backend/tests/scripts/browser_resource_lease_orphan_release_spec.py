from types import SimpleNamespace

import pytest

from scripts.maintenance.browser_resource_lease_orphan_release import (
    validate_pending_orphan_lease_release_identity,
)


LEASE_KEY = "mindscape:runner_resources:lease:v1:ig_profile_lock:profile:hash"


def _kwargs():
    return {
        "task": SimpleNamespace(
            id="task-1",
            status="pending",
            runner_id=None,
            execution_context={
                "resource_admission": {
                    "state": "waiting",
                    "resource_keys": [LEASE_KEY],
                }
            },
        ),
        "task_id": "task-1",
        "expected_owner": "dead-runner:task-1",
        "expected_lease_key": LEASE_KEY,
        "live_lease_owner": "dead-runner:task-1",
        "task_live_ttl": -2,
        "runner_task_live_ttl": -2,
        "runner_heartbeat_ttl": -2,
        "processing_score": None,
    }


def test_pending_orphan_lease_release_requires_every_owner_signal_absent():
    validate_pending_orphan_lease_release_identity(**_kwargs())


@pytest.mark.parametrize(
    "status",
    ["succeeded", "failed", "cancelled_by_user", "expired"],
)
def test_terminal_orphan_lease_release_requires_every_owner_signal_absent(status):
    kwargs = _kwargs()
    kwargs["task"].status = status
    kwargs["task"].execution_context["runner_id"] = "dead-runner"

    validate_pending_orphan_lease_release_identity(**kwargs)


def test_orphan_lease_release_rejects_running_task():
    kwargs = _kwargs()
    kwargs["task"].status = "running"

    with pytest.raises(RuntimeError, match="task_not_inactive"):
        validate_pending_orphan_lease_release_identity(**kwargs)


def test_terminal_orphan_lease_release_rejects_different_context_runner():
    kwargs = _kwargs()
    kwargs["task"].status = "failed"
    kwargs["task"].execution_context["runner_id"] = "other-runner"

    with pytest.raises(RuntimeError, match="task_runner_owner_still_present"):
        validate_pending_orphan_lease_release_identity(**kwargs)


def test_pending_orphan_lease_release_accepts_key_rebuilt_from_wait_requirements():
    kwargs = _kwargs()
    profile_path = "/app/data/ig-browser-profiles/chaos.300_"
    from backend.app.services.runner_resources.lease_keys import (
        build_resource_lease_key,
    )

    kwargs["expected_lease_key"] = build_resource_lease_key(
        "ig_profile_lock", profile_path
    )
    kwargs["task"].execution_context = {
        "resource_admission": {
            "state": "waiting",
            "requirements": {"ig_profile_lock": profile_path},
        }
    }
    kwargs["task"].blocked_payload = {
        "requirements": {"ig_profile_lock": profile_path}
    }

    validate_pending_orphan_lease_release_identity(**kwargs)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("task_live_ttl", 30, "live_owner_still_present"),
        ("runner_task_live_ttl", 30, "live_owner_still_present"),
        ("runner_heartbeat_ttl", 30, "runner_heartbeat_still_present"),
        ("processing_score", 1.0, "task_processing_owner_still_present"),
        ("live_lease_owner", "other-runner:task-1", "live_lease_owner_mismatch"),
    ],
)
def test_pending_orphan_lease_release_fails_closed_on_mismatch(field, value, reason):
    kwargs = _kwargs()
    kwargs[field] = value

    with pytest.raises(RuntimeError, match=reason):
        validate_pending_orphan_lease_release_identity(**kwargs)
