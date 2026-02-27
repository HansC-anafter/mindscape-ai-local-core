import os
import logging
from typing import Any, Dict
from sqlalchemy.engine import Engine
from sqlalchemy import create_engine

from app.database.config import get_postgres_url_core, get_postgres_url_vector

logger = logging.getLogger(__name__)


class ConnectionFactory:
    """
    Factory for creating/retrieving database connections.
    PostgreSQL is the only supported backend as of 2026-02-23.
    """

    _instance = None
    _postgres_engines: Dict[str, Engine] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConnectionFactory, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.force_postgres = (
            os.getenv("MINDSCAPE_FORCE_POSTGRES", "true").lower() == "true"
        )
        self.core_url = get_postgres_url_core(required=False)
        self.vector_url = get_postgres_url_vector(required=False)

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
        raise RuntimeError(
            "PostgreSQL URL not configured. "
            "Set DATABASE_URL_CORE and DATABASE_URL_VECTOR environment variables."
        )

    def get_db_type(self, role: str = "core") -> str:
        """Return the current database type. Always 'postgres'."""
        return "postgres"

    def get_connection(self, role: str = "core") -> Any:
        """
        Get a raw SQLAlchemy connection to PostgreSQL.

        Returns a SQLAlchemy Connection object.
        """
        return self._get_postgres_engine(role).connect()

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
