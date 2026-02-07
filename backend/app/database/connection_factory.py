import os
import logging
from typing import Optional, Union, Any, Dict
from sqlalchemy.engine import Engine
from sqlalchemy import create_engine
import sqlite3

from app.database.config import get_postgres_url_core, get_postgres_url_vector

logger = logging.getLogger(__name__)


class ConnectionFactory:
    """
    Factory for creating/retrieving database connections.
    Supports both SQLite (legacy) and PostgreSQL (target) modes based on configuration.
    This is the core of the hybrid adapter layer for the migration.
    """

    _instance = None
    _postgres_engines: Dict[str, Engine] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConnectionFactory, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Determine strict mode from env (default to False to allow fallback)
        self.force_postgres = (
            os.getenv("MINDSCAPE_FORCE_POSTGRES", "false").lower() == "true"
        )
        self.core_url = get_postgres_url_core(required=False)
        self.vector_url = get_postgres_url_vector(required=False)
        self.legacy_url = os.getenv("DATABASE_URL", "")

    def _get_role_url(self, role: str) -> str:
        if role == "vector":
            if self.vector_url:
                return self.vector_url
            if self.core_url:
                logger.warning(
                    "Vector DB URL not configured, falling back to core PostgreSQL URL"
                )
                return self.core_url
        if self.core_url:
            return self.core_url
        return self.legacy_url

    def get_db_type(self, role: str = "core") -> str:
        """Return the current database type: 'sqlite' or 'postgres'"""
        db_url = self._get_role_url(role)
        if db_url.startswith("postgres"):
            return "postgres"
        return "sqlite"

    def get_connection(self, role: str = "core") -> Union[sqlite3.Connection, Any]:
        """
        Get a raw connection object.

        IMPORTANT: As of 2026-01-27, PostgreSQL is the primary database.
        SQLite fallback is deprecated and will be removed in a future release.

        For Postgres: Returns a SQLAlchemy Connection
        For SQLite (deprecated): Returns a sqlite3.Connection
        """
        db_type = self.get_db_type(role)

        if db_type == "sqlite":
            # SQLite is now deprecated - always raise error unless explicitly allowed
            if self.force_postgres:
                raise RuntimeError(
                    "PostgreSQL is enforced but DATABASE_URL is pointing to SQLite! "
                    "Please configure DATABASE_URL_CORE and DATABASE_URL_VECTOR "
                    "to point to PostgreSQL."
                )

            # Emit deprecation warning for SQLite usage
            import warnings

            warnings.warn(
                "SQLite database connection is deprecated. "
                "Please migrate to PostgreSQL by setting DATABASE_URL_CORE/DATABASE_URL_VECTOR.",
                DeprecationWarning,
                stacklevel=2,
            )

            # Legacy SQLite behavior (mirrors StoreBase.get_connection)
            db_path = self._get_role_url(role).replace("sqlite:///", "")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn

        elif db_type == "postgres":
            # PostgreSQL mode (primary)
            return self._get_postgres_engine(role).connect()

        raise ValueError(f"Unsupported database type: {db_type}")

    def _get_postgres_engine(self, role: str) -> Engine:
        if role in self._postgres_engines:
            return self._postgres_engines[role]

        url = self._get_role_url(role)
        if not url.startswith("postgres"):
            raise RuntimeError(f"PostgreSQL URL not configured for role: {role}")

        safe_url = url
        if "@" in url:
            parts = url.split("@")
            safe_url = "..." + parts[-1]

        logger.info(f"Initializing PostgreSQL engine for {role}: {safe_url}")
        engine = create_engine(url, pool_pre_ping=True)
        self._postgres_engines[role] = engine
        return engine

    @classmethod
    def reset(cls):
        """Reset singleton state (useful for testing)"""
        cls._instance = None
        cls._postgres_engines = {}


# Global accessor
def get_db_connection(role: str = "core"):
    return ConnectionFactory().get_connection(role=role)
