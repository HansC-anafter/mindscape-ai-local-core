from types import SimpleNamespace

import pytest

from backend.app.models.workspace import TaskStatus
from backend.app.services.runner_resources import resource_block_control
from backend.app.services.runner_resources.resource_block_control import (
    ResourceBlockResumeError,
    resume_resource_blocked_task,
)


class _Store:
    def __init__(self):
        self.task = SimpleNamespace(
            id="task-1",
            workspace_id="ws-1",
            status=TaskStatus.PENDING,
            blocked_reason="resource_exhausted",
            blocked_payload={"evidence": "kept"},
            next_eligible_at=None,
            frontier_state="cold",
            queue_shard="browser_local",
            pack_id="ig_batch_pin_references",
            execution_context={
                "inputs": {"checkpoint": "checkpoint-7"},
                "resource_block": {
                    "node_policy_fingerprint": "old-policy",
                    "resource_profile_fingerprint": "old-profile",
                    "requested_memory_bytes": 4096,
                },
            },
        )
        self.transitions = 0
        self.rollback = None

    def get_task(self, task_id):
        assert task_id == self.task.id
        return self.task

    def try_resume_resource_block(self, task_id, **kwargs):
        assert task_id == self.task.id
        assert kwargs["expected_blocked_reason"] == "resource_exhausted"
        self.transitions += 1
        self.task.execution_context = kwargs["execution_context"]
        self.task.blocked_reason = None
        self.task.frontier_state = "ready"
        return True

    def update_task(self, task_id, **kwargs):
        self.rollback = (task_id, kwargs)


class _Queue:
    instances = []
    enqueue_ok = True

    def __init__(self, pack_id):
        self.pack_id = pack_id
        self.enqueued = []
        self.__class__.instances.append(self)

    async def enqueue_task(self, task_id):
        self.enqueued.append(task_id)
        return self.enqueue_ok


@pytest.mark.asyncio
async def test_resume_rejects_unchanged_contract(monkeypatch):
    store = _Store()

    async def _same(*_args, **_kwargs):
        return "old-policy", "old-profile"

    monkeypatch.setattr(resource_block_control, "_current_fingerprints", _same)
    monkeypatch.setattr(resource_block_control, "RedisRunnerQueueStore", _Queue)

    with pytest.raises(ResourceBlockResumeError, match="resource_contract_unchanged"):
        await resume_resource_blocked_task(
            workspace_id="ws-1",
            task_id="task-1",
            reason="profile calibrated",
            tasks_store=store,
        )
    assert store.transitions == 0


@pytest.mark.asyncio
async def test_resume_changed_contract_transitions_and_enqueues_once(monkeypatch):
    store = _Store()
    _Queue.instances.clear()

    async def _changed(*_args, **_kwargs):
        return "new-policy", "new-profile"

    monkeypatch.setattr(resource_block_control, "_current_fingerprints", _changed)
    monkeypatch.setattr(resource_block_control, "RedisRunnerQueueStore", _Queue)

    result = await resume_resource_blocked_task(
        workspace_id="ws-1",
        task_id="task-1",
        reason="measured profile deployed",
        tasks_store=store,
    )

    assert result["state"] == "queued"
    assert store.transitions == 1
    assert _Queue.instances[-1].enqueued == ["task-1"]
    assert store.task.execution_context["inputs"]["checkpoint"] == "checkpoint-7"
    assert "resource_block" not in store.task.execution_context
