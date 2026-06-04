"""Lifecycle helpers for workspace event streams."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

DisconnectProbe = Callable[[], Awaitable[bool]]


async def should_stop_event_stream(
    disconnect_probe: DisconnectProbe | None,
    *,
    logger: logging.Logger,
    workspace_id: str,
) -> bool:
    """Return true when the SSE client has disconnected."""

    if disconnect_probe is None:
        return False

    try:
        disconnected = await disconnect_probe()
    except Exception as exc:
        logger.warning(
            "[SSE] Client disconnect probe failed for ws=%s: %s",
            workspace_id[:8],
            exc,
        )
        return False

    if disconnected:
        logger.info("[SSE] Client disconnected for ws=%s; stopping stream", workspace_id[:8])
    return disconnected
