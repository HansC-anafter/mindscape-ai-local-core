"""Artifact event and marker helpers."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Dict, Optional

from backend.app.services.conversation.task_manager_core.artifact_storage import (
    artifact_type_value,
)
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


async def create_artifact_mind_event(
    *,
    store: Any,
    artifact: Any,
    task: Any,
    execution_result: Dict[str, Any],
    utc_now_fn: Callable[[], Any] = utc_now,
) -> None:
    """Create the unified MindEvent record for a new artifact."""
    del execution_result

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
                "artifact_type": artifact_type_value(artifact),
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
                "artifact_type": artifact_type_value(artifact),
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
        if hasattr(artifacts_store, "list_latest_artifacts_by_playbook_type"):
            artifacts = artifacts_store.list_latest_artifacts_by_playbook_type(
                workspace_id, playbook_code, artifact_type
            )
        elif hasattr(artifacts_store, "list_artifacts_by_playbook_type"):
            artifacts = artifacts_store.list_artifacts_by_playbook_type(
                workspace_id, playbook_code, artifact_type
            )
        else:
            artifacts = artifacts_store.list_artifacts_by_playbook(
                workspace_id, playbook_code
            )
        same_type_artifacts = [
            artifact
            for artifact in artifacts
            if artifact_type_value(artifact) == artifact_type
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
