from datetime import datetime, timezone

from backend.app.services.stores.tasks_store._runner import (
    _build_claim_execution_context,
)


def test_claim_context_clears_stale_deferred_metadata():
    now = datetime(2026, 5, 8, 3, 30, tzinfo=timezone.utc)

    ctx = _build_claim_execution_context(
        {
            "inputs": {"target_handle": "example"},
            "retry_count": 2,
            "resource_wait_count": 1,
            "resource_pressure_source": "subprocess_sigkill",
            "resource_pressure": True,
            "resource_retry_delay_sec": 300,
            "resource_snapshot": {"memory": {"working_set_ratio": 0.91}},
            "runner_id": "old-runner",
            "heartbeat_at": "2026-05-08T03:00:00+00:00",
            "resume_after": "2026-05-08T03:05:00+00:00",
            "runner_skip_reason": "concurrency_locked",
            "error": "previous failure",
            "failed_at": "2026-05-08T03:00:01+00:00",
        },
        runner_id="new-runner",
        now=now,
    )

    assert ctx["inputs"] == {"target_handle": "example"}
    assert ctx["retry_count"] == 2
    assert ctx["resource_wait_count"] == 1
    assert ctx["runner_id"] == "new-runner"
    assert ctx["heartbeat_at"] == "2026-05-08T03:30:00+00:00"
    assert ctx["status"] == "running"

    for stale_key in (
        "resource_pressure_source",
        "resource_pressure",
        "resource_retry_delay_sec",
        "resource_snapshot",
        "resume_after",
        "runner_skip_reason",
        "error",
        "failed_at",
    ):
        assert stale_key not in ctx
