"""Graph node completion helpers for TaskManager."""

from __future__ import annotations

import logging
from typing import Any, Dict

from backend.app.services.execution_core.clock import utc_now

logger = logging.getLogger(__name__)


async def create_graph_node_for_task(
    *,
    task: Any,
    timeline_item: Any,
    playbook_code: str,
    execution_result: Dict[str, Any],
) -> None:
    """Apply or create a completed task graph node."""
    del execution_result

    try:
        execution_context = {}
        if hasattr(task, "execution_context") and task.execution_context:
            execution_context = task.execution_context
        elif hasattr(task, "metadata") and task.metadata:
            execution_context = task.metadata.get("execution_context", {})

        pending_graph_node_id = execution_context.get("pending_graph_node_id")

        from backend.app.services.stores.graph_changelog_store import GraphChangelogStore

        graph_store = GraphChangelogStore()

        if pending_graph_node_id:
            try:
                result = graph_store.apply_change(
                    change_id=pending_graph_node_id,
                    applied_by="system:task_completion",
                )
                if result.get("success"):
                    logger.info(
                        "Applied graph node %s for completed task %s",
                        pending_graph_node_id,
                        task.id,
                    )
                    return

                logger.warning(
                    "Failed to apply graph node %s: %s",
                    pending_graph_node_id,
                    result.get("error"),
                )
            except Exception as exc:
                logger.warning("Error applying graph node: %s", exc)

        origin_intent_id = execution_context.get("origin_intent_id")
        origin_intent_label = execution_context.get("origin_intent_label")
        intent_confidence = execution_context.get("intent_confidence")
        lens_snapshot_hash = execution_context.get("effective_lens_hash")

        node_metadata = {
            "playbook_code": playbook_code,
            "timeline_item_id": timeline_item.id,
            "task_id": task.id,
            "message_id": task.message_id,
            "origin_intent_id": origin_intent_id,
            "origin_intent_label": origin_intent_label,
            "intent_confidence": intent_confidence,
            "lens_snapshot_hash": lens_snapshot_hash,
            "completed_at": (
                task.completed_at.isoformat()
                if hasattr(task, "completed_at") and task.completed_at
                else utc_now().isoformat()
            ),
            "timeline_item_type": (
                timeline_item.type.value
                if hasattr(timeline_item.type, "value")
                else str(timeline_item.type)
            ),
            "artifact_id": (
                timeline_item.data.get("artifact_id") if timeline_item.data else None
            ),
        }

        change_id = graph_store.create_pending_change(
            workspace_id=task.workspace_id,
            operation="create_node",
            target_type="node",
            target_id=task.id,
            after_state={
                "id": task.id,
                "node_type": "task",
                "label": timeline_item.title or playbook_code,
                "status": "completed",
                "metadata": node_metadata,
                "created_at": utc_now().isoformat(),
            },
            actor="system",
            actor_context="task_completion",
        )

        graph_store.apply_change(change_id, applied_by="system:auto_apply")

        logger.info(
            "Created and applied graph node for task %s (intent: %s, lens: %s)",
            task.id,
            origin_intent_id,
            lens_snapshot_hash,
        )
    except Exception as exc:
        logger.warning(
            "Failed to handle graph node for task %s: %s",
            task.id,
            exc,
            exc_info=True,
        )
