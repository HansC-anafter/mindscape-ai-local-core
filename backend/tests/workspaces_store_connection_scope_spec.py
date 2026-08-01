from contextlib import contextmanager
from types import SimpleNamespace

from backend.app.services.stores.postgres.workspaces_store import (
    PostgresWorkspacesStore,
)


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, params):
        return _Result(self.rows)


def test_workspace_point_reads_convert_buffered_row_after_connection_close():
    state = {"open": False}
    row = SimpleNamespace(id="workspace-a")
    store = object.__new__(PostgresWorkspacesStore)

    @contextmanager
    def _connection():
        state["open"] = True
        try:
            yield _Connection([row])
        finally:
            state["open"] = False

    converted = []

    def _convert(value):
        assert state["open"] is False
        converted.append(("full", value.id))
        return value.id

    def _convert_summary(value):
        assert state["open"] is False
        converted.append(("summary", value.id))
        return {"id": value.id}

    store.get_connection = _connection
    store._row_to_workspace = _convert
    store._row_to_workspace_summary = _convert_summary

    assert store.get_workspace_sync("workspace-a") == "workspace-a"
    assert store.get_workspace_summary_sync("workspace-a") == {"id": "workspace-a"}
    assert converted == [
        ("full", "workspace-a"),
        ("summary", "workspace-a"),
    ]


def test_workspace_lists_convert_buffered_rows_after_connection_close():
    state = {"open": False}
    rows = [SimpleNamespace(id="workspace-a"), SimpleNamespace(id="workspace-b")]
    store = object.__new__(PostgresWorkspacesStore)

    @contextmanager
    def _connection():
        state["open"] = True
        try:
            yield _Connection(rows)
        finally:
            state["open"] = False

    converted = []

    def _convert(row):
        assert state["open"] is False
        converted.append(("full", row.id))
        return row.id

    def _convert_summary(row):
        assert state["open"] is False
        converted.append(("summary", row.id))
        return {"id": row.id}

    store.get_connection = _connection
    store._row_to_workspace = _convert
    store._row_to_workspace_summary = _convert_summary

    assert store.list_workspaces("default-user") == ["workspace-a", "workspace-b"]
    assert store.list_workspace_summaries("default-user") == [
        {"id": "workspace-a"},
        {"id": "workspace-b"},
    ]
    assert store.list_discoverable_workspaces() == ["workspace-a", "workspace-b"]
    assert converted == [
        ("full", "workspace-a"),
        ("full", "workspace-b"),
        ("summary", "workspace-a"),
        ("summary", "workspace-b"),
        ("full", "workspace-a"),
        ("full", "workspace-b"),
    ]
