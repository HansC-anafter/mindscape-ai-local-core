import logging
from datetime import datetime, timezone

from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)
store = MindscapeStore()


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
