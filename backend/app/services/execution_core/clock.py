"""Clock helpers shared by execution/orchestration services."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
