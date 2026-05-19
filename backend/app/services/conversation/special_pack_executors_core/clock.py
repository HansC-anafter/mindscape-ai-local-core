"""Clock helper for special pack executors."""

from datetime import datetime, timezone


def utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
