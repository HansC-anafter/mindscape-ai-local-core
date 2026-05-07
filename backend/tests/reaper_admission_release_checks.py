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
        self.release_candidate_calls = 0
        self.concurrency_locked_calls = 0
        self.dependency_hold_calls = 0
        self.unblocked_cold_calls = 0

    def list_running_playbook_execution_tasks(self, *, workspace_id=None, limit=200):
        return [
            task for task in self._tasks if task.status == TaskStatus.RUNNING
        ][:limit]

    def list_frontier_running_pending_tasks(self, *, workspace_id=None, limit=200):
        return [
            task
            for task in self._tasks
            if task.status == TaskStatus.PENDING
            and getattr(task, "frontier_state", None) == "running"
        ][:limit]

    def list_due_admission_deferred_tasks(self, *, queue_shard=None, limit=200):
        return self._tasks[:limit]

    def list_due_admission_deferred_release_candidates(
        self, *, queue_shard=None, limit=200
    ):
        self.release_candidate_calls += 1
        return self._tasks[:limit]

    def list_due_concurrency_locked_tasks(self, *, queue_shard=None, limit=200):
        self.concurrency_locked_calls += 1
        return self._tasks[:limit]

    def list_due_dependency_hold_tasks(self, *, queue_shard=None, limit=200):
        self.dependency_hold_calls += 1
        return self._tasks[:limit]

    def list_due_unblocked_cold_tasks(self, *, queue_shard=None, limit=200):
        self.unblocked_cold_calls += 1
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


def _build_concurrency_locked_task() -> Task:
    now = _utc_now()
    return Task(
        id="task-locked",
        workspace_id="ws-1",
        message_id="msg-locked",
        execution_id="exec-locked",
        pack_id="ig_batch_pin_references",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="browser_local",
        created_at=now - timedelta(minutes=5),
        next_eligible_at=now - timedelta(minutes=1),
        blocked_reason="concurrency_locked",
        frontier_state="cold",
        execution_context={
            "playbook_code": "ig_batch_pin_references",
            "runner_skip_reason": "concurrency_locked",
            "runner_skip_lock_key": "concurrency:playbook_input:ig_batch_pin_references:profile-a",
            "runner_skip_conflict_lock_key": "concurrency:playbook_input:ig_batch_pin_references:profile-a",
            "resume_after": now.isoformat(),
            "inputs": {
                "workspace_id": "ws-1",
                "target_handle": "sample",
                "user_data_dir": "profile-a",
            },
        },
    )


def _build_dependency_hold_task() -> Task:
    now = _utc_now()
    return Task(
        id="task-dependency",
        workspace_id="ws-1",
        message_id="msg-dependency",
        execution_id="exec-dependency",
        pack_id="vision_reference_analyze",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="vision_local",
        created_at=now - timedelta(minutes=5),
        next_eligible_at=now - timedelta(minutes=1),
        blocked_reason="dependency_hold",
        frontier_state="cold",
        execution_context={
            "playbook_code": "vision_reference_analyze",
            "dependency_hold": {"deps": ["mlx"], "checked_at": now.isoformat()},
            "resume_after": now.isoformat(),
        },
    )


def _build_unblocked_cold_task() -> Task:
    now = _utc_now()
    return Task(
        id="task-cold",
        workspace_id="ws-1",
        message_id="msg-cold",
        execution_id="exec-cold",
        pack_id="vision_reference_analyze",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="vision_local",
        created_at=now - timedelta(minutes=5),
        next_eligible_at=now - timedelta(minutes=1),
        blocked_reason=None,
        frontier_state="cold",
        execution_context={"playbook_code": "vision_reference_analyze"},
    )


def _build_stale_queued_running_task_without_owner() -> Task:
    now = _utc_now()
    return Task(
        id="task-orphan-running",
        workspace_id="ws-1",
        message_id="msg-orphan",
        execution_id="exec-orphan",
        pack_id="ig_batch_pin_references",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="browser_local",
        created_at=now - timedelta(hours=2),
        started_at=now - timedelta(hours=2),
        next_eligible_at=now - timedelta(hours=2),
        frontier_state="running",
        execution_context={
            "playbook_code": "ig_batch_pin_references",
            "status": "queued",
            "runner_reaper": {
                "action": "startup_reset",
                "previous_runner_id": "runner-old",
                "new_runner_id": "runner-current",
            },
            "inputs": {
                "workspace_id": "ws-1",
                "target_handle": "sample",
                "user_data_dir": "profile-a",
            },
        },
    )


