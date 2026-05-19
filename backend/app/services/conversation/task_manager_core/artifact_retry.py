"""Artifact retry flow for timeline items."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from backend.app.services.conversation.task_manager_core.artifact_events import (
    resolve_task_intent_id,
)
from backend.app.services.conversation.task_manager_core.artifact_storage import (
    artifact_type_value,
    artifact_write_failed_warning,
    persist_timeline_item_data,
    prepare_workspace_storage,
    set_pending_sync_state_if_enabled,
)

logger = logging.getLogger(__name__)


def warning_to_retry_response(warning: Dict[str, Any]) -> Dict[str, Any]:
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
        workspace, artifact_warning = await prepare_workspace_storage(
            store=store,
            workspace_id=timeline_item.workspace_id,
        )
        if artifact_warning:
            return warning_to_retry_response(artifact_warning)

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
            return warning_to_retry_response(artifact_write_failed_warning(artifact))

        artifact.metadata = artifact.metadata or {}
        artifact.metadata["version"] = artifact_extractor._get_next_version(
            workspace_id=timeline_item.workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type_value(artifact),
        )
        artifact.metadata["is_latest"] = True

        if workspace is not None:
            set_pending_sync_state_if_enabled(artifact, workspace)

        artifact = artifacts_store.create_artifact(artifact)
        logger.info(
            "Retry created artifact: %s for timeline item %s",
            artifact.id,
            timeline_item_id,
        )

        update_latest_markers_fn(
            workspace_id=timeline_item.workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type_value(artifact),
            new_artifact_id=artifact.id,
        )
        persist_timeline_item_data(
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
