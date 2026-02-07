"""PostgreSQL ORM layer for local-core.

This module provides SQLAlchemy ORM for PostgreSQL database.
Note: SQLite is handled separately via StoreBase for workspace state.

IMPORTANT: This module is PostgreSQL-only.
Sonic Space models require PostgreSQL-specific types (UUID, JSONB, ARRAY).
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
]
