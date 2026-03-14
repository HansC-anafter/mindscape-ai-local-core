"""Runner utility functions — timezone-aware timestamps and env parsing."""

import os
from datetime import datetime, timezone
from typing import Optional


def _utc_now() -> datetime:
    """Return timezone-aware UTC now. Fixes Postgres timestamptz offset bug."""
    return datetime.now(timezone.utc)


def _parse_utc_iso(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        # Ensure timezone-aware: old code stored naive UTC timestamps.
        # If naive, assume UTC so reaper comparisons don't raise TypeError.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except Exception:
        return default
