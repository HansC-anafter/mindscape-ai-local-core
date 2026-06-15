"""Shared helpers for remaining Postgres store facades."""

from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
