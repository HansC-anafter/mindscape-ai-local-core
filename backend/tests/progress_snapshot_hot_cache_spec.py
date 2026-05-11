import pytest

from backend.app.services import mindscape_store
from backend.app.services.runner_resources import InMemoryTtlSnapshotStore


class _FakeMindscapeStoreForImport:
    db_path = ":memory:"


mindscape_store.MindscapeStore = _FakeMindscapeStoreForImport

from backend.app.routes.core.workspace import tasks as tasks_route


async def _inline_ui_read(func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.fixture(autouse=True)
def _reset_progress_snapshot_cache(monkeypatch):
    store = InMemoryTtlSnapshotStore(now_epoch=100.0)
    tasks_route._PROGRESS_SNAPSHOT_CACHE.clear()
    tasks_route._PROGRESS_SNAPSHOT_INFLIGHT.clear()
    monkeypatch.setattr(tasks_route, "_PROGRESS_SNAPSHOT_STORE", store)
    monkeypatch.setattr(tasks_route, "run_ui_read", _inline_ui_read)
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
        tasks_route,
        "_load_execution_progress_snapshot_payload",
        _loader,
    )

    first = await tasks_route.get_execution_progress_snapshot("ws-1", "exec-1")
    tasks_route._PROGRESS_SNAPSHOT_CACHE.clear()
    second = await tasks_route.get_execution_progress_snapshot("ws-1", "exec-1")

    assert first == second
    assert calls["count"] == 1
    assert second["progress"] == {"step": 1}


@pytest.mark.asyncio
async def test_progress_snapshot_hot_cache_expires(monkeypatch):
    store = tasks_route._PROGRESS_SNAPSHOT_STORE
    calls = {"count": 0}

    def _loader(_workspace_id, _execution_id):
        calls["count"] += 1
        return {"task_status": "running", "progress": {"step": calls["count"]}}

    monkeypatch.setattr(
        tasks_route,
        "_load_execution_progress_snapshot_payload",
        _loader,
    )

    first = await tasks_route.get_execution_progress_snapshot("ws-1", "exec-1")
    tasks_route._PROGRESS_SNAPSHOT_CACHE.clear()
    store.advance(5)
    second = await tasks_route.get_execution_progress_snapshot("ws-1", "exec-1")

    assert first["progress"] == {"step": 1}
    assert second["progress"] == {"step": 2}
    assert calls["count"] == 2
