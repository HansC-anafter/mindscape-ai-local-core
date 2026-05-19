"""Storage helpers for task artifacts."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def artifact_type_value(artifact: Any) -> str:
    artifact_type = getattr(artifact, "artifact_type", None)
    return artifact_type.value if hasattr(artifact_type, "value") else str(artifact_type)


async def prepare_workspace_storage(
    *,
    store: Any,
    workspace_id: str,
) -> tuple[Any, Optional[Dict[str, Any]]]:
    workspace = await store.workspaces.get_workspace(workspace_id)
    if not workspace:
        return None, {
            "type": "workspace_not_found",
            "message": "Workspace not found, artifact creation skipped",
            "action_required": "Please check workspace configuration",
        }

    if not workspace.storage_base_path:
        return workspace, {
            "type": "storage_path_not_configured",
            "message": "Workspace storage path not configured. Artifact creation skipped.",
            "action_required": "Please set storage path in workspace settings",
            "storage_path_missing": True,
        }

    storage_path = Path(workspace.storage_base_path).expanduser().resolve()
    if not storage_path.exists():
        try:
            storage_path.mkdir(parents=True, exist_ok=True)
            logger.info("Created storage directory: %s", storage_path)
        except Exception as exc:
            return workspace, {
                "type": "storage_path_not_exists",
                "message": (
                    f"Storage path does not exist and cannot be created: {storage_path}"
                ),
                "action_required": (
                    "Please check workspace storage configuration or create the "
                    f"directory: {exc}"
                ),
                "storage_path": str(storage_path),
            }

    if not os.access(storage_path, os.W_OK):
        return workspace, {
            "type": "storage_path_not_writable",
            "message": f"Storage path is not writable: {storage_path}",
            "action_required": "Please check directory permissions",
            "storage_path": str(storage_path),
        }

    return workspace, None


def artifact_write_failed_warning(artifact: Any) -> Dict[str, Any]:
    return {
        "type": "artifact_write_failed",
        "message": (
            artifact.metadata.get("write_error", "Failed to write artifact file")
            if getattr(artifact, "metadata", None)
            else "Failed to write artifact file"
        ),
        "action_required": (
            "Artifact content is available but file write failed. "
            "Please check storage configuration."
        ),
        "fallback_path": getattr(artifact, "storage_ref", None),
    }


def persist_timeline_item_data(
    *,
    timeline_items_store: Any,
    timeline_item: Any,
    artifact_id: Optional[str] = None,
    warning: Optional[Dict[str, Any]] = None,
    clear_warning: bool = False,
) -> None:
    data = dict(timeline_item.data or {})
    if artifact_id:
        data["artifact_id"] = artifact_id
    if clear_warning:
        data.pop("artifact_warning", None)
        data.pop("artifact_creation_failed", None)
    if warning:
        data["artifact_warning"] = warning
        data["artifact_creation_failed"] = True
    timeline_item.data = data
    timeline_items_store.update_timeline_item(item_id=timeline_item.id, data=data)


def set_pending_sync_state_if_enabled(artifact: Any, workspace: Any) -> None:
    if getattr(artifact, "sync_state", None) is not None:
        return

    try:
        storage_config = workspace.storage_config or {}
        if isinstance(storage_config, str):
            storage_config = json.loads(storage_config)

        cloud_enabled = storage_config.get("cloud_enabled", False)
        if not cloud_enabled:
            cloud_enabled = os.getenv("CLOUD_SYNC_ENABLED", "false").lower() == "true"

        if cloud_enabled:
            artifact.sync_state = "pending"
            logger.info("Artifact %s marked as pending sync", getattr(artifact, "id", None))
    except Exception as exc:
        logger.warning(
            "Failed to check cloud sync configuration: %s, defaulting to None",
            exc,
        )
        artifact.sync_state = None
