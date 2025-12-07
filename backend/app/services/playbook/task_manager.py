"""
Task Manager
Handles Task creation, status updates, and cleanup for playbook executions
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, Any

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)


class PlaybookTaskManager:
    """Manages Task records for playbook executions"""

    def __init__(self, store: Any):
        self.store = store
        self.tasks_store = TasksStore(db_path=store.db_path)

    def create_execution_task(
        self,
        execution_id: str,
        workspace_id: str,
        profile_id: str,
        playbook_code: str,
        playbook_name: str,
        inputs: Optional[Dict[str, Any]] = None,
        total_steps: int = 1
    ) -> bool:
        """
        Create Task record for execution session.

        Args:
            execution_id: Execution ID
            workspace_id: Workspace ID
            profile_id: Profile ID
            playbook_code: Playbook code
            playbook_name: Playbook name
            inputs: Optional execution inputs
            total_steps: Total number of steps

        Returns:
            True if task was created successfully, False otherwise
        """
        try:
            # Build execution_context for ExecutionSession
            execution_context = {
                "playbook_code": playbook_code,
                "playbook_name": playbook_name,
                "trigger_source": inputs.get("trigger_source", "manual") if inputs else "manual",
                "current_step_index": 0,
                "total_steps": total_steps,
                "origin_intent_id": inputs.get("origin_intent_id") if inputs else None,
                "origin_intent_label": inputs.get("origin_intent_label") if inputs else None,
                "intent_confidence": inputs.get("intent_confidence") if inputs else None,
                "origin_suggestion_id": inputs.get("origin_suggestion_id") if inputs else None,
            }

            # Create Task record with execution_id
            task = Task(
                id=execution_id,
                workspace_id=workspace_id,
                message_id=inputs.get("message_id", str(uuid.uuid4())) if inputs else str(uuid.uuid4()),
                execution_id=execution_id,
                profile_id=profile_id,
                pack_id=playbook_code,
                task_type="playbook_execution",
                status=TaskStatus.RUNNING,
                execution_context=execution_context,
                params=inputs or {},
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            self.tasks_store.create_task(task)
            logger.info(f"PlaybookTaskManager: Created execution task {execution_id} for playbook {playbook_code}, workspace_id={workspace_id}")
            return True
        except Exception as task_error:
            logger.warning(f"PlaybookTaskManager: Failed to create execution task for {playbook_code}: {task_error}", exc_info=True)
            return False

    def update_task_status_to_failed(
        self,
        execution_id: str,
        error: str
    ) -> bool:
        """Update task status to FAILED"""
        try:
            task = self.tasks_store.get_task_by_execution_id(execution_id)
            if task:
                self.tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error=error[:1000]
                )
                logger.info(f"PlaybookTaskManager: Updated execution task {execution_id} status to FAILED")
                return True
            return False
        except Exception as e:
            logger.warning(f"PlaybookTaskManager: Failed to update task status: {e}")
            return False

    def update_task_status_to_succeeded(
        self,
        execution_id: str,
        structured_output: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update task status to SUCCEEDED"""
        try:
            task = self.tasks_store.get_task_by_execution_id(execution_id)
            if task and task.status.value == 'running':
                # Update task status to SUCCEEDED
                self.tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.SUCCEEDED,
                    result={
                        "execution_id": execution_id,
                        "structured_output": structured_output,
                        "status": "completed"
                    },
                    completed_at=datetime.utcnow()
                )
                logger.info(f"PlaybookTaskManager: Updated task {task.id} status to SUCCEEDED for completed execution {execution_id}")
                return True
            return False
        except Exception as e:
            logger.warning(f"PlaybookTaskManager: Failed to update task status or cleanup execution: {e}")
            return False

