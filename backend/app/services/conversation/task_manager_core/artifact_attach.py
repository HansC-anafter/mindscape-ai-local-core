"""Artifact attach flow for completed task timeline items."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

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
        workspace, artifact_warning = await prepare_workspace_storage(
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
                artifact_warning = artifact_write_failed_warning(artifact)

        if artifact:
            artifact.metadata = artifact.metadata or {}
            artifact.metadata["version"] = get_next_version_fn(
                workspace_id=task.workspace_id,
                playbook_code=playbook_code,
                artifact_type=artifact_type_value(artifact),
            )
            artifact.metadata["is_latest"] = True

            if workspace is not None:
                set_pending_sync_state_if_enabled(artifact, workspace)

            artifact = artifacts_store.create_artifact(artifact)
            logger.info("Created artifact: %s for task %s", artifact.id, task.id)

            update_latest_markers_fn(
                workspace_id=task.workspace_id,
                playbook_code=playbook_code,
                artifact_type=artifact_type_value(artifact),
                new_artifact_id=artifact.id,
            )
            persist_timeline_item_data(
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
            persist_timeline_item_data(
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
        persist_timeline_item_data(
            timeline_items_store=timeline_items_store,
            timeline_item=timeline_item,
            warning={
                "type": "artifact_creation_error",
                "message": f"Unexpected error during artifact creation: {exc}",
                "action_required": "Please check logs and try again",
            },
        )
        return None
