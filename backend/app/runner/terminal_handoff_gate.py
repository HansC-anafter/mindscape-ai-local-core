"""Serialize terminal publication until the same runner claims a successor."""

from __future__ import annotations

import asyncio
import logging
import os

from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore


logger = logging.getLogger("backend.app.runner.worker")
DEFAULT_LOCK_KEY = "mindscape:runner:terminal-handoff:default-local-browser"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def terminal_handoff_enabled() -> bool:
    if "LOCAL_CORE_RUNNER_TERMINAL_HANDOFF_ENABLED" in os.environ:
        return _env_bool("LOCAL_CORE_RUNNER_TERMINAL_HANDOFF_ENABLED")
    # Keep graceful in-container worker refreshes effective before the compose
    # service itself is recreated with the explicit flag.
    return os.getenv("LOCAL_CORE_RUNNER_ID", "").startswith(
        "default-browser-steady-"
    )


def _lock_key() -> str:
    return (
        os.getenv("LOCAL_CORE_RUNNER_TERMINAL_HANDOFF_LOCK_KEY")
        or DEFAULT_LOCK_KEY
    ).strip()


def _owner_id(runner_id: str) -> str:
    return f"{str(runner_id or '').strip()}:terminal-handoff"


def _ttl_seconds() -> int:
    try:
        return max(
            5,
            int(os.getenv("LOCAL_CORE_RUNNER_TERMINAL_HANDOFF_TTL_SECONDS", "30")),
        )
    except ValueError:
        return 30


def _poll_interval_seconds() -> float:
    try:
        milliseconds = int(
            os.getenv("LOCAL_CORE_RUNNER_TERMINAL_HANDOFF_POLL_INTERVAL_MS", "50")
        )
    except ValueError:
        milliseconds = 50
    return max(10, milliseconds) / 1000.0


async def acquire_terminal_handoff(
    redis_queue: RedisRunnerQueueStore | None,
    *,
    runner_id: str,
) -> bool:
    """Wait for exclusive terminal publication ownership.

    The owner intentionally keeps this lease after publishing a terminal state.
    Its next successful DB claim releases the lease, making completion+replacement
    a serialized handoff instead of a burst of independent terminal transitions.
    """

    if not terminal_handoff_enabled() or redis_queue is None:
        return False

    owner_id = _owner_id(runner_id)
    while True:
        try:
            acquired = await redis_queue.acquire_lock(
                _lock_key(),
                owner_id,
                ttl_seconds=_ttl_seconds(),
            )
        except Exception as exc:
            logger.warning(
                "Runner terminal handoff gate unavailable runner_id=%s error=%s",
                runner_id,
                exc,
            )
            return False
        if acquired:
            return True
        await asyncio.sleep(_poll_interval_seconds())


async def release_terminal_handoff_after_claim(
    redis_queue: RedisRunnerQueueStore | None,
    *,
    runner_id: str,
) -> bool:
    """Release a terminal handoff only after a replacement row is RUNNING."""

    if not terminal_handoff_enabled() or redis_queue is None:
        return False
    try:
        return await redis_queue.release_lock(
            _lock_key(),
            _owner_id(runner_id),
        )
    except Exception as exc:
        logger.warning(
            "Runner terminal handoff release failed runner_id=%s error=%s",
            runner_id,
            exc,
        )
        return False
