import asyncio

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner.worker import _dequeue_preferred_different_playbook
from backend.app.services.runner_topology.profile_registry import RunnerProfile


class _FakeFairClient:
    def __init__(self, ids):
        self.ids = ids

    async def lrange(self, queue_name, start, end):
        return self.ids[start : end + 1]


class _FakeFairQueue:
    pack_id = "browser_local"
    q_pending = "pending:browser_local"

    def __init__(self, ids):
        self.client = _FakeFairClient(ids)
        self.promoted: list[str] = []

    async def _get_client(self):
        return self.client

    async def promote_pending_task_by_id(
        self,
        task_id: str,
        visibility_timeout_sec: int = 180,
    ):
        self.promoted.append(task_id)
        return task_id


class _FakeTaskStore:
    def __init__(self, tasks):
        self.tasks = tasks

    def get_task(self, task_id):
        return self.tasks.get(task_id)


def _pending_browser_task(task_id: str, pack_id: str) -> Task:
    now = _utc_now()
    return Task(
        id=task_id,
        workspace_id="ws-1",
        message_id=f"msg-{task_id}",
        execution_id=f"exec-{task_id}",
        pack_id=pack_id,
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="browser_local",
        execution_context={"queue_shard": "browser_local"},
        created_at=now,
    )


def _browser_profile() -> RunnerProfile:
    return RunnerProfile(
        profile_code="browser_local",
        display_name="Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("browser_local",),
        max_inflight=2,
    )


def test_dequeue_preferred_different_playbook_selects_lane_diversity():
    queue = _FakeFairQueue(["task-following", "task-batch"])

    task_id, queue_store = asyncio.run(
        _dequeue_preferred_different_playbook(
            [queue],
            tasks_store=_FakeTaskStore(
                {
                    "task-following": _pending_browser_task(
                        "task-following",
                        "ig_analyze_following",
                    ),
                    "task-batch": _pending_browser_task(
                        "task-batch",
                        "ig_batch_pin_references",
                    ),
                }
            ),
            excluded_pack_ids={"ig_batch_pin_references"},
            runner_profile=_browser_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
        )
    )

    assert task_id == "task-following"
    assert queue_store is queue
    assert queue.promoted == ["task-following"]


def test_dequeue_preferred_different_playbook_falls_back_when_only_same_lane():
    queue = _FakeFairQueue(["task-batch-a", "task-batch-b"])

    task_id, queue_store = asyncio.run(
        _dequeue_preferred_different_playbook(
            [queue],
            tasks_store=_FakeTaskStore(
                {
                    "task-batch-a": _pending_browser_task(
                        "task-batch-a",
                        "ig_batch_pin_references",
                    ),
                    "task-batch-b": _pending_browser_task(
                        "task-batch-b",
                        "ig_batch_pin_references",
                    ),
                }
            ),
            excluded_pack_ids={"ig_batch_pin_references"},
            runner_profile=_browser_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
        )
    )

    assert task_id is None
    assert queue_store is None
    assert queue.promoted == []
