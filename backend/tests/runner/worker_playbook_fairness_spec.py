import asyncio

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner import worker
from backend.app.runner.worker import (
    _build_parked_task_update,
    _dequeue_by_route_gate_policy,
)
from backend.app.runner.database_backoff import (
    RunnerDatabaseRecoveryBackoff,
    is_database_recovery_error,
)
from backend.app.services.host_resources import route_gate
from backend.app.services.host_resources.route_identity_projection import (
    serialize_route_identity_projection,
)
from backend.app.services.runner_topology.profile_registry import RunnerProfile


class _FakeFairClient:
    def __init__(self, ids):
        self.ids = ids
        self.projections = {}

    async def lrange(self, queue_name, start, end):
        return self.ids[start : end + 1]

    async def mget(self, keys):
        return [self.projections.get(key) for key in keys]


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


def _projection(task_id: str, pack_id: str, *, lane_id: str = "runner:default_local"):
    return {
        "task_id": task_id,
        "pack_id": pack_id,
        "playbook_code": pack_id,
        "task_type": "playbook_execution",
        "workspace_id": "ws-1",
        "queue_shard": "browser_local",
        "route_identity": {
            "lane_id": lane_id,
            "resource_groups": [lane_id],
            "priority_class": "default",
            "pack_id": pack_id,
            "playbook_code": pack_id,
        },
    }


def _browser_profile() -> RunnerProfile:
    return RunnerProfile(
        profile_code="browser_local",
        display_name="Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("browser_local",),
        max_inflight=2,
    )


def test_route_gate_policy_selects_playbook_diversity():
    queue = _FakeFairQueue(["task-following", "task-batch"])
    for task_id, pack_id in {
        "task-following": "ig_analyze_following",
        "task-batch": "ig_batch_pin_references",
    }.items():
        queue.client.projections[
            f"mindscape:host_resources:route_identity:{task_id}"
        ] = serialize_route_identity_projection(task_id, _projection(task_id, pack_id))

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_route_gate_policy(
            [queue],
            runner_profile=_browser_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
            active_pack_ids={"ig_batch_pin_references"},
        )
    )

    assert task_id == "task-following"
    assert queue_store is queue
    assert drain_wait is False
    assert queue.promoted == ["task-following"]


def test_route_gate_policy_falls_back_when_only_same_playbook():
    queue = _FakeFairQueue(["task-batch-a", "task-batch-b"])
    for task_id in ["task-batch-a", "task-batch-b"]:
        queue.client.projections[
            f"mindscape:host_resources:route_identity:{task_id}"
        ] = serialize_route_identity_projection(
            task_id,
            _projection(task_id, "ig_batch_pin_references"),
        )

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_route_gate_policy(
            [queue],
            runner_profile=_browser_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
            active_pack_ids={"ig_batch_pin_references"},
        )
    )

    assert task_id is None
    assert queue_store is None
    assert drain_wait is False
    assert queue.promoted == []


def test_route_gate_policy_waits_for_drain_after_current(monkeypatch):
    queue = _FakeFairQueue(["task-default"])
    queue.client.projections[
        "mindscape:host_resources:route_identity:task-default"
    ] = serialize_route_identity_projection(
        "task-default",
        _projection("task-default", "ig_batch_pin_references"),
    )
    monkeypatch.setattr(
        route_gate,
        "list_active_route_reservations",
        lambda: [
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["mps_generation"],
                    "drain_policy": "drain_after_current",
                },
            }
        ],
    )

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_route_gate_policy(
            [queue],
            runner_profile=_browser_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
            active_pack_ids=set(),
        )
    )

    assert task_id is None
    assert queue_store is None
    assert drain_wait is True
    assert queue.promoted == []


def test_database_recovery_error_detection_and_backoff():
    exc = RuntimeError(
        'connection to server at "postgres" failed: FATAL:  the database system is not yet accepting connections'
    )
    backoff = RunnerDatabaseRecoveryBackoff(delay_seconds=5)

    assert is_database_recovery_error(exc) is True
    assert backoff.note_failure(exc) is True
    assert backoff.is_active() is True
    assert backoff.remaining_seconds() > 0


def test_parked_pending_update_clears_live_runner_ownership():
    update = _build_parked_task_update(
        {
            "playbook_code": "ig_batch_pin_references",
            "runner_id": "runner-old",
            "heartbeat_at": "2026-05-08T03:00:00+00:00",
        },
        reason="concurrency_locked",
        delay_seconds=30,
        lock_key="ig:source:a",
        conflicting_lock_key="ig:source:a",
        current_queue_shard="browser_local",
    )

    ctx = update["execution_context"]
    assert ctx["last_runner_id"] == "runner-old"
    assert "runner_id" not in ctx
    assert "heartbeat_at" not in ctx
    assert update["frontier_state"] == "cold"
    assert update["queue_shard"] == "browser_local"


def test_runner_lock_ttl_uses_runtime_configuration(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", "3600")

    assert worker._runner_lock_ttl_seconds() == 3600
