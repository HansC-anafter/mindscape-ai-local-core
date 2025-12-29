"""PostgreSQL database configuration.

IMPORTANT: This module handles ONLY PostgreSQL configuration.
SQLite configuration is handled separately in StoreBase.

This module does NOT use DATABASE_URL (which is for SQLite).
It reads PostgreSQL configuration from POSTGRES_* environment variables.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_postgres_url() -> str:
    """Get PostgreSQL connection URL.

    This function reads PostgreSQL configuration from environment variables.
    It does NOT use DATABASE_URL (which is for SQLite).

    Returns:
        SQLAlchemy-compatible PostgreSQL URL

    Raises:
        ValueError: If PostgreSQL configuration is missing
    """
    # Option 1: Full URL from POSTGRES_URL (if set)
    postgres_url = os.getenv("POSTGRES_URL", "")
    if postgres_url.startswith("postgresql://") or postgres_url.startswith("postgres://"):
        logger.info("Using PostgreSQL from POSTGRES_URL")
        return postgres_url

    # Option 2: Individual environment variables
    host = os.getenv("POSTGRES_HOST")
    if not host:
        raise ValueError(
            "PostgreSQL configuration missing. "
            "Sonic Space and vector storage require PostgreSQL. "
            "Please set POSTGRES_HOST environment variable."
        )

    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "mindscape_vectors")
    user = os.getenv("POSTGRES_USER", "mindscape")
    password = os.getenv("POSTGRES_PASSWORD", "mindscape_password")

    url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    logger.info(f"Using PostgreSQL: {user}@{host}:{port}/{db}")
    return url


def get_engine_kwargs() -> dict:
    """Get engine-specific keyword arguments for PostgreSQL.

    Returns:
        Dictionary of keyword arguments for create_engine()
    """
    return {
        "echo": os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true",
        "pool_pre_ping": True,
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
    }

