from types import SimpleNamespace

from backend.app.routes.core import execution_query_helpers
from backend.app.services.runner_resources import SyncRedisTtlSnapshotStore


class _FakeCache:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def set(self, key, value, ttl):
        self.values[key] = value
        self.ttls[key] = ttl
        return True

    def get(self, key):
        return self.values.get(key)


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self, store):
        self._store = store

    def execute(self, query, params):
        self._store.execute_count += 1
        self._store.last_query = str(query)
        self._store.last_params = dict(params)
        return _FakeResult(self._store.row)


class _FakeConnectionContext:
    def __init__(self, store):
        self._store = store

    def __enter__(self):
        return _FakeConnection(self._store)

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeTasksStore:
    def __init__(self, row, heartbeats=None):
        self.row = row
        self.heartbeats = list(heartbeats or [])
        self.execute_count = 0
        self.heartbeat_count = 0
        self.last_query = None
        self.last_params = None

    def get_connection(self):
        return _FakeConnectionContext(self)

    def list_runner_heartbeats(self, *, max_age_seconds, limit):
        self.heartbeat_count += 1
        assert max_age_seconds == 300
        assert limit == 100
        return self.heartbeats


def test_execution_status_payload_uses_hot_cache_after_first_db_read(monkeypatch):
    cache = _FakeCache()
    monkeypatch.setattr(
        execution_query_helpers,
        "_STATUS_SNAPSHOT_STORE",
        SyncRedisTtlSnapshotStore(cache),
    )

    row = SimpleNamespace(
        execution_id="exec-1",
        status="running",
        execution_context={
            "status": "running",
            "runner_id": "runner-a",
            "result": {"heavy": True},
            "workflow_result": {"heavy": True},
            "step_outputs": {"heavy": True},
            "outputs": {"heavy": True},
            "conversation_state": {"heavy": True},
        },
    )
    store = _FakeTasksStore(
        row,
        heartbeats=[
            {
                "runner_id": "runner-a",
                "heartbeat_at": "2026-05-12T00:00:00Z",
                "resource_snapshot": {"browser_contexts": {"available": 0}},
            }
        ],
    )

    first = execution_query_helpers.load_execution_status_payload(store, "exec-1")
    second = execution_query_helpers.load_execution_status_payload(store, "exec-1")

    assert first == second
    assert store.execute_count == 1
    assert store.heartbeat_count == 1
    assert first["task_status"] == "running"
    assert first["execution_context"]["runner_resource_snapshot"] == {
        "browser_contexts": {"available": 0}
    }
    assert first["execution_context"]["runner_heartbeat_at"] == "2026-05-12T00:00:00Z"
    for heavy_key in (
        "result",
        "workflow_result",
        "step_outputs",
        "outputs",
        "conversation_state",
    ):
        assert heavy_key not in first["execution_context"]


def test_execution_status_payload_falls_back_when_hot_cache_errors(monkeypatch):
    class _BrokenSnapshotStore:
        def get(self, key):
            raise RuntimeError("cache unavailable")

        def set(self, key, value, ttl_seconds):
            raise RuntimeError("cache unavailable")

    monkeypatch.setattr(
        execution_query_helpers,
        "_STATUS_SNAPSHOT_STORE",
        _BrokenSnapshotStore(),
    )

    row = SimpleNamespace(
        execution_id="exec-1",
        status="succeeded",
        execution_context={"status": "succeeded", "result": {"heavy": True}},
    )
    store = _FakeTasksStore(row)

    payload = execution_query_helpers.load_execution_status_payload(store, "exec-1")

    assert payload["task_status"] == "succeeded"
    assert payload["execution_context"] == {"status": "succeeded"}
    assert store.execute_count == 1
