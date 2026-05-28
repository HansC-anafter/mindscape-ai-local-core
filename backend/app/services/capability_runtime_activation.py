"""Explicit runtime activation for installed capability APIs."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import FastAPI

from backend.app.services.pack_activation_service import PackActivationService

logger = logging.getLogger(__name__)


def activate_installed_capability_routes(
    *,
    app: FastAPI,
    capability_code: str,
    reason: str,
) -> Dict[str, Any]:
    """Refresh descriptors and activate one installed capability in this process."""

    started = time.monotonic()
    from app.services.capability_registry import load_capabilities
    from backend.app.services.capability_api_loader import (
        activate_capability_api_code,
        refresh_seeded_capability_descriptors,
    )

    load_capabilities(reset=True)
    descriptors = refresh_seeded_capability_descriptors(app)
    matching_descriptors = [
        descriptor
        for descriptor in descriptors
        if descriptor.capability_code == capability_code
    ]
    routers = activate_capability_api_code(
        app=app,
        capability_code=capability_code,
        activation_mode=f"explicit_install_activation:{reason}",
        activation_service=PackActivationService(),
    )
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    if duration_ms >= 1000:
        logger.warning(
            "Capability runtime activation was slow: capability=%s duration_ms=%.2f",
            capability_code,
            duration_ms,
        )
    return {
        "state": "activated",
        "capability_code": capability_code,
        "descriptors": len(matching_descriptors),
        "routers_registered": len(routers),
        "duration_ms": duration_ms,
    }
