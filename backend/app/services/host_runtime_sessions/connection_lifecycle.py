"""Deterministic WebSocket teardown for host-runtime routes."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def close_host_runtime_websocket(websocket: Any) -> None:
    """Release the ASGI socket after every host-runtime handler exit.

    A peer keepalive failure is not always surfaced as ``WebSocketDisconnect``;
    the ``websockets`` implementation may raise ``ConnectionClosedError``
    instead. In both cases the route must attempt one explicit close so the
    server does not leave a TCP half-close in CLOSE_WAIT.
    """

    try:
        await websocket.close()
    except Exception:  # pragma: no cover - transport-specific close failures
        logger.debug("host-runtime websocket close already completed", exc_info=True)
