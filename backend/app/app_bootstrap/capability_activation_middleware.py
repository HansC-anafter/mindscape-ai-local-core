from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.pack_activation_service import PackActivationService
from backend.app.services.capability_api_loader import (
    activate_capability_api_code,
    find_seeded_capability_for_path,
    get_capability_api_activation_policy,
    refresh_seeded_capability_descriptors,
)

logger = logging.getLogger(__name__)


async def ensure_capability_activation_for_request(
    request: Request,
) -> Optional[JSONResponse]:
    """
    Lazily activate seeded capability APIs on first request when startup policy is seed_only.
    """
    if get_capability_api_activation_policy() != "seed_only":
        return None

    if request.method.upper() == "OPTIONS":
        return None

    capability_code = find_seeded_capability_for_path(request.app, request.url.path)
    if (
        not capability_code
        and request.url.path.startswith("/api/v1/capabilities/")
    ):
        refresh_seeded_capability_descriptors(request.app)
        capability_code = find_seeded_capability_for_path(request.app, request.url.path)
    if not capability_code:
        return None

    activation_service = getattr(
        request.app.state, "capability_activation_service", None
    ) or PackActivationService()

    try:
        activate_capability_api_code(
            app=request.app,
            capability_code=capability_code,
            activation_mode="request_activate",
            activation_service=activation_service,
        )
    except Exception as exc:
        logger.error(
            "Request-time capability activation failed for %s (%s): %s",
            capability_code,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    f"Capability '{capability_code}' failed to activate for "
                    f"path {request.url.path}: {exc}"
                )
            },
        )

    return None
