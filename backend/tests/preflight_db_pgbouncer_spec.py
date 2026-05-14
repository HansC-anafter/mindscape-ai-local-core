import sys
import types

from backend.scripts import preflight_db


class _FakeCursor:
    def execute(self, *_args, **_kwargs):
        return None

    def close(self):
        return None


class _FakeConnection:
    def cursor(self):
        return _FakeCursor()

    def set_isolation_level(self, _level):
        return None

    def close(self):
        return None


def test_preflight_db_does_not_connect_to_postgres_database_via_pgbouncer(
    monkeypatch,
):
    dbnames = []

    def _connect(**kwargs):
        dbnames.append(kwargs["dbname"])
        return _FakeConnection()

    fake_psycopg2 = types.ModuleType("psycopg2")
    fake_psycopg2.connect = _connect
    fake_extensions = types.ModuleType("psycopg2.extensions")
    fake_extensions.ISOLATION_LEVEL_AUTOCOMMIT = object()

    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extensions", fake_extensions)
    monkeypatch.setenv("POSTGRES_CORE_HOST", "pgbouncer")
    monkeypatch.setenv("POSTGRES_CORE_PORT", "6432")
    monkeypatch.setenv("POSTGRES_CORE_DB", "mindscape_core")
    monkeypatch.setenv("POSTGRES_VECTOR_DB", "mindscape_vectors")

    assert preflight_db.ensure_databases() is True
    assert "postgres" not in dbnames
    assert dbnames == ["mindscape_core", "mindscape_vectors", "mindscape_vectors"]
