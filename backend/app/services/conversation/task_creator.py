"""
Task Creator

Creates and manages task instances for playbook executions.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

from ...models.workspace import Task, TaskStatus
from ...core.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


class TaskCreator:
    """
    Creates and manages task instances

    Responsibilities:
    - Create task instances for playbook executions
    - Check for existing tasks to avoid duplicates
    - Handle task creation with execution context
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

        # Create new task
        task = Task(
            id=str(uuid.uuid4()) if not execution_id else execution_id,
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
