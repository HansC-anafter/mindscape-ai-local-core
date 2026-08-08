from __future__ import annotations

import asyncio
from pathlib import Path

from backend.app.database import vector_connection
from backend.app.database.connection_factory import ConnectionFactory


class _FakeBackoff:
    def __init__(self) -> None:
        self.labels: list[str] = []
        self.failures: list[Exception] = []

    def wait_if_active(self, *, label: str) -> None:
        self.labels.append(label)

    def note_failure(self, exc: Exception) -> bool:
        self.failures.append(exc)
        return True


def test_connection_factory_raw_connection_uses_role_engine_and_backoff() -> None:
    ConnectionFactory.reset()
    factory = ConnectionFactory()
    raw_connection = object()

    class FakeEngine:
        def raw_connection(self):
            return raw_connection

    backoff = _FakeBackoff()
    factory._recovery_backoffs["vector"] = backoff
    factory._get_postgres_engine = lambda role: FakeEngine()  # type: ignore[method-assign]

    assert factory.get_raw_connection("vector") is raw_connection
    assert backoff.labels == ["PostgreSQL vector DBAPI connection"]
    ConnectionFactory.reset()


def test_default_vector_connection_delegates_to_bounded_role_engine(monkeypatch) -> None:
    expected = object()

    class FakeFactory:
        def get_raw_connection(self, *, role: str):
            assert role == "vector"
            return expected

    monkeypatch.setattr(vector_connection, "ConnectionFactory", FakeFactory)

    assert vector_connection.get_vector_dbapi_connection() is expected
    assert vector_connection.get_vector_dbapi_connection({}) is expected


def test_custom_vector_connection_is_identified_and_timeout_bounded(monkeypatch) -> None:
    captured = {}
    expected = object()

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return expected

    import psycopg2

    monkeypatch.setenv("DB_APPLICATION_NAME", "local-core-backend")
    monkeypatch.setattr(psycopg2, "connect", fake_connect)

    result = vector_connection.get_vector_dbapi_connection(
        {"host": "custom-db", "database": "vectors", "connect_timeout": 2}
    )

    assert result is expected
    assert captured["application_name"] == "local-core-backend:vector"
    assert captured["connect_timeout"] == 2


def test_default_vector_runtime_callers_have_one_transport_owner() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    caller_paths = [
        "app/routes/core/vector_db.py",
        "app/routes/core/system_settings/llm/chat_embedding_core/migration_analysis.py",
        "app/services/vector_search.py",
        "app/services/tool_embedding_service.py",
        "app/services/embedding_migration_service.py",
        "app/services/playbook_indexer.py",
        "app/services/event_embedding_generator_core/storage.py",
        "app/services/playbook_webhook.py",
    ]

    for relative_path in caller_paths:
        source = (backend_root / relative_path).read_text(encoding="utf-8")
        assert "psycopg2.connect" not in source, relative_path
        assert "get_vector_dbapi_connection" in source, relative_path

    transport_source = (
        backend_root / "app/database/vector_connection.py"
    ).read_text(encoding="utf-8")
    assert transport_source.count("psycopg2.connect") == 1


def test_playbook_seed_returns_pooled_connection_after_commit(monkeypatch) -> None:
    from backend.app.services import playbook_webhook

    class FakeCursor:
        def __init__(self) -> None:
            self.params = None
            self.closed = False

        def execute(self, query, params) -> None:
            assert "INSERT INTO memory_embeddings" in query
            self.params = params

        def close(self) -> None:
            self.closed = True

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_value = FakeCursor()
            self.committed = False
            self.closed = False

        def cursor(self):
            return self.cursor_value

        def commit(self) -> None:
            self.committed = True

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()
    monkeypatch.setattr(
        playbook_webhook,
        "get_vector_dbapi_connection",
        lambda: connection,
    )
    handler = object.__new__(playbook_webhook.PlaybookWebhookHandler)

    asyncio.run(
        handler._create_seed(
            user_id="user-1",
            source_type="playbook",
            content="result",
            confidence=0.8,
            source_id="source-1",
        )
    )

    assert connection.cursor_value.params == (
        "user-1",
        "playbook",
        "result",
        "{}",
        "source-1",
        0.8,
        1.0,
    )
    assert connection.committed is True
    assert connection.cursor_value.closed is True
    assert connection.closed is True