def _build_running_browser_task(
    *,
    pack_id: str = "browser_profile_scan",
    heartbeat_age_seconds: int = 30,
    current_step_index: int = 0,
    started_age_seconds: int = 3600,
) -> Task:
    now = _utc_now()
    return Task(
        id="task-watchdog",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-watchdog",
        pack_id=pack_id,
        task_type="playbook_execution",
        status=TaskStatus.RUNNING,
        queue_shard="browser_local",
        created_at=now - timedelta(seconds=started_age_seconds),
        started_at=now - timedelta(seconds=started_age_seconds),
        execution_context={
            "runner_id": "runner-1",
            "heartbeat_at": (now - timedelta(seconds=heartbeat_age_seconds)).isoformat(),
            "status": "running",
            "current_step_index": current_step_index,
            "no_progress_watchdog": {
                "enabled": True,
                "artifact_progress_source": "browser_profile_scan_progress",
            },
        },
    )


class _FakeExecution:
    def __init__(self, *, updated_at, created_at=None, phase="queue"):
        self.updated_at = updated_at
        self.created_at = created_at or updated_at
        self.phase = phase


class _FakeExecutionStore:
    def __init__(self, executions):
        self.executions = dict(executions)

    def get_execution(self, execution_id: str):
        return self.executions.get(execution_id)


class _FakeArtifact:
    def __init__(self, *, metadata=None, content=None):
        self.metadata = metadata or {}
        self.content = content or {}


class _FakeArtifactsStore:
    def __init__(self, artifacts):
        self.artifacts = dict(artifacts)

    def get_by_execution_id(self, execution_id: str):
        return self.artifacts.get(execution_id)


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


@pytest.mark.asyncio
async def test_releases_due_concurrency_locked_task_to_ready_queue():
    store = _FakeTasksStore([_build_concurrency_locked_task()])
    queue = _FakeRedisQueue("browser_local")

    released = await reaper._release_concurrency_locked_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert store.concurrency_locked_calls == 1
    assert queue._client.enqueued == ["task-locked"]
    assert store.updated[0][0] == "task-locked"
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["blocked_payload"] is None
    assert update["frontier_state"] == "ready"
    assert update["queue_shard"] == "browser_local"
    assert update["frontier_enqueued_at"] is not None
    assert "runner_skip_reason" not in update["execution_context"]
    assert "runner_skip_lock_key" not in update["execution_context"]
    assert "runner_skip_conflict_lock_key" not in update["execution_context"]
    assert "resume_after" not in update["execution_context"]


@pytest.mark.asyncio
async def test_releases_due_dependency_hold_task_to_ready_queue():
    store = _FakeTasksStore([_build_dependency_hold_task()])
    queue = _FakeRedisQueue("vision_local")

    released = await reaper._release_dependency_hold_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert store.dependency_hold_calls == 1
    assert queue._client.enqueued == ["task-dependency"]
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["blocked_payload"] is None
    assert update["frontier_state"] == "ready"
    assert update["queue_shard"] == "vision_local"
    assert "dependency_hold" not in update["execution_context"]
    assert "resume_after" not in update["execution_context"]


@pytest.mark.asyncio
async def test_releases_due_unblocked_cold_task_to_ready_queue():
    store = _FakeTasksStore([_build_unblocked_cold_task()])
    queue = _FakeRedisQueue("vision_local")

    released = await reaper._release_unblocked_cold_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert store.unblocked_cold_calls == 1
    assert queue._client.enqueued == ["task-cold"]
    update = store.updated[0][1]
    assert update["blocked_reason"] is None
    assert update["blocked_payload"] is None
    assert update["frontier_state"] == "ready"
    assert update["queue_shard"] == "vision_local"


def test_requeues_stale_queued_running_task_without_runner_owner(monkeypatch):
    task = _build_stale_queued_running_task_without_owner()
    store = _FakeTasksStore([task])
    monkeypatch.setenv("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", "180")

    reaper._reap_stale_running_tasks(store, "runner-new", redis_queue=None)

    assert len(store.updated) == 1
    assert store.updated[0][0] == "task-orphan-running"
    update = store.updated[0][1]
    assert update["status"] == TaskStatus.PENDING
    assert update["started_at"] is None
    assert update["blocked_reason"] is None
    assert update["frontier_state"] == "ready"
    assert update["frontier_enqueued_at"] is not None
    assert update["next_eligible_at"] is not None
    updated_ctx = update["execution_context"]
    assert updated_ctx["status"] == "queued"
    assert updated_ctx["runner_reaper"]["action"] == "requeue_orphan_no_runner"
    assert "runner_id" not in updated_ctx
    assert "heartbeat_at" not in updated_ctx


