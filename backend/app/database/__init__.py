"""PostgreSQL ORM layer for local-core.

This module provides SQLAlchemy ORM for PostgreSQL database.
Note: SQLite is handled separately via StoreBase for workspace state.

IMPORTANT: This module is PostgreSQL-only.
Sonic Space models require PostgreSQL-specific types (UUID, JSONB, ARRAY).

It also exposes a small async-compatible session shim because several
installed cloud capability packs expect ``app.database.get_async_session()``
and use async-style SQLAlchemy session methods.
"""

from .base import Base
from .engine import (
    engine_postgres,
    engine_postgres_core,
    engine_postgres_vector,
    SessionLocalPostgres,
    SessionLocalCore,
    SessionLocalVector,
)
from .session import get_db_postgres, get_db_core, get_db_vector


class _AsyncSessionCompat:
    """Async-shaped wrapper over the sync SQLAlchemy SessionLocalCore session."""

    def __init__(self, sync_session):
        self._sync_session = sync_session

    def add(self, *args, **kwargs):
        return self._sync_session.add(*args, **kwargs)

    async def execute(self, *args, **kwargs):
        return self._sync_session.execute(*args, **kwargs)

    async def flush(self):
        return self._sync_session.flush()

    async def refresh(self, *args, **kwargs):
        return self._sync_session.refresh(*args, **kwargs)

    async def commit(self):
        return self._sync_session.commit()

    async def rollback(self):
        return self._sync_session.rollback()

    async def close(self):
        return self._sync_session.close()

    def __getattr__(self, name):
        return getattr(self._sync_session, name)


class _AsyncSessionContext:
    """Async context manager that yields a compat-wrapped core DB session."""

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._session = None

    async def __aenter__(self):
        self._session = self._session_factory()
        return _AsyncSessionCompat(self._session)

    async def __aexit__(self, exc_type, exc, tb):
        if self._session is None:
            return False
        try:
            if exc_type is not None:
                self._session.rollback()
        finally:
            self._session.close()
        return False


def get_async_session():
    """Return an async-compatible context manager backed by SessionLocalCore."""
    if SessionLocalCore is None:
        raise RuntimeError("PostgreSQL core database not configured")
    return _AsyncSessionContext(SessionLocalCore)

# Alias for convenience (matches Sonic Space usage)
get_db = get_db_postgres

__all__ = [
    "Base",
    "engine_postgres",
    "engine_postgres_core",
    "engine_postgres_vector",
    "SessionLocalPostgres",
    "SessionLocalCore",
    "SessionLocalVector",
    "get_db_postgres",
    "get_db_core",
    "get_db_vector",
    "get_db",
    "get_async_session",
]
