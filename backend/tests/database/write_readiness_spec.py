from app.database import config as db_config
from backend.app.database.write_readiness import check_core_write_readiness


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _FakeConnection:
    def __init__(self, *, in_recovery=False, read_only="off"):
        self.in_recovery = in_recovery
        self.read_only = read_only

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement):
        sql = str(statement)
        if "pg_is_in_recovery" in sql:
            return _ScalarResult(self.in_recovery)
        if "transaction_read_only" in sql:
            return _ScalarResult(self.read_only)
        return _ScalarResult(1)


class _FakeEngine:
    def __init__(self, connection):
        self.connection = connection
        self.disposed = False

    def connect(self):
        return self.connection

    def dispose(self):
        self.disposed = True


def test_core_write_readiness_returns_ready(monkeypatch):
    db_config._resolved_url_cache.clear()
    monkeypatch.setenv("DATABASE_URL_CORE", "postgresql://user:pass@db/core")
    engine = _FakeEngine(_FakeConnection())

    readiness = check_core_write_readiness(
        operation="test",
        engine_factory=lambda _url: engine,
    )

    assert readiness.ready is True
    assert readiness.reason == "ready"
    assert readiness.retry_after_seconds == 0
    assert engine.disposed is True


def test_core_write_readiness_detects_recovery(monkeypatch):
    db_config._resolved_url_cache.clear()
    monkeypatch.setenv("DATABASE_URL_CORE", "postgresql://user:pass@db/core")

    readiness = check_core_write_readiness(
        operation="test",
        engine_factory=lambda _url: _FakeEngine(_FakeConnection(in_recovery=True)),
    )

    assert readiness.ready is False
    assert readiness.reason == "postgres_recovery_in_progress"
