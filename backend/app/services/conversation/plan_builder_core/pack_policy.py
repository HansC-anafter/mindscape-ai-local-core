"""Pack availability and side-effect policy helpers for PlanBuilder."""

from __future__ import annotations

import logging
from typing import Optional

from ...capability_registry import get_registry
from ....models.workspace import SideEffectLevel
from ...stores.installed_packs_store import InstalledPacksStore

logger = logging.getLogger(__name__)


def is_pack_available(pack_id: str) -> bool:
    """Return whether a pack is installed or present in the registry."""
    try:
        store = InstalledPacksStore()
        if store.get_pack(pack_id):
            return True

        registry = get_registry()
        capability_info = registry.capabilities.get(pack_id)
        if capability_info:
            return True

        return False
    except Exception as exc:
        logger.warning("Failed to check pack availability for %s: %s", pack_id, exc)
        return False


def check_pack_tools_configured(pack_id: str) -> bool:
    """Return whether a pack's declared tools are considered configured."""
    try:
        registry = get_registry()
        capability_info = registry.capabilities.get(pack_id)
        if not capability_info:
            return False

        manifest = capability_info.get("manifest", {})
        tools = manifest.get("tools", [])

        if tools:
            return True

        return True
    except Exception as exc:
        logger.warning("Failed to check pack tools for %s: %s", pack_id, exc)
        return False


def determine_side_effect_level(pack_id: str) -> SideEffectLevel:
    """Return the side effect level for a pack, defaulting conservatively."""
    try:
        store = InstalledPacksStore()
        row = store.get_pack(pack_id)
        metadata = row.get("metadata") if row else None
        if isinstance(metadata, dict) and "side_effect_level" in metadata:
            level_str = metadata["side_effect_level"]
            try:
                return SideEffectLevel(level_str)
            except ValueError:
                logger.warning(
                    "Invalid side_effect_level '%s' for pack %s, using default",
                    level_str,
                    pack_id,
                )

        registry = get_registry()
        capability_info = registry.capabilities.get(pack_id)
        if capability_info:
            manifest = capability_info.get("manifest", {})
            if "side_effect_level" in manifest:
                level_str = manifest["side_effect_level"]
                try:
                    return SideEffectLevel(level_str)
                except ValueError:
                    logger.warning(
                        "Invalid side_effect_level '%s' for pack %s, using default",
                        level_str,
                        pack_id,
                    )

        logger.debug(
            "No side_effect_level found for pack %s, defaulting to readonly",
            pack_id,
        )
        return SideEffectLevel.READONLY
    except Exception as exc:
        logger.warning(
            "Failed to determine side_effect_level for pack %s: %s, using default",
            pack_id,
            exc,
        )
        return SideEffectLevel.READONLY


def get_pack_id_from_playbook_code(playbook_code: str) -> Optional[str]:
    """Resolve a pack ID from a playbook code."""
    registry = get_registry()

    if "." in playbook_code:
        pack_id, _ = playbook_code.split(".", 1)
        if pack_id in registry.list_capabilities():
            return pack_id

    for capability_code in registry.list_capabilities():
        capability = registry.get_capability(capability_code)
        if not capability:
            continue

        playbooks = registry.get_capability_playbooks(capability_code)
        for playbook_file in playbooks:
            playbook_name = playbook_file.replace(".json", "").replace(".yaml", "")
            if playbook_name == playbook_code:
                return capability_code

    try:
        from ...mindscape_store import MindscapeStore
        from ...playbook_service import PlaybookService

        store = MindscapeStore()
        playbook_service = PlaybookService(store)
        playbook_run = playbook_service.load_playbook_run_sync(
            playbook_code,
            workspace_id=None,
        )
        if playbook_run and playbook_run.playbook:
            metadata = playbook_run.playbook.metadata
            if hasattr(metadata, "capability_tags") and metadata.capability_tags:
                for tag in metadata.capability_tags:
                    if tag in registry.list_capabilities():
                        return tag
    except Exception as exc:
        logger.debug(
            "Failed to get pack_id from playbook service for %s: %s",
            playbook_code,
            exc,
        )

    logger.warning("Could not find pack_id for playbook_code: %s", playbook_code)
    return None
