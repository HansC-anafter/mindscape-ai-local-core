"""Shared helpers for chat and embedding settings routes."""

from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
