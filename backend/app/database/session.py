"""PostgreSQL database session management for FastAPI dependency injection."""

import logging
from typing import Generator
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .engine import SessionLocalCore, SessionLocalVector

logger = logging.getLogger(__name__)


def _yield_session(session_factory, role: str) -> Generator[Session, None, None]:
    if session_factory is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"PostgreSQL {role} database not configured. "
                f"Please configure DATABASE_URL_{role.upper()} or POSTGRES_{role.upper()}_*."
            ),
        )

    db = session_factory()
    try:
        yield db
    except HTTPException:
        # Preserve FastAPI HTTP exceptions (do not mask as 503)
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"PostgreSQL session error: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=503, detail=f"PostgreSQL {role} database error: {str(e)}"
        )
    finally:
        db.close()


def get_db_core() -> Generator[Session, None, None]:
    """Get PostgreSQL core database session."""
    yield from _yield_session(SessionLocalCore, "core")


def get_db_vector() -> Generator[Session, None, None]:
    """Get PostgreSQL vector database session."""
    yield from _yield_session(SessionLocalVector, "vector")


# Backward-compatible aliases
get_db_postgres = get_db_core
get_db = get_db_core
