from sqlalchemy.pool import NullPool

from backend.app.database import engine_factory


def test_transaction_engine_uses_queue_pool_kwargs(monkeypatch):
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(engine_factory, "create_engine", fake_create_engine)
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "1")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "5")

    engine_factory.create_transaction_engine(
        "postgresql://u:p@pgbouncer:6432/core",
        "local-core-test",
    )

    assert captured["url"] == "postgresql://u:p@pgbouncer:6432/core"
    assert captured["kwargs"]["pool_size"] == 2
    assert captured["kwargs"]["max_overflow"] == 1
    assert captured["kwargs"]["pool_timeout"] == 5
    assert captured["kwargs"]["pool_use_lifo"] is True
    assert captured["kwargs"]["connect_args"]["application_name"] == "local-core-test"


def test_transient_and_session_engines_use_nullpool(monkeypatch):
    calls = []

    def fake_create_engine(url, **kwargs):
        calls.append((url, kwargs))
        return object()

    monkeypatch.setattr(engine_factory, "create_engine", fake_create_engine)

    engine_factory.create_transient_transaction_engine(
        "postgresql://u:p@pgbouncer:6432/core",
        "transient-test",
    )
    engine_factory.create_session_semantics_engine(
        "postgresql://u:p@postgres:5432/core",
        "session-test",
    )

    assert calls[0][1]["poolclass"] is NullPool
    assert calls[0][1]["connect_args"]["application_name"] == "transient-test"
    assert calls[1][1]["poolclass"] is NullPool
    assert calls[1][1]["connect_args"]["application_name"] == "session-test"
