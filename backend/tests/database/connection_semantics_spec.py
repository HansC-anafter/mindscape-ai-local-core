import pytest

from backend.app.database import config as db_config


def _clear_db_url_caches() -> None:
    db_config._resolved_url_cache.clear()
    db_config._resolved_session_url_cache.clear()


def test_transaction_and_session_urls_are_separate(monkeypatch):
    _clear_db_url_caches()
    monkeypatch.setenv(
        "DATABASE_URL_CORE",
        "postgresql://mindscape:pw@pgbouncer:6432/mindscape_core",
    )
    monkeypatch.setenv(
        "DATABASE_URL_CORE_SESSION",
        "postgresql://mindscape:pw@postgres:5432/mindscape_core",
    )
    monkeypatch.setenv(
        "DATABASE_URL_VECTOR_SESSION",
        "postgresql://mindscape:pw@postgres:5432/mindscape_vectors",
    )
    monkeypatch.setenv(
        "PGBOUNCER_ADMIN_URL",
        "postgresql://mindscape:pw@pgbouncer:6432/pgbouncer",
    )

    assert "pgbouncer:6432/mindscape_core" in db_config.get_postgres_url_core()
    assert "postgres:5432/mindscape_core" in db_config.get_postgres_url_core_session()
    assert (
        "postgres:5432/mindscape_vectors"
        in db_config.get_postgres_url_vector_session()
    )
    assert "pgbouncer:6432/pgbouncer" in db_config.get_pgbouncer_admin_url()


def test_missing_session_url_does_not_fallback_to_transaction_url(monkeypatch):
    _clear_db_url_caches()
    monkeypatch.setenv(
        "DATABASE_URL_CORE",
        "postgresql://mindscape:pw@pgbouncer:6432/mindscape_core",
    )
    monkeypatch.delenv("DATABASE_URL_CORE_SESSION", raising=False)

    with pytest.raises(ValueError, match="DATABASE_URL_CORE_SESSION"):
        db_config.get_postgres_url_core_session()


def test_engine_kwargs_include_timeout_and_lifo(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "3")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "4")
    monkeypatch.setenv("DB_POOL_USE_LIFO", "false")

    kwargs = db_config.get_engine_kwargs()

    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 3
    assert kwargs["pool_timeout"] == 4
    assert kwargs["pool_use_lifo"] is False
