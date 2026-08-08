from datetime import datetime, timezone

from backend.app.services.stores.tasks_store._crud_frontier_release import (
    TasksStoreFrontierReleaseMixin,
)


class _Result:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _Connection:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount
        self.sql = ""
        self.params = {}

    def execute(self, statement, params):
        self.sql = " ".join(str(statement).split())
        self.params = dict(params)
        return _Result(self.rowcount)


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Store(TasksStoreFrontierReleaseMixin):
    def __init__(self, rowcount: int):
        self.connection = _Connection(rowcount)
        self.refreshed = []

    def transaction(self):
        return _Transaction(self.connection)

    def _refresh_task_projection(self, connection, task_id):
        assert connection is self.connection
        self.refreshed.append(task_id)


def test_resource_wait_release_is_atomic_and_refreshes_projection():
    store = _Store(rowcount=1)
    released_at = datetime(2026, 8, 1, 15, 45, tzinfo=timezone.utc)

    assert store.try_release_resource_wait_task(
        "task-1",
        released_at=released_at,
    ) is True

    assert "execution_context::jsonb - 'resource_admission'" in store.connection.sql
    assert "- 'runner_resource_leases' - 'resume_after'" in store.connection.sql
    assert ")::json" in store.connection.sql
    assert "blocked_reason = 'resource_wait'" in store.connection.sql
    assert "next_eligible_at <= :released_at" in store.connection.sql
    assert store.connection.params == {
        "task_id": "task-1",
        "pending_status": "pending",
        "released_at": released_at,
    }
    assert store.refreshed == ["task-1"]


def test_resource_wait_release_noop_does_not_refresh_projection():
    store = _Store(rowcount=0)

    assert store.try_release_resource_wait_task(
        "task-raced",
        released_at=datetime.now(timezone.utc),
    ) is False
    assert store.refreshed == []
