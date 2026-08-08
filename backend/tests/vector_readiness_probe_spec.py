from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from backend.app.services import vector_readiness_probe
from backend.app.services.vector_readiness_probe import VectorReadinessProbe


class _FakeCursor:
    def __init__(self, row=(True, "0.8.0", 1536)) -> None:
        self.row = row
        self.execute_count = 0
        self.closed = False

    def execute(self, query: str) -> None:
        assert "pg_extension" in query
        self.execute_count += 1

    def fetchone(self):
        return self.row

    def close(self) -> None:
        self.closed = True


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor_value = cursor
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def close(self) -> None:
        self.closed = True


def test_cold_probe_coalesces_32_threads_to_one_connection_and_query() -> None:
    entered = threading.Event()
    release = threading.Event()
    call_lock = threading.Lock()
    calls = 0
    cursor = _FakeCursor(row=(True, "0.8.0"))
    connection = _FakeConnection(cursor)

    def connection_factory():
        nonlocal calls
        with call_lock:
            calls += 1
        entered.set()
        assert release.wait(timeout=2)
        return connection

    probe = VectorReadinessProbe(connection_factory=connection_factory)
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = [executor.submit(probe.check) for _ in range(32)]
        assert entered.wait(timeout=1)
        time.sleep(0.05)
        release.set()
        results = [future.result(timeout=2) for future in futures]

    assert calls == 1
    assert cursor.execute_count == 1
    assert connection.closed is True
    assert all(result.connected for result in results)
    assert len({id(result) for result in results}) == 1


def test_probe_cache_and_force_refresh_have_exact_connection_budget() -> None:
    calls = 0

    def connection_factory():
        nonlocal calls
        calls += 1
        return _FakeConnection(_FakeCursor(row=(True, "0.8.0")))

    probe = VectorReadinessProbe(connection_factory=connection_factory)

    assert probe.check().connected is True
    assert probe.check().connected is True
    assert probe.check(force=True).connected is True
    assert calls == 2


def test_probe_failure_is_cached_without_retry_and_releases_waiters() -> None:
    calls = 0

    def connection_factory():
        nonlocal calls
        calls += 1
        raise RuntimeError("vector unavailable")

    probe = VectorReadinessProbe(connection_factory=connection_factory)
    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(lambda _: probe.check(), range(32)))

    assert calls == 1
    assert all(result.connected is False for result in results)
    assert all(result.error == "vector unavailable" for result in results)


def test_explicit_connection_test_uses_one_connection_and_one_query(monkeypatch) -> None:
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor)
    calls = 0

    def fake_connection_factory(config=None):
        nonlocal calls
        calls += 1
        assert config == {"host": "custom"}
        return connection

    monkeypatch.setattr(
        vector_readiness_probe,
        "get_vector_dbapi_connection",
        fake_connection_factory,
    )

    result = vector_readiness_probe.run_vector_connection_test({"host": "custom"})

    assert result["connected"] is True
    assert result["pgvector_version"] == "0.8.0"
    assert result["dimension"] == 1536
    assert calls == 1
    assert cursor.execute_count == 1
    assert connection.closed is True
