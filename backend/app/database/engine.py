"""PostgreSQL SQLAlchemy engines and session factories for core and vector roles."""

import logging
from sqlalchemy.orm import sessionmaker

from .config import (
    get_postgres_url_core,
    get_postgres_url_vector,
)
from .engine_factory import create_transaction_engine

logger = logging.getLogger(__name__)


def _init_engine(role: str, url_provider):
    try:
        postgres_url = url_provider(required=False)
        if not postgres_url:
            logger.warning(
                f"PostgreSQL {role} engine not initialized (missing configuration)"
            )
            return None
        engine = create_transaction_engine(postgres_url, f"local-core-{role}")
        logger.info(f"PostgreSQL {role} engine initialized successfully")
        return engine
    except Exception as e:
        logger.error(f"PostgreSQL {role} engine initialization failed: {e}")
        return None


engine_postgres_core = _init_engine("core", get_postgres_url_core)
engine_postgres_vector = _init_engine("vector", get_postgres_url_vector)

# Backward compatibility
engine_postgres = engine_postgres_core

SessionLocalCore = (
    sessionmaker(autocommit=False, autoflush=False, bind=engine_postgres_core)
    if engine_postgres_core
    else None
)
SessionLocalVector = (
    sessionmaker(autocommit=False, autoflush=False, bind=engine_postgres_vector)
    if engine_postgres_vector
    else None
)

# Backward compatibility
SessionLocalPostgres = SessionLocalCore
