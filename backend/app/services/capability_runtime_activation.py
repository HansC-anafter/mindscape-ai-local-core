"""Explicit runtime activation for installed capability APIs."""

from __future__ import annotations

import logging
import time
import hashlib
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI

from backend.app.services.capability_runtime_refresh import (
    prepare_capability_for_reactivation,
)
from backend.app.services.capability_pack_route_cache import (
    clear_installed_capability_metadata_caches,
)

logger = logging.getLogger(__name__)


def activate_installed_capability_routes(
    *,
    app: FastAPI,
    capability_code: str,
    reason: str,
    expected_manifest_hash: str | None = None,
) -> Dict[str, Any]:
    """Refresh descriptors and activate one installed capability in this process."""

    started = time.monotonic()
    from app.services.capability_registry import reload_capability
    from backend.app.services.capability_api_loader import (
        _get_runtime_state,
        activate_capability_api_code,
        refresh_seeded_capability_descriptors,
    )

    state = _get_runtime_state(app)
    with state["activation_lock"]:
        clear_installed_capability_metadata_caches(
            capability_code=capability_code,
            reason=f"explicit_runtime_activation:{reason}",
        )
        descriptors = refresh_seeded_capability_descriptors(app)
        matching_descriptors = [
            descriptor
            for descriptor in descriptors
            if descriptor.capability_code == capability_code
        ]
        capabilities_dir = (
            matching_descriptors[0].capability_dir.parent
            if matching_descriptors
            else None
        )
        if not reload_capability(capability_code, capabilities_dir):
            raise ValueError(f"capability_manifest_not_found:{capability_code}")
        manifest_path = (
            matching_descriptors[0].manifest_path
            if matching_descriptors
            else Path(__file__).resolve().parent.parent
            / "capabilities"
            / capability_code
            / "manifest.yaml"
        )
        if not manifest_path.exists():
            raise ValueError(f"capability_manifest_not_found:{capability_code}")
        actual_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if (
            expected_manifest_hash
            and actual_manifest_hash != expected_manifest_hash
        ):
            raise ValueError("candidate_manifest_hash_readback_mismatch")
        refresh = prepare_capability_for_reactivation(
            app=app,
            capability_code=capability_code,
            descriptors=matching_descriptors,
        )
        routers = activate_capability_api_code(
            app=app,
            capability_code=capability_code,
            activation_mode=f"explicit_install_activation:{reason}",
            activation_service=None,
            force_refresh=True,
        )
        if routers:
            app.openapi_schema = None
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
        "routes_removed": refresh["removed_routes"],
        "modules_purged": refresh["purged_modules"],
        "duration_ms": duration_ms,
        "manifest_hash": actual_manifest_hash,
    }
