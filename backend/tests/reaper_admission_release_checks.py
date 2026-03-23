from datetime import timedelta

import pytest

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner import reaper
from backend.app.services.task_admission_service import (
    ADMISSION_DEFERRED_REASON,
    AdmissionDecision,
)


class _FakePipeline:
    def __init__(self, client):
        self.client = client
        self._pending: list[str] = []

    def lpush(self, _queue_name, task_id):
        self._pending.append(task_id)

    async def execute(self):
        self.client.enqueued.extend(self._pending)


class _FakeRedisClient:
    def __init__(self):
        self.enqueued: list[str] = []

    def pipeline(self):
        return _FakePipeline(self)


class _FakeRedisQueue:
    def __init__(self, pack_id: str):
        self.pack_id = pack_id
        self.q_pending = f"{pack_id}:pending"
        self._client = _FakeRedisClient()

    async def _get_client(self):
        return self._client


class _FakeTasksStore:
    def __init__(self, tasks):
        self._tasks = list(tasks)
        self.updated: list[tuple[str, dict]] = []

    def list_due_admission_deferred_tasks(self, *, queue_shard=None, limit=200):
        return self._tasks[:limit]

    def update_task(self, task_id, **kwargs):
        self.updated.append((task_id, kwargs))


class _FakeAdmissionService:
    def __init__(self, decision: AdmissionDecision):
        self.decision = decision

    def evaluate_on_release(self, _tasks_store, _task):
        return self.decision


def _build_deferred_task() -> Task:
    now = _utc_now()
    return Task(
        id="task-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="ig_analyze_pinned_reference",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="ig_analysis",
        created_at=now,
        next_eligible_at=now,
        blocked_reason=ADMISSION_DEFERRED_REASON,
        frontier_state="cold",
        execution_context={
            "auto_triggered": True,
            "admission_policy": {
                "mode": "auto",
                "visibility": "background",
                "producer_kind": "pin_reference",
            },
            "admission": {
                "state": "deferred",
                "reason": "pending_limit",
                "visibility": "background",
                "producer_kind": "pin_reference",
                "queue_shard": "ig_analysis",
            },
        },
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
