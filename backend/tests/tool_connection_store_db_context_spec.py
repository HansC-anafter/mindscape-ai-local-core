from contextlib import contextmanager

from backend.app.services.tool_connection_store import ToolConnectionStore


class _FakeResult:
    def __init__(self):
        self.rowcount = 0

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((str(query), params or {}))
        return _FakeResult()


def _store_with_fake_connection():
    store = ToolConnectionStore.__new__(ToolConnectionStore)
    fake_connection = _FakeConnection()

    @contextmanager
    def fake_db_connection():
        yield fake_connection

    store._db_connection = fake_db_connection
    return store, fake_connection


def test_get_connections_by_profile_uses_db_context_not_public_lookup_method():
    store, fake_connection = _store_with_fake_connection()

    result = store.get_connections_by_profile("default-user")

    assert result == []
    assert fake_connection.calls
    assert fake_connection.calls[0][1]["profile_id"] == "default-user"


def test_get_connection_public_lookup_uses_db_context_without_recursing():
    store, fake_connection = _store_with_fake_connection()

    result = store.get_connection("conn-1", "default-user")

    assert result is None
    assert fake_connection.calls
    assert fake_connection.calls[0][1] == {
        "id": "conn-1",
        "profile_id": "default-user",
    }
