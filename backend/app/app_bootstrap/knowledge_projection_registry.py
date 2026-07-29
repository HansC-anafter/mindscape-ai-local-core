"""Startup seam for installed knowledge-projection descriptors."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI

from backend.app.app_bootstrap.startup_contract import capture_phase_duration

logger = logging.getLogger(__name__)


def hydrate_knowledge_projection_registry(
    app: FastAPI,
) -> dict[str, Any]:
    """Load projection descriptors before product routes accept source actions."""

    started = time.monotonic()
    try:
        from backend.app.services.knowledge_projection.retrievable.installed_manifest_loader import (
            hydrate_installed_projection_manifests,
        )

        receipt = hydrate_installed_projection_manifests()
        app.state.knowledge_projection_registry = receipt
        logger.info(
            "Knowledge projection registry %s: manifests=%d/%d "
            "capabilities=%d descriptors=%d errors=%d",
            receipt["status"],
            receipt["parsed_manifest_count"],
            receipt["scanned_manifest_count"],
            receipt["registered_capability_count"],
            receipt["registered_descriptor_count"],
            len(receipt["errors"]),
        )
        return receipt
    except Exception as exc:
        receipt = {
            "status": "failed",
            "error": str(exc),
        }
        app.state.knowledge_projection_registry = receipt
        logger.error(
            "Knowledge projection registry hydration failed: %s",
            exc,
            exc_info=True,
        )
        raise
    finally:
        capture_phase_duration(
            "startup.knowledge_projection_registry",
            started,
            logger,
        )


__all__ = ["hydrate_knowledge_projection_registry"]
