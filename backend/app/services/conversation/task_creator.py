"""
Task Creator

Creates and manages task instances for playbook executions.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

from ...core.domain_context import LocalDomainContext
from ...models.workspace import Task, TaskStatus
from ...services.stores.graph_changelog_store import GraphChangelogStore

logger = logging.getLogger(__name__)


class TaskCreator:
    """
    Creates and manages task instances

    Responsibilities:
    - Create task instances for playbook executions
    - Check for existing tasks to avoid duplicates
    - Handle task creation with execution context
    - Create planned graph nodes for visual tracking
    """

    def __init__(self, tasks_store, execution_context_builder):
        """
        Initialize TaskCreator

        Args:
            tasks_store: TasksStore instance
            execution_context_builder: ExecutionContextBuilder instance
        """
        self.tasks_store = tasks_store
        self.execution_context_builder = execution_context_builder

    async def create_or_get_task(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        ctx: LocalDomainContext,
        message_id: str,
        execution_id: Optional[str],
        execution_result: Optional[Dict[str, Any]] = None,
        execution_mode: str = "conversation",
    ) -> Task:
        """
        Create or get existing task for playbook execution

        Args:
            playbook_code: Playbook code
            playbook_context: Playbook context
            ctx: Execution context
            message_id: Message ID
            execution_id: Optional execution ID
            execution_result: Optional execution result
            execution_mode: Execution mode

        Returns:
            Task instance
        """
        # Check if task already exists (created by PlaybookService)
        existing_task = None
        if execution_id:
            existing_task = self.tasks_store.get_task(execution_id)

        if existing_task:
            logger.info(
                f"TaskCreator: Task {existing_task.id} already exists, skipping creation"
            )
            return existing_task

        # Build execution context
        execution_context = await self.execution_context_builder.build(
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            ctx=ctx,
            execution_result=execution_result,
            execution_mode=execution_mode,
        )

        # Generate task ID
        task_id = str(uuid.uuid4()) if not execution_id else execution_id

        # Create planned graph node (dashed line visualization)
        pending_graph_node_id = await self._create_planned_graph_node(
            task_id=task_id,
            workspace_id=ctx.workspace_id,
            playbook_code=playbook_code,
            execution_context=execution_context,
        )

        # Add pending_graph_node_id to execution_context for later update
        if pending_graph_node_id:
            execution_context["pending_graph_node_id"] = pending_graph_node_id

        # Create new task
        task = Task(
            id=task_id,
            workspace_id=ctx.workspace_id,
            message_id=message_id,
            execution_id=execution_id or str(uuid.uuid4()),
            pack_id=playbook_code,
            task_type="playbook_execution",
            status=TaskStatus.RUNNING,
            params={
                "playbook_code": playbook_code,
                "context": playbook_context,
            },
            result=None,
            execution_context=execution_context,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            completed_at=None,
            error=None,
        )

        self.tasks_store.create_task(task)
        logger.info(f"TaskCreator: Created task {task.id} for playbook {playbook_code}")

        return task

    async def _create_planned_graph_node(
        self,
        task_id: str,
        workspace_id: str,
        playbook_code: str,
        execution_context: Dict[str, Any],
    ) -> Optional[str]:
        """
        Create a planned (dashed) graph node for the task.

        This implements the "draw dashed line first" pattern:
        - Node is created with status="planned" when task starts
        - Node will be updated to status="completed" when task succeeds
        - Node will be updated to status="cancelled" if task is cancelled

        Args:
            task_id: Task ID
            workspace_id: Workspace ID
            playbook_code: Playbook code
            execution_context: Execution context with Intent/Lens bindings

        Returns:
            Pending change ID (for later update) or None if creation failed
        """
        try:
            # Extract Intent/Lens bindings from execution context
            origin_intent_id = execution_context.get("origin_intent_id")
            origin_intent_label = execution_context.get("origin_intent_label")
            intent_confidence = execution_context.get("intent_confidence")
            lens_snapshot_hash = execution_context.get("effective_lens_hash")

            graph_store = GraphChangelogStore()
            change_id = graph_store.create_pending_change(
                workspace_id=workspace_id,
                operation="create_node",
                target_type="node",  # Must be: node, edge, overlay, or batch
                target_id=task_id,
                after_state={
                    "id": task_id,
                    "node_type": "task",  # Distinguishes from intent/lens nodes
                    "label": playbook_code,
                    "status": "planned",  # Dashed line visualization
                    "metadata": {
                        "playbook_code": playbook_code,
                        "task_id": task_id,
                        # Intent binding (retrospective)
                        "origin_intent_id": origin_intent_id,
                        "origin_intent_label": origin_intent_label,
                        "intent_confidence": intent_confidence,
                        # Lens binding (retrospective)
                        "lens_snapshot_hash": lens_snapshot_hash,
                        # Lifecycle
                        "planned_at": datetime.utcnow().isoformat(),
                    },
                    "created_at": datetime.utcnow().isoformat(),
                },
                actor="system",
                actor_context="task_creation",
            )

            logger.info(
                f"TaskCreator: Created planned graph node {change_id} for task {task_id}"
            )
            return change_id

        except Exception as e:
            # Graph node creation is non-critical
            logger.warning(
                f"TaskCreator: Failed to create planned graph node for task {task_id}: {e}",
                exc_info=True,
            )
            return None
