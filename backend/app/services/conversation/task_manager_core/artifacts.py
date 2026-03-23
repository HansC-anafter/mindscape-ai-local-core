"""Artifact lifecycle helpers extracted from TaskManager."""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from backend.app.services.execution_core.clock import utc_now

logger = logging.getLogger(__name__)


def resolve_task_intent_id(task: Any, execution_result: Dict[str, Any]) -> Optional[str]:
    """Resolve intent binding from the task result or task metadata."""
    intent_id = execution_result.get("intent_id")
    if not intent_id and hasattr(task, "intent_id"):
        intent_id = task.intent_id
    if (
        not intent_id
        and hasattr(task, "metadata")
        and isinstance(task.metadata, dict)
    ):
        intent_id = task.metadata.get("intent_id")
    return intent_id


def _artifact_type_value(artifact: Any) -> str:
    artifact_type = getattr(artifact, "artifact_type", None)
    return artifact_type.value if hasattr(artifact_type, "value") else str(artifact_type)


async def _prepare_workspace_storage(
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


def _artifact_write_failed_warning(artifact: Any) -> Dict[str, Any]:
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


def _persist_timeline_item_data(
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


def _set_pending_sync_state_if_enabled(artifact: Any, workspace: Any) -> None:
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


async def create_artifact_mind_event(
    *,
    store: Any,
    artifact: Any,
    task: Any,
    execution_result: Dict[str, Any],
    utc_now_fn: Callable[[], Any] = utc_now,
) -> None:
    """Create the unified MindEvent record for a new artifact."""
    del execution_result  # Compatibility parameter for callers already passing it.

    if not store:
        logger.debug("Store not available, skipping MindEvent creation for artifact")
        return

    try:
        from backend.app.models.mindscape import EventActor, EventType, MindEvent

        workspace = await store.get_workspace(task.workspace_id)
        if not workspace:
            logger.warning(
                "Workspace %s not found, cannot create MindEvent for artifact",
                task.workspace_id,
            )
            return

        entity_ids = [artifact.id]
        if getattr(artifact, "intent_id", None):
            entity_ids.append(artifact.intent_id)

        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=utc_now_fn(),
            actor=EventActor.AGENT,
            channel="workspace",
            profile_id=workspace.owner_user_id,
            workspace_id=task.workspace_id,
            event_type=EventType.ARTIFACT_CREATED,
            payload={
                "artifact_id": artifact.id,
                "artifact_type": _artifact_type_value(artifact),
                "title": artifact.title,
                "summary": artifact.summary,
                "playbook_code": artifact.playbook_code,
                "task_id": task.id,
                "execution_id": (
                    task.execution_id if hasattr(task, "execution_id") else None
                ),
                "intent_id": getattr(artifact, "intent_id", None),
                "file_path": (
                    artifact.metadata.get("file_path")
                    if getattr(artifact, "metadata", None)
                    else None
                ),
                "storage_ref": getattr(artifact, "storage_ref", None),
            },
            entity_ids=entity_ids,
            metadata={
                "is_artifact": True,
                "artifact_type": _artifact_type_value(artifact),
            },
        )

        store.events.create_event(event, generate_embedding=True)
        logger.info("Created MindEvent for artifact %s", artifact.id)
    except Exception as exc:
        logger.warning("Failed to create MindEvent for artifact: %s", exc, exc_info=True)


def update_artifact_latest_markers(
    *,
    artifacts_store: Any,
    workspace_id: str,
    playbook_code: str,
    artifact_type: str,
    new_artifact_id: str,
) -> None:
    """Flip older versions off and keep the newest artifact marked latest."""
    try:
        artifacts = artifacts_store.list_artifacts_by_playbook(workspace_id, playbook_code)
        same_type_artifacts = [
            artifact
            for artifact in artifacts
            if _artifact_type_value(artifact) == artifact_type
            and artifact.id != new_artifact_id
        ]

        for old_artifact in same_type_artifacts:
            old_metadata = old_artifact.metadata or {}
            if old_metadata.get("is_latest", False):
                artifacts_store.update_artifact(
                    old_artifact.id,
                    metadata={**old_metadata, "is_latest": False},
                )

        new_artifact = artifacts_store.get_artifact(new_artifact_id)
        if new_artifact:
            new_metadata = new_artifact.metadata or {}
            if not new_metadata.get("is_latest", True):
                artifacts_store.update_artifact(
                    new_artifact_id,
                    metadata={**new_metadata, "is_latest": True},
                )
    except Exception as exc:
        logger.warning(
            "Failed to update artifact latest markers for %s: %s",
            new_artifact_id,
            exc,
            exc_info=True,
        )


async def attach_artifact_to_timeline_item(
    *,
    store: Any,
    artifacts_store: Any,
    timeline_items_store: Any,
    artifact_extractor: Any,
    task: Any,
    timeline_item: Any,
    execution_result: Dict[str, Any],
    playbook_code: str,
    get_next_version_fn: Callable[..., int],
    update_latest_markers_fn: Callable[..., None],
    create_mind_event_fn: Callable[..., Awaitable[None]],
) -> Optional[Any]:
    """Create and attach the artifact for a completed task timeline item."""
    try:
        workspace, artifact_warning = await _prepare_workspace_storage(
            store=store,
            workspace_id=task.workspace_id,
        )
        artifact = None

        if not artifact_warning:
            intent_id = resolve_task_intent_id(task, execution_result)
            artifact = artifact_extractor.extract_artifact_from_task_result(
                task=task,
                execution_result=execution_result,
                playbook_code=playbook_code,
                intent_id=intent_id,
            )
            if (
                artifact
                and getattr(artifact, "metadata", None)
                and artifact.metadata.get("write_failed")
            ):
                artifact_warning = _artifact_write_failed_warning(artifact)

        if artifact:
            artifact.metadata = artifact.metadata or {}
            artifact.metadata["version"] = get_next_version_fn(
                workspace_id=task.workspace_id,
                playbook_code=playbook_code,
                artifact_type=_artifact_type_value(artifact),
            )
            artifact.metadata["is_latest"] = True

            if workspace is not None:
                _set_pending_sync_state_if_enabled(artifact, workspace)

            artifact = artifacts_store.create_artifact(artifact)
            logger.info("Created artifact: %s for task %s", artifact.id, task.id)

            update_latest_markers_fn(
                workspace_id=task.workspace_id,
                playbook_code=playbook_code,
                artifact_type=_artifact_type_value(artifact),
                new_artifact_id=artifact.id,
            )
            _persist_timeline_item_data(
                timeline_items_store=timeline_items_store,
                timeline_item=timeline_item,
                artifact_id=artifact.id,
            )
            await create_mind_event_fn(
                artifact=artifact,
                task=task,
                execution_result=execution_result,
            )

        if artifact_warning:
            _persist_timeline_item_data(
                timeline_items_store=timeline_items_store,
                timeline_item=timeline_item,
                warning=artifact_warning,
            )
            logger.warning(
                "Artifact creation failed for task %s: %s. Warning recorded in timeline item %s.",
                task.id,
                artifact_warning.get("message"),
                timeline_item.id,
            )

        return artifact
    except Exception as exc:
        logger.error(
            "Error during artifact creation for task %s: %s",
            task.id,
            exc,
            exc_info=True,
        )
        _persist_timeline_item_data(
            timeline_items_store=timeline_items_store,
            timeline_item=timeline_item,
            warning={
                "type": "artifact_creation_error",
                "message": f"Unexpected error during artifact creation: {exc}",
                "action_required": "Please check logs and try again",
            },
        )
        return None


def _warning_to_retry_response(warning: Dict[str, Any]) -> Dict[str, Any]:
    response = {
        "success": False,
        "error": warning.get("message", "Artifact creation failed"),
    }
    if warning.get("action_required"):
        response["action_required"] = warning["action_required"]
    if warning.get("storage_path_missing") is not None:
        response["storage_path_missing"] = warning["storage_path_missing"]
    if warning.get("storage_path") is not None:
        response["storage_path"] = warning["storage_path"]
    if warning.get("fallback_path") is not None:
        response["fallback_path"] = warning["fallback_path"]
    return response


async def retry_timeline_item_artifact_creation(
    *,
    store: Any,
    tasks_store: Any,
    timeline_items_store: Any,
    artifacts_store: Any,
    artifact_extractor: Any,
    timeline_item_id: str,
    update_latest_markers_fn: Callable[..., None],
    create_mind_event_fn: Callable[..., Awaitable[None]],
) -> Dict[str, Any]:
    """Retry artifact creation for a timeline item that previously recorded a warning."""
    try:
        timeline_item = timeline_items_store.get_timeline_item(timeline_item_id)
        if not timeline_item:
            return {"success": False, "error": "Timeline item not found"}

        if not (
            timeline_item.data and timeline_item.data.get("artifact_creation_failed")
        ):
            return {
                "success": False,
                "error": "No artifact creation failure recorded for this timeline item",
            }

        if not timeline_item.task_id:
            return {
                "success": False,
                "error": "Timeline item has no associated task",
            }

        task = tasks_store.get_task(timeline_item.task_id)
        if not task:
            return {"success": False, "error": "Task not found"}

        execution_result = timeline_item.data.copy() if timeline_item.data else {}
        if not execution_result and task.result:
            execution_result = task.result
        if not execution_result:
            return {
                "success": False,
                "error": "No execution result available for artifact creation",
            }

        playbook_code = execution_result.get("playbook_code") or task.pack_id or "unknown"
        workspace, artifact_warning = await _prepare_workspace_storage(
            store=store,
            workspace_id=timeline_item.workspace_id,
        )
        if artifact_warning:
            return _warning_to_retry_response(artifact_warning)

        try:
            artifact = artifact_extractor.extract_artifact_from_task_result(
                task=task,
                execution_result=execution_result,
                playbook_code=playbook_code,
                intent_id=resolve_task_intent_id(task, execution_result),
            )
        except Exception as exc:
            logger.error(
                "Error extracting artifact during retry: %s",
                exc,
                exc_info=True,
            )
            return {
                "success": False,
                "error": f"Failed to extract artifact: {exc}",
                "action_required": "Please check execution result format and try again",
            }

        if not artifact:
            logger.warning(
                "extract_artifact_from_task_result returned None for task %s, playbook_code: %s, execution_result keys: %s",
                task.id,
                playbook_code,
                list(execution_result.keys()) if execution_result else "None",
            )
            return {
                "success": False,
                "error": (
                    "Failed to extract artifact from execution result. "
                    "The execution result may not contain artifact data."
                ),
                "action_required": "Please check if the task execution completed successfully",
            }

        if getattr(artifact, "metadata", None) and artifact.metadata.get("write_failed"):
            return _warning_to_retry_response(_artifact_write_failed_warning(artifact))

        artifact.metadata = artifact.metadata or {}
        artifact.metadata["version"] = artifact_extractor._get_next_version(
            workspace_id=timeline_item.workspace_id,
            playbook_code=playbook_code,
            artifact_type=_artifact_type_value(artifact),
        )
        artifact.metadata["is_latest"] = True

        if workspace is not None:
            _set_pending_sync_state_if_enabled(artifact, workspace)

        artifact = artifacts_store.create_artifact(artifact)
        logger.info(
            "Retry created artifact: %s for timeline item %s",
            artifact.id,
            timeline_item_id,
        )

        update_latest_markers_fn(
            workspace_id=timeline_item.workspace_id,
            playbook_code=playbook_code,
            artifact_type=_artifact_type_value(artifact),
            new_artifact_id=artifact.id,
        )
        _persist_timeline_item_data(
            timeline_items_store=timeline_items_store,
            timeline_item=timeline_item,
            artifact_id=artifact.id,
            clear_warning=True,
        )
        await create_mind_event_fn(
            artifact=artifact,
            task=task,
            execution_result=execution_result,
        )
        return {
            "success": True,
            "artifact_id": artifact.id,
            "message": "Artifact created successfully",
        }
    except Exception as exc:
        logger.error(
            "Failed to retry artifact creation for timeline item %s: %s",
            timeline_item_id,
            exc,
            exc_info=True,
        )
        return {"success": False, "error": f"Unexpected error: {exc}"}
