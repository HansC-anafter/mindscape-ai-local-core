"""Build candidate metadata without persisting committed pack truth."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

from backend.app.routes.core.capability_install_core.restart_policy import (
    apply_restart_decision_to_payload,
)


def build_candidate_metadata(
    *,
    capability_code: str,
    version: str,
    manifest: Mapping[str, Any],
    installed_manifest_path: Path,
    restart_decision: Mapping[str, Any],
    extra_metadata: Optional[Mapping[str, Any]],
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    """Return validated metadata for the later single truth transaction."""

    from backend.app.services.model_route_slot_registry import ModelRouteSlotRegistry

    if not installed_manifest_path.is_file():
        raise RuntimeError("candidate_installed_manifest_missing")
    installed_manifest = yaml.safe_load(
        installed_manifest_path.read_text(encoding="utf-8")
    )
    if not isinstance(installed_manifest, dict):
        raise RuntimeError("candidate_installed_manifest_invalid")
    metadata: dict[str, Any] = {
        "version": installed_manifest.get("version", version),
        "side_effect_level": installed_manifest.get("side_effect_level"),
    }
    if extra_metadata:
        metadata.update(dict(extra_metadata))
    metadata = apply_restart_decision_to_payload(metadata, dict(restart_decision))
    route_slots = ModelRouteSlotRegistry().extract_pack_slots_from_manifest(
        pack_id=capability_code,
        pack_meta=dict(manifest),
        manifest_path=str(installed_manifest_path),
        installed=True,
        enabled=True,
    )
    metadata["model_route_slots"] = route_slots
    metadata["model_route_slot_count"] = len(route_slots)

    validation_state = None
    if manifest.get("playbooks"):
        from app.services.pack_validation_background import (
            build_validation_status_payload,
        )

        validation_state = build_validation_status_payload(
            "pending",
            mode="background",
        )
        metadata["validation"] = validation_state
    return metadata, validation_state
