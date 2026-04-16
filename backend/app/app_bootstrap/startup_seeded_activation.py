import logging
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.pack_activation_service import PackActivationService

logger = logging.getLogger(__name__)

_PRESERVE_STARTUP_SEEDED_INSTALL_STATES = {"validation_failed", "validation_pending"}
_PRESERVE_STARTUP_SEEDED_ACTIVATION_STATES = {"pending_restart"}


def should_preserve_startup_seeded_activation(
    existing_state: Optional[Dict[str, Any]],
) -> bool:
    if not existing_state:
        return False
    if (
        existing_state.get("activation_state")
        in _PRESERVE_STARTUP_SEEDED_ACTIVATION_STATES
    ):
        return True
    return (
        existing_state.get("install_state")
        in _PRESERVE_STARTUP_SEEDED_INSTALL_STATES
    )


def record_startup_seeded_activation_pending(
    *,
    activation_service: PackActivationService,
    pack_id: str,
    manifest: Optional[Dict[str, Any]],
    manifest_path: Optional[Path],
):
    existing = activation_service.get_state(pack_id)
    if should_preserve_startup_seeded_activation(existing):
        logger.info(
            "Preserving existing activation state for %s during startup seeding (install_state=%s, activation_state=%s)",
            pack_id,
            existing.get("install_state"),
            existing.get("activation_state"),
        )
        return existing
    return activation_service.record_activation_pending(
        pack_id=pack_id,
        manifest=manifest,
        manifest_path=manifest_path,
        activation_mode="startup_seeded",
    )
