"""Bounded file-backed database secret resolution."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote


MAX_SECRET_BYTES = 4096


def read_secret_file(path_value: str) -> str:
    """Read one regular, non-symlink secret file without normalizing its value."""
    path = Path(path_value)
    if path.is_symlink():
        raise ValueError("Database secret file must not be a symlink")
    if not path.is_file():
        raise ValueError("Database secret file is missing")
    raw = path.read_bytes()
    if len(raw) > MAX_SECRET_BYTES:
        raise ValueError("Database secret file exceeds the size limit")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
        if raw.endswith(b"\r"):
            raw = raw[:-1]
    if not raw or b"\n" in raw or b"\r" in raw or b"\x00" in raw:
        raise ValueError("Database secret file must contain one non-empty line")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Database secret file must contain UTF-8 text") from exc


def get_role_password(role: str) -> str | None:
    """Resolve a role password, preferring its explicit file contract."""
    role_key = role.upper()
    role_file = os.getenv(f"POSTGRES_{role_key}_PASSWORD_FILE")
    if role_file:
        return read_secret_file(role_file)
    role_value = os.getenv(f"POSTGRES_{role_key}_PASSWORD")
    if role_value:
        return role_value
    if role_key != "CORE":
        return None
    generic_file = os.getenv("POSTGRES_PASSWORD_FILE")
    if generic_file:
        return read_secret_file(generic_file)
    generic_value = os.getenv("POSTGRES_PASSWORD")
    return generic_value or None


def quote_postgres_url_component(value: str) -> str:
    """Quote a credential or database component for a PostgreSQL URL."""
    return quote(value, safe="")
