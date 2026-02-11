"""
Common utilities shared across workspace sub-modules.
"""

from datetime import datetime, timezone


def _utc_now() -> datetime:
    """Return timezone-aware UTC now. Fixes Postgres timestamptz offset bug."""
    return datetime.now(timezone.utc)
