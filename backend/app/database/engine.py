"""PostgreSQL SQLAlchemy engine and session factory."""

import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import get_postgres_url, get_engine_kwargs

logger = logging.getLogger(__name__)

# Check required PostgreSQL environment variables
REQUIRED_POSTGRES_ENV_VARS = [
    "POSTGRES_HOST",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
]

missing_vars = [var for var in REQUIRED_POSTGRES_ENV_VARS if not os.getenv(var)]
if missing_vars:
    logger.error(
        f"Missing required PostgreSQL environment variables: {', '.join(missing_vars)}. "
        f"Sonic Space and vector features will not be available. "
        f"Please configure these variables in docker-compose.yml or .env file."
    )
    engine_postgres = None
    SessionLocalPostgres = None
else:
    # Create PostgreSQL engine
    try:
        postgres_url = get_postgres_url()
        engine_kwargs = get_engine_kwargs()
        engine_postgres = create_engine(postgres_url, **engine_kwargs)
        logger.info("PostgreSQL engine initialized successfully")
    except Exception as e:
        logger.error(f"PostgreSQL engine initialization failed: {e}")
        logger.error("Sonic Space and vector features will not be available")
        # Don't raise here - allow lazy initialization
        engine_postgres = None

# Create session factory
if engine_postgres:
    SessionLocalPostgres = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine_postgres
    )
else:
    SessionLocalPostgres = None
    if not missing_vars:
        # Only log error if env vars were present but connection failed
        logger.error("PostgreSQL session factory not created due to engine initialization failure")

