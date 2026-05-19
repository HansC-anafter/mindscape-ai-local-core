"""Clock helper for suggestion card creation."""

from datetime import datetime, timezone


def utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
