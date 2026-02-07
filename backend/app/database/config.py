"""PostgreSQL database configuration for core and vector roles."""

import os
import logging
from typing import Optional, Dict
from urllib.parse import urlparse, unquote

logger = logging.getLogger(__name__)


ROLE_CORE = "core"
ROLE_VECTOR = "vector"


def _get_role_env(role: str, key: str) -> Optional[str]:
    role_key = role.upper()
    return os.getenv(f"POSTGRES_{role_key}_{key}") or os.getenv(f"POSTGRES_{key}")


def _get_role_url(role: str) -> Optional[str]:
    role_key = role.upper()
    url = os.getenv(f"DATABASE_URL_{role_key}") or os.getenv(f"POSTGRES_{role_key}_URL")
    if url and (url.startswith("postgresql://") or url.startswith("postgres://")):
        return url
    return None


def _get_legacy_url() -> Optional[str]:
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return url
    return None


def _get_default_db(role: str) -> str:
    return "mindscape_vectors" if role == ROLE_VECTOR else "mindscape_core"


def _build_role_url(role: str) -> Optional[str]:
    host = _get_role_env(role, "HOST")
    if not host:
        return None
    port = _get_role_env(role, "PORT") or "5432"
    db = _get_role_env(role, "DB") or _get_default_db(role)
    user = _get_role_env(role, "USER") or "mindscape"
    password = _get_role_env(role, "PASSWORD") or "mindscape_password"
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _resolve_postgres_url(role: str) -> Optional[str]:
    url = _get_role_url(role)
    if url:
        logger.info(f"Using PostgreSQL {role} URL from role-specific env")
        return url

    url = _build_role_url(role)
    if url:
        logger.info(f"Using PostgreSQL {role} URL from role-specific parts")
        return url

    legacy_url = _get_legacy_url()
    if legacy_url:
        logger.warning(
            f"Falling back to DATABASE_URL for PostgreSQL {role} connection"
        )
        return legacy_url

    return None


def get_postgres_url_core(required: bool = True) -> str:
    """Get PostgreSQL connection URL for core database."""
    url = _resolve_postgres_url(ROLE_CORE)
    if url:
        return url
    if required:
        raise ValueError(
            "PostgreSQL core configuration missing. "
            "Set DATABASE_URL_CORE or POSTGRES_CORE_* environment variables."
        )
    return ""


def get_postgres_url_vector(required: bool = True) -> str:
    """Get PostgreSQL connection URL for vector database."""
    url = _resolve_postgres_url(ROLE_VECTOR)
    if url:
        return url
    if required:
        raise ValueError(
            "PostgreSQL vector configuration missing. "
            "Set DATABASE_URL_VECTOR or POSTGRES_VECTOR_* environment variables."
        )
    return ""


def get_postgres_url(required: bool = True) -> str:
    """Backward-compatible alias for core PostgreSQL URL."""
    return get_postgres_url_core(required=required)


def _parse_postgres_url(url: str) -> Dict[str, Optional[str]]:
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/") if parsed.path else None,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
    }


def _get_postgres_config(role: str) -> Dict[str, Optional[str]]:
    url = _resolve_postgres_url(role)
    if url:
        return _parse_postgres_url(url)

    host = _get_role_env(role, "HOST")
    port = _get_role_env(role, "PORT") or "5432"
    db = _get_role_env(role, "DB") or _get_default_db(role)
    user = _get_role_env(role, "USER") or "mindscape"
    password = _get_role_env(role, "PASSWORD") or "mindscape_password"
    return {
        "host": host,
        "port": int(port),
        "database": db,
        "user": user,
        "password": password,
    }


def get_core_postgres_config() -> Dict[str, Optional[str]]:
    """Get PostgreSQL connection config for core database."""
    return _get_postgres_config(ROLE_CORE)


def get_vector_postgres_config() -> Dict[str, Optional[str]]:
    """Get PostgreSQL connection config for vector database."""
    return _get_postgres_config(ROLE_VECTOR)


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
