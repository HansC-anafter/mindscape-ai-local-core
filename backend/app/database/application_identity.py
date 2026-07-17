"""Role-preserving PostgreSQL application identity."""

from __future__ import annotations

import hashlib
import os
import re


MAX_POSTGRES_APPLICATION_NAME_BYTES = 63
DEFAULT_PROCESS_APPLICATION_NAME = "local-core-unidentified"
ALLOWED_DATABASE_ROLES = frozenset(
    {
        "core",
        "vector",
        "core-readonly",
        "vector-readonly",
        "session",
    }
)
_PROCESS_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _process_application_name(value: str | None = None) -> str:
    candidate = str(
        value if value is not None else os.getenv("DB_APPLICATION_NAME", "")
    ).strip()
    if not candidate:
        return DEFAULT_PROCESS_APPLICATION_NAME
    if not candidate.isascii() or not _PROCESS_NAME_PATTERN.fullmatch(candidate):
        return DEFAULT_PROCESS_APPLICATION_NAME
    return candidate


def _fit_postgres_identifier(value: str) -> str:
    encoded = value.encode("ascii")
    if len(encoded) <= MAX_POSTGRES_APPLICATION_NAME_BYTES:
        return value
    digest = hashlib.sha256(encoded).hexdigest()[:10]
    suffix = f"-{digest}"
    prefix_budget = MAX_POSTGRES_APPLICATION_NAME_BYTES - len(suffix)
    return value[:prefix_budget] + suffix


def application_name_for_role(
    database_role: str,
    *,
    process_application_name: str | None = None,
) -> str:
    """Return one bounded process-role identity for a PostgreSQL connection."""

    role = str(database_role or "").strip().lower()
    if role not in ALLOWED_DATABASE_ROLES:
        raise ValueError(f"unsupported_database_application_role:{role or 'empty'}")
    process_name = _process_application_name(process_application_name)
    return _fit_postgres_identifier(f"{process_name}:{role}")


__all__ = [
    "ALLOWED_DATABASE_ROLES",
    "DEFAULT_PROCESS_APPLICATION_NAME",
    "MAX_POSTGRES_APPLICATION_NAME_BYTES",
    "application_name_for_role",
]
