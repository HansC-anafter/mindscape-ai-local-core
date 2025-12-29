"""PostgreSQL database session management for FastAPI dependency injection.

This module provides get_db() function for FastAPI dependency injection.
It is specifically for PostgreSQL models that require PostgreSQL-specific types.

For SQLite workspace state, use StoreBase instead.
"""

import logging
from typing import Generator
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .engine import SessionLocalPostgres

logger = logging.getLogger(__name__)


def get_db_postgres() -> Generator[Session, None, None]:
    """Get PostgreSQL database session for FastAPI dependency injection.

    This function is specifically for PostgreSQL models that require
    PostgreSQL-specific types (UUID, JSONB, ARRAY, etc.).

    For SQLite workspace state, use StoreBase instead.

    Yields:
        SQLAlchemy Session object (PostgreSQL)

    Raises:
        HTTPException: If PostgreSQL connection is not available

    Example:
        ```python
        from fastapi import Depends
        from app.database import get_db
        from sqlalchemy.orm import Session

        @router.get("/items")
        def get_items(db: Session = Depends(get_db)):
            items = db.query(Item).all()
            return items
        ```
    """
    if SessionLocalPostgres is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "PostgreSQL database not configured. "
                "Sonic Space requires PostgreSQL with pgvector extension. "
                "Please configure POSTGRES_HOST environment variable."
            )
        )

    db = SessionLocalPostgres()
    try:
        yield db
    except Exception as e:
        logger.error(f"PostgreSQL session error: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail=f"PostgreSQL database error: {str(e)}"
        )
    finally:
        db.close()


# Alias for convenience (matches Sonic Space usage)
get_db = get_db_postgres

