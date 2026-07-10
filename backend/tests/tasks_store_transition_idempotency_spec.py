from contextlib import contextmanager
from types import SimpleNamespace

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store import _crud_status, _crud_update
from backend.app.services.stores.tasks_store._crud_status import (
    TasksStoreStatusUpdateMixin,
)
from backend.app.services.stores.tasks_store._crud_update import TasksStoreUpdateMixin


class _Result:
    def __init__(self, row=None, *, rowcount=1):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self):
        self.dialect = SimpleNamespace(name="postgresql")
        self.sql = []

    def execute(self, statement, params):
        raw = str(statement)
        self.sql.append(raw)
        normalized = " ".join(raw.split())
        if normalized.startswith("SELECT status, pack_id"):
            return _Result(
                SimpleNamespace(
                    _mapping={
                        "status": "failed",
                        "pack_id": "ig",
                        "task_type": "playbook_execution",
                        "created_at": None,
                        "next_eligible_at": None,
                        "blocked_reason": None,
                        "frontier_state": "done",
                        "frontier_enqueued_at": None,
                    }
                )
            )
        if normalized.startswith("UPDATE tasks SET"):
            return _Result(rowcount=1)
        if normalized.startswith(
            "SELECT workspace_id, execution_id, pack_id, started_at, completed_at"
        ):
            return _Result(
                SimpleNamespace(
                    _mapping={
                        "workspace_id": "workspace-1",
                        "execution_id": "execution-1",
                        "pack_id": "ig",
                        "started_at": None,
                        "completed_at": None,
                    }
                )
            )
        raise AssertionError(f"unexpected SQL: {normalized}")


class _Store(TasksStoreUpdateMixin, TasksStoreStatusUpdateMixin):
    def __init__(self):
        self.conn = _Connection()
        self.projection_refreshes = []
        self.in_transaction = False

    @contextmanager
    def transaction(self):
        self.in_transaction = True
        try:
            yield self.conn
        finally:
            self.in_transaction = False

    def get_task(self, task_id):
        assert self.in_transaction is False
        return SimpleNamespace(id=task_id, status=TaskStatus.FAILED)

    def serialize_json(self, value):
        return value

    def _refresh_task_projection(self, conn, task_id):
        self.projection_refreshes.append(task_id)


def test_update_task_same_status_keeps_field_update_without_status_event(monkeypatch):
    published = []
    monkeypatch.setattr(_crud_update, "sync_meeting_command_from_task_safely", lambda task: None)
    monkeypatch.setattr(
        _crud_update,
        "_publish_terminal_event",
        lambda *args: published.append(args),
    )
    store = _Store()

    updated = store.update_task(
        "task-1",
        status=TaskStatus.FAILED,
        error="new diagnostic",
    )

    assert updated.id == "task-1"
    assert "FOR UPDATE" in store.conn.sql[0]
    assert any("error =" in sql for sql in store.conn.sql)
    assert store.projection_refreshes == ["task-1"]
    assert published == []


def test_update_task_status_same_status_refreshes_projection_without_event(monkeypatch):
    published = []
    monkeypatch.setattr(_crud_status, "sync_meeting_command_from_task_safely", lambda task: None)
    monkeypatch.setattr(
        _crud_status,
        "_publish_terminal_event",
        lambda *args: published.append(args),
    )
    store = _Store()

    updated = store.update_task_status(
        "task-2",
        TaskStatus.FAILED,
        error="same terminal state, newer diagnostic",
    )

    assert updated.id == "task-2"
    assert "FOR UPDATE" in store.conn.sql[0]
    assert store.projection_refreshes == ["task-2"]
    assert published == []
