"""Shared value helpers for task result landing."""

from datetime import datetime, timezone
from typing import Any, Optional


DATA_SOURCE_SUMMARY_LIMIT = 500


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def clean_string(value: Any) -> Optional[str]:
    """Return a trimmed string or None when the value is empty/non-string."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
