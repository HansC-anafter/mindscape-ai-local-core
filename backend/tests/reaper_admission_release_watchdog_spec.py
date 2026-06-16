from datetime import timedelta

from backend.app.models.workspace import TaskStatus, _utc_now
from backend.app.runner import reaper
from backend.tests.reaper_admission_release_support import (
    _FakeArtifact,
    _FakeArtifactsStore,
    _FakeExecution,
    _FakeExecutionStore,
    _FakeLiveStateStore,
    _FakeTasksStore,
    _build_running_browser_task,
    _build_stale_queued_running_task_without_owner,
)


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


def test_skips_reaping_running_task_with_fresh_live_state(monkeypatch):
    task = _build_running_browser_task(heartbeat_age_seconds=3600)
    store = _FakeTasksStore([task])
    live_state = _FakeLiveStateStore(
        {
            task.id: {
                "task_id": task.id,
                "runner_id": "runner-1",
                "heartbeat_at": _utc_now().isoformat(),
            }
        }
    )
    monkeypatch.setenv("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", "180")

    reaper._reap_stale_running_tasks(
        store,
        "runner-new",
        redis_queue=None,
        live_state_store=live_state,
    )

    assert store.updated == []


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
                        "semantic_progress_at": (
                            _utc_now() - timedelta(minutes=2)
                        ).isoformat(),
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
