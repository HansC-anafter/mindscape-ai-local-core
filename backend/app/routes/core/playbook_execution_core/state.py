import logging
from datetime import datetime, timezone

from backend.app.routes.core.execution_shared import (
    playbook_executor,
    playbook_runner,
    playbook_service,
)

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
