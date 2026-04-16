"""Runner control sentinels — restart and drain/quiesce handling."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.app.runner.utils import _utc_now

logger = logging.getLogger(__name__)

_RESTART_SENTINEL_PATH = Path("/app/data/.restart_runner")
_RESTART_DRAIN_TIMEOUT_SECONDS = 30
_DRAIN_SENTINEL_PATH = Path("/app/data/.drain_runner")
_DRAIN_SENTINEL_DEFAULT_TTL_SECONDS = 4 * 60 * 60


def _load_active_sentinel(
    *,
    path: Path,
    label: str,
    default_ttl_seconds: int,
    consume: bool,
) -> dict[str, object] | None:
    """Parse a sentinel file and return metadata while it remains valid."""
    if not path.exists():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
        sentinel = json.loads(raw)
        requested_at = str(sentinel.get("requested_at") or "")
        ttl_seconds = int(sentinel.get("ttl_seconds") or default_ttl_seconds)
        request_id = str(sentinel.get("request_id") or "unknown")

        req_time = datetime.fromisoformat(requested_at)
        if req_time.tzinfo is None:
            req_time = req_time.replace(tzinfo=timezone.utc)
        age_seconds = (_utc_now() - req_time).total_seconds()

        if age_seconds > ttl_seconds:
            logger.warning(
                "Stale %s sentinel (age=%.1fs, ttl=%ds), removing: %s",
                label,
                age_seconds,
                ttl_seconds,
                request_id,
            )
            path.unlink(missing_ok=True)
            return None

        if consume:
            path.unlink(missing_ok=True)

        return {
            "request_id": request_id,
            "requested_at": requested_at,
            "ttl_seconds": ttl_seconds,
            "age_seconds": age_seconds,
        }
    except Exception as exc:
        logger.warning("Failed to parse %s sentinel, removing: %s", label, exc)
        path.unlink(missing_ok=True)
        return None


def _check_restart_sentinel() -> bool:
    """Check if a restart sentinel file exists and is still valid.

    Returns True if the runner should exit for restart.
    Removes the sentinel file before returning to prevent restart loops.
    """
    sentinel = _load_active_sentinel(
        path=_RESTART_SENTINEL_PATH,
        label="restart",
        default_ttl_seconds=30,
        consume=True,
    )
    if not sentinel:
        return False
    logger.info(
        "Restart sentinel detected (age=%.1fs, request_id=%s), preparing to exit",
        float(sentinel["age_seconds"]),
        sentinel["request_id"],
    )
    return True


def _check_drain_sentinel() -> dict[str, object] | None:
    """Return active drain sentinel metadata when runners should stop dequeuing."""
    return _load_active_sentinel(
        path=_DRAIN_SENTINEL_PATH,
        label="drain",
        default_ttl_seconds=_DRAIN_SENTINEL_DEFAULT_TTL_SECONDS,
        consume=False,
    )
