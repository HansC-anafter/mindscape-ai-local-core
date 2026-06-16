"""Registration helpers for runtime-facing optional route modules."""

from __future__ import annotations

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def register_runtime_route_modules(app: FastAPI) -> None:
    from backend.app.routes.runtime_dispatch import router as runtime_dispatch_router

    app.include_router(runtime_dispatch_router)
    logger.info("Runtime dispatch routes registered")

    try:
        from backend.app.routes.host_runtime_sessions import (
            router as host_runtime_sessions_router,
        )

        app.include_router(host_runtime_sessions_router, tags=["host-runtime-sessions"])
        logger.info("Host Runtime Session Gateway routes registered")
    except Exception as exc:
        logger.warning(
            "Failed to register Host Runtime Session Gateway routes: %s",
            exc,
        )