def test_requests_watchdog_abort_for_running_task_with_no_progress(monkeypatch):
    task = _build_running_browser_task()
    store = _FakeTasksStore([task])
    execution_store = _FakeExecutionStore(
        {
            "exec-watchdog": _FakeExecution(
                updated_at=_utc_now() - timedelta(minutes=20),
                phase="queue",
            )
        }
    )
    monkeypatch.setenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_SECONDS", "600")
    monkeypatch.delenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_PACKS", raising=False)

    requested = reaper._request_watchdog_abort_for_no_progress_tasks(
        store,
        watcher_id="test-watchdog",
        execution_store=execution_store,
    )

    assert requested == 1
    assert len(store.updated) == 1
    updated_ctx = store.updated[0][1]["execution_context"]
    assert updated_ctx["watchdog_abort_requested_at"]
    assert "Runner no-progress watchdog tripped" in updated_ctx["watchdog_abort_reason"]
    assert updated_ctx["watchdog_abort"]["phase"] == "queue"
    assert updated_ctx["watchdog_abort"]["watcher_id"] == "test-watchdog"


def test_skips_watchdog_abort_for_fresh_resume_with_stale_execution(monkeypatch):
    task = _build_running_browser_task(started_age_seconds=30)
    task.execution_context["auto_resume_count"] = 1
    task.execution_context["auto_resume_from_task_id"] = "old-task"
    store = _FakeTasksStore([task])
    execution_store = _FakeExecutionStore(
        {
            "exec-watchdog": _FakeExecution(
                updated_at=_utc_now() - timedelta(minutes=20),
                phase="queue",
            )
        }
    )
    monkeypatch.setenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_SECONDS", "600")
    monkeypatch.delenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_PACKS", raising=False)

    requested = reaper._request_watchdog_abort_for_no_progress_tasks(
        store,
        watcher_id="test-watchdog",
        execution_store=execution_store,
    )

    assert requested == 0
    assert store.updated == []


def test_skips_watchdog_abort_once_progress_has_started(monkeypatch):
    task = _build_running_browser_task(current_step_index=1)
    store = _FakeTasksStore([task])
    execution_store = _FakeExecutionStore(
        {
            "exec-watchdog": _FakeExecution(
                updated_at=_utc_now() - timedelta(minutes=20),
                phase="queue",
            )
        }
    )
    monkeypatch.setenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_SECONDS", "600")
    monkeypatch.delenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_PACKS", raising=False)

    requested = reaper._request_watchdog_abort_for_no_progress_tasks(
        store,
        watcher_id="test-watchdog",
        execution_store=execution_store,
    )

    assert requested == 0
    assert store.updated == []


def test_skips_watchdog_abort_when_artifact_semantic_progress_is_fresh(monkeypatch):
    task = _build_running_browser_task()
    store = _FakeTasksStore([task])
    execution_store = _FakeExecutionStore(
        {
            "exec-watchdog": _FakeExecution(
                updated_at=_utc_now() - timedelta(minutes=20),
                phase="queue",
            )
        }
    )
    artifacts_store = _FakeArtifactsStore(
        {
            "exec-watchdog": _FakeArtifact(
                metadata={"source": "browser_profile_scan_progress"},
                content={
                    "progress": {
                        "stage": "dialog_opened",
                        "semantic_progress_at": (_utc_now() - timedelta(minutes=2)).isoformat(),
                    }
                },
            )
        }
    )
    monkeypatch.setenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_SECONDS", "600")
    monkeypatch.delenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_PACKS", raising=False)

    requested = reaper._request_watchdog_abort_for_no_progress_tasks(
        store,
        watcher_id="test-watchdog",
        execution_store=execution_store,
        artifacts_store=artifacts_store,
    )

    assert requested == 0
    assert store.updated == []


def test_watchdog_uses_postgres_execution_store_by_default(monkeypatch):
    task = _build_running_browser_task()
    store = _FakeTasksStore([task])
    created = {"count": 0}

    class _PatchedExecutionStore(_FakeExecutionStore):
        def __init__(self):
            created["count"] += 1
            super().__init__(
                {
                    "exec-watchdog": _FakeExecution(
                        updated_at=_utc_now() - timedelta(minutes=20),
                        phase="queue",
                    )
                }
            )

    monkeypatch.setenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_SECONDS", "600")
    monkeypatch.delenv("LOCAL_CORE_RUNNER_NO_PROGRESS_WATCHDOG_PACKS", raising=False)
    monkeypatch.setattr(
        "backend.app.services.stores.postgres.remaining_stores.PostgresPlaybookExecutionsStore",
        _PatchedExecutionStore,
    )

    requested = reaper._request_watchdog_abort_for_no_progress_tasks(
        store,
        watcher_id="test-watchdog",
    )

    assert created["count"] == 1
    assert requested == 1
    assert len(store.updated) == 1
