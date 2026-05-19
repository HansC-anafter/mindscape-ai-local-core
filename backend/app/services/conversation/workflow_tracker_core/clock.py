"""Clock helpers for workflow tracking."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
