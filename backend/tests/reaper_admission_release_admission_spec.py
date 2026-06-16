from datetime import timedelta

import pytest

from backend.app.models.workspace import _utc_now
from backend.app.runner import reaper
from backend.app.services.task_admission_service import (
    ADMISSION_DEFERRED_REASON,
    AdmissionDecision,
)
from backend.tests.reaper_admission_release_support import (
    _FakeAdmissionService,
    _FakeRedisQueue,
    _FakeTasksStore,
    _build_deferred_task,
)


@pytest.mark.asyncio
async def test_releases_due_deferred_task_when_capacity_available(monkeypatch):
    store = _FakeTasksStore([_build_deferred_task()])
    queue = _FakeRedisQueue("ig_analysis")
    monkeypatch.setattr(
        reaper,
        "TASK_ADMISSION_SERVICE",
        _FakeAdmissionService(
            AdmissionDecision(
                allow=True,
                queue_shard="ig_analysis",
                execution_context={"auto_triggered": True},
            )
        ),
    )

    released = await reaper._release_admission_deferred_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert store.release_candidate_calls == 1
    assert queue._client.enqueued == ["task-1"]
    assert store.updated[0][0] == "task-1"
    assert store.updated[0][1]["blocked_reason"] is None
    assert store.updated[0][1]["frontier_state"] == "ready"


@pytest.mark.asyncio
async def test_reextends_deferred_task_when_capacity_still_exceeded(monkeypatch):
    store = _FakeTasksStore([_build_deferred_task()])
    queue = _FakeRedisQueue("ig_analysis")
    next_eligible_at = _utc_now() + timedelta(seconds=45)
    monkeypatch.setattr(
        reaper,
        "TASK_ADMISSION_SERVICE",
        _FakeAdmissionService(
            AdmissionDecision(
                allow=False,
                queue_shard="ig_analysis",
                execution_context={
                    "auto_triggered": True,
                    "admission": {"state": "deferred"},
                },
                blocked_payload={"reason": "pending_limit"},
                next_eligible_at=next_eligible_at,
            )
        ),
    )

    released = await reaper._release_admission_deferred_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 0
    assert queue._client.enqueued == []
    assert store.updated[0][1]["blocked_reason"] == ADMISSION_DEFERRED_REASON
    assert store.updated[0][1]["frontier_state"] == "cold"
    assert store.updated[0][1]["next_eligible_at"] == next_eligible_at
    assert "execution_context" not in store.updated[0][1]
