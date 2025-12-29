"""PostgreSQL ORM layer for local-core.

This module provides SQLAlchemy ORM for PostgreSQL database.
Note: SQLite is handled separately via StoreBase for workspace state.

IMPORTANT: This module is PostgreSQL-only.
Sonic Space models require PostgreSQL-specific types (UUID, JSONB, ARRAY).
"""

from .base import Base
from .engine import engine_postgres, SessionLocalPostgres
from .session import get_db_postgres

# Alias for convenience (matches Sonic Space usage)
get_db = get_db_postgres

__all__ = [
    "Base",
    "engine_postgres",
    "SessionLocalPostgres",
    "get_db_postgres",
    "get_db",
]

