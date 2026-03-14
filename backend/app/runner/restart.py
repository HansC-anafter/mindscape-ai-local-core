"""Runner restart sentinel — detects restart requests from backend."""

import json
import logging
from datetime import timezone
from pathlib import Path

from backend.app.runner.utils import _utc_now

logger = logging.getLogger(__name__)

_RESTART_SENTINEL_PATH = Path("/app/data/.restart_runner")
_RESTART_DRAIN_TIMEOUT_SECONDS = 30


def _check_restart_sentinel() -> bool:
    """Check if a restart sentinel file exists and is still valid.

    Returns True if the runner should exit for restart.
    Removes the sentinel file before returning to prevent restart loops.
    """
    if not _RESTART_SENTINEL_PATH.exists():
        return False
    try:
        raw = _RESTART_SENTINEL_PATH.read_text(encoding="utf-8")
        sentinel = json.loads(raw)
        requested_at = sentinel.get("requested_at", "")
        ttl_seconds = sentinel.get("ttl_seconds", 30)
        request_id = sentinel.get("request_id", "unknown")

        # Validate TTL to prevent stale sentinels from triggering restart loops
        from datetime import datetime

        req_time = datetime.fromisoformat(requested_at)
        if req_time.tzinfo is None:
            req_time = req_time.replace(tzinfo=timezone.utc)
        age = (_utc_now() - req_time).total_seconds()
        if age > ttl_seconds:
            logger.warning(
                "Stale restart sentinel (age=%.1fs, ttl=%ds), removing: %s",
                age,
                ttl_seconds,
                request_id,
            )
            _RESTART_SENTINEL_PATH.unlink(missing_ok=True)
            return False

        # Valid sentinel: remove first, then signal restart
        _RESTART_SENTINEL_PATH.unlink(missing_ok=True)
        logger.info(
            "Restart sentinel detected (age=%.1fs, request_id=%s), preparing to exit",
            age,
            request_id,
        )
        return True
    except Exception as e:
        logger.warning("Failed to parse restart sentinel, removing: %s", e)
        _RESTART_SENTINEL_PATH.unlink(missing_ok=True)
        return False
