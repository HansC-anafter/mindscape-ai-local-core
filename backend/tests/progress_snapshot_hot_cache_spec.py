import pytest
from types import SimpleNamespace
from fastapi import HTTPException

from backend.app.services import mindscape_store
from backend.app.services.runner_resources import InMemoryTtlSnapshotStore


class _FakeMindscapeStoreForImport:
    db_path = ":memory:"


mindscape_store.MindscapeStore = _FakeMindscapeStoreForImport

from backend.app.routes.core.workspace.tasks_core import (
    progress_snapshot as progress_snapshot_core,
)
from backend.app.routes.core.workspace.tasks_core import (
    progress_snapshot_routes as progress_snapshot_route,
)


async def _inline_ui_read(func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.fixture(autouse=True)
def _reset_progress_snapshot_cache(monkeypatch):
    store = InMemoryTtlSnapshotStore(now_epoch=100.0)
    progress_snapshot_route._PROGRESS_SNAPSHOT_CACHE.clear()
    progress_snapshot_route._PROGRESS_SNAPSHOT_LAST_KNOWN.clear()
    progress_snapshot_route._PROGRESS_SNAPSHOT_INFLIGHT.clear()
    monkeypatch.setattr(progress_snapshot_route, "_PROGRESS_SNAPSHOT_STORE", store)
    monkeypatch.setattr(progress_snapshot_route, "run_ui_read", _inline_ui_read)
    return store


@pytest.mark.asyncio
async def test_progress_snapshot_uses_hot_cache_after_process_cache_miss(monkeypatch):
    calls = {"count": 0}

    def _loader(workspace_id, execution_id):
        calls["count"] += 1
        return {
            "workspace_id": workspace_id,
            "execution_id": execution_id,
            "task_status": "running",
            "progress": {"step": calls["count"]},
        }

    monkeypatch.setattr(
        progress_snapshot_route,
        "_load_execution_progress_snapshot_payload",
        _loader,
    )

    first = await progress_snapshot_route.get_execution_progress_snapshot("ws-1", "exec-1")
    progress_snapshot_route._PROGRESS_SNAPSHOT_CACHE.clear()
    second = await progress_snapshot_route.get_execution_progress_snapshot("ws-1", "exec-1")

    assert first == second
    assert calls["count"] == 1
    assert second["progress"] == {"step": 1}


@pytest.mark.asyncio
async def test_progress_snapshot_hot_cache_expires(monkeypatch):
    store = progress_snapshot_route._PROGRESS_SNAPSHOT_STORE
    calls = {"count": 0}

    def _loader(_workspace_id, _execution_id):
        calls["count"] += 1
        return {"task_status": "running", "progress": {"step": calls["count"]}}

    monkeypatch.setattr(
        progress_snapshot_route,
        "_load_execution_progress_snapshot_payload",
        _loader,
    )

    first = await progress_snapshot_route.get_execution_progress_snapshot("ws-1", "exec-1")
    progress_snapshot_route._PROGRESS_SNAPSHOT_CACHE.clear()
    store.advance(5)
    second = await progress_snapshot_route.get_execution_progress_snapshot("ws-1", "exec-1")

    assert first["progress"] == {"step": 1}
    assert second["progress"] == {"step": 2}
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_progress_snapshot_returns_explicit_stale_last_known_on_db_failure(
    monkeypatch,
):
    store = progress_snapshot_route._PROGRESS_SNAPSHOT_STORE
    monkeypatch.setattr(
        progress_snapshot_route,
        "record_database_failure",
        lambda _code: SimpleNamespace(incident_id="incident-1"),
    )
    monkeypatch.setattr(
        progress_snapshot_route,
        "_load_execution_progress_snapshot_payload",
        lambda workspace_id, execution_id: {
            "workspace_id": workspace_id,
            "execution_id": execution_id,
            "task_status": "running",
            "progress": {"step": 1},
        },
    )
    fresh = await progress_snapshot_route.get_execution_progress_snapshot(
        "ws-1", "exec-1"
    )
    assert fresh["stale"] is False

    progress_snapshot_route._PROGRESS_SNAPSHOT_CACHE.clear()
    store.advance(5)
    monkeypatch.setattr(
        progress_snapshot_route,
        "_load_execution_progress_snapshot_payload",
        lambda *_args: (_ for _ in ()).throw(
            RuntimeError("server closed the connection unexpectedly")
        ),
    )

    degraded = await progress_snapshot_route.get_execution_progress_snapshot(
        "ws-1", "exec-1"
    )

    assert degraded["stale"] is True
    assert degraded["degraded_reason"] == "postgres_unavailable"
    assert degraded["progress"] == {"step": 1}


@pytest.mark.asyncio
async def test_progress_snapshot_returns_stable_503_without_raw_sql(monkeypatch):
    monkeypatch.setattr(
        progress_snapshot_route,
        "record_database_failure",
        lambda _code: SimpleNamespace(incident_id="incident-2"),
    )
    monkeypatch.setattr(
        progress_snapshot_route,
        "_load_execution_progress_snapshot_payload",
        lambda *_args: (_ for _ in ()).throw(
            RuntimeError(
                "server closed the connection unexpectedly [SQL: SELECT * FROM tasks]"
            )
        ),
    )

    with pytest.raises(HTTPException) as raised:
        await progress_snapshot_route.get_execution_progress_snapshot(
            "ws-1", "exec-1"
        )

    assert raised.value.status_code == 503
    assert raised.value.headers == {"Retry-After": "30"}
    assert raised.value.detail == {
        "error_code": "runtime_database_unavailable",
        "retry_after_seconds": 30,
        "incident_id": "incident-2",
    }
    assert "SELECT" not in str(raised.value.detail)


@pytest.mark.asyncio
async def test_progress_snapshot_does_not_mislabel_query_defects_as_db_outages(
    monkeypatch,
):
    monkeypatch.setattr(
        progress_snapshot_route,
        "_load_execution_progress_snapshot_payload",
        lambda *_args: (_ for _ in ()).throw(
            RuntimeError(
                "operator does not exist: text -> unknown [SQL: SELECT content -> 'progress']"
            )
        ),
    )

    with pytest.raises(HTTPException) as raised:
        await progress_snapshot_route.get_execution_progress_snapshot(
            "ws-1", "exec-1"
        )

    assert raised.value.status_code == 500
    assert raised.value.detail == {"error_code": "progress_snapshot_query_failed"}
    assert "SELECT" not in str(raised.value.detail)


def test_progress_snapshot_payload_overlays_live_task_heartbeat(monkeypatch):
    class _FakeResult:
        def fetchall(self):
            return [
                SimpleNamespace(
                    id="artifact-1",
                    updated_at=None,
                    created_at=None,
                    metadata='{"artifact_kind":"ig_following_progress"}',
                    content=(
                        '{"progress":{"stage":"scrolling","saved_dedup_targets":12},'
                        '"metadata":{"target_username":"demo"}}'
                    ),
                )
            ]

    class _FakeConnection:
        def execute(self, query, params):
            query_text = str(query)
            assert "content ->" not in query_text
            assert "content" in query_text
            return _FakeResult()

    class _FakeConnectionContext:
        def __enter__(self):
            return _FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    task = SimpleNamespace(
        id="task-1",
        workspace_id="ws-1",
        execution_id="exec-1",
        status="running",
        execution_context={
            "heartbeat_at": "2026-05-29T09:09:56.822251+00:00",
            "runner_id": "runner-db",
            "inputs": {},
        },
        heartbeat_at="2026-05-29T09:09:56.822251+00:00",
        runner_id="runner-db",
        queue_shard="browser_local",
        blocked_reason=None,
        blocked_payload=None,
        frontier_state=None,
        next_eligible_at=None,
    )

    class _FakeTasksStore:
        def get_progress_task_control(self, execution_id):
            assert execution_id == "exec-1"
            return task

        def get_connection(self):
            return _FakeConnectionContext()

    class _FakeQueueCache:
        def refresh_if_stale(self, tasks_store):
            return None

        def get_position(self, tasks_store, task_obj):
            return None

        def get_total(self, queue_shard):
            return 1

    class _FakeRunnerLiveStateStore:
        def get_task_heartbeat(self, task_id):
            assert task_id == "task-1"
            return {
                "heartbeat_at": "2026-05-29T10:18:41.490662+00:00",
                "runner_id": "runner-live",
            }

    monkeypatch.setattr(progress_snapshot_core, "TasksStore", _FakeTasksStore)
    monkeypatch.setattr(
        progress_snapshot_core,
        "RunnerLiveStateStore",
        _FakeRunnerLiveStateStore,
    )
    monkeypatch.setattr(progress_snapshot_core, "_QUEUE_CACHE", _FakeQueueCache())

    payload = progress_snapshot_core.load_execution_progress_snapshot_payload(
        "ws-1",
        "exec-1",
    )

    assert payload["execution_context"]["heartbeat_at"] == (
        "2026-05-29T10:18:41.490662+00:00"
    )
    assert payload["execution_context"]["runner_id"] == "runner-live"
    assert payload["progress"] == {
        "stage": "scrolling",
        "saved_dedup_targets": 12,
    }
    assert payload["content_metadata"] == {"target_username": "demo"}
