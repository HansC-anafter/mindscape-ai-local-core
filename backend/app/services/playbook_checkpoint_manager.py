"""
PlaybookCheckpointManager - manages checkpoint creation and resume functionality

Provides checkpoint/resume capabilities for long-running playbook executions,
enabling Claude-style persistent execution across sessions.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from backend.app.services.stores.playbook_executions_store import PlaybookExecutionsStore
from backend.app.models.workspace import ExecutionSession

logger = logging.getLogger(__name__)


class PlaybookCheckpointManager:
    """
    Manages checkpoint creation and resume functionality for playbook executions

    Checkpoints capture the complete execution state including:
    - Current step index and execution context
    - Variable values and intermediate results
    - Tool call results and responses
    - Phase summaries and artifacts
    """

    def __init__(self, executions_store: PlaybookExecutionsStore):
        """
        Initialize checkpoint manager

        Args:
            executions_store: Store for playbook executions
        """
        self.executions_store = executions_store

    def create_checkpoint(self, execution_session: ExecutionSession) -> str:
        """
        Create a checkpoint of the current execution state

        Captures all necessary state to resume execution from this point.

        Args:
            execution_session: Current execution session

        Returns:
            Checkpoint ID
        """
        checkpoint_data = {
            "execution_id": execution_session.execution_id,
            "workspace_id": execution_session.workspace_id,
            "playbook_code": execution_session.playbook_code,
            "current_step_index": execution_session.current_step_index,
            "total_steps": execution_session.total_steps,
            "execution_context": execution_session.task.execution_context or {},
            "phase_summaries": execution_session.phase_summaries,
            "paused_at": execution_session.paused_at.isoformat() if execution_session.paused_at else None,
            "origin_intent_id": execution_session.origin_intent_id,
            "intent_confidence": execution_session.intent_confidence,
            "failure_type": execution_session.failure_type,
            "failure_reason": execution_session.failure_reason,
            "default_cluster": execution_session.default_cluster,
            "supports_resume": execution_session.supports_resume,
            "created_at": datetime.utcnow().isoformat()
        }

        import json
        checkpoint_json = json.dumps(checkpoint_data, ensure_ascii=False)

        # Update execution record with checkpoint
        success = self.executions_store.update_checkpoint(
            execution_id=execution_session.execution_id,
            checkpoint_data=checkpoint_json,
            phase=getattr(execution_session, 'phase', None)
        )

        if not success:
            raise ValueError(f"Failed to update checkpoint for execution {execution_session.execution_id}")

        checkpoint_id = f"checkpoint_{execution_session.execution_id}_{int(datetime.utcnow().timestamp())}"
        logger.info(f"Created checkpoint: {checkpoint_id} for execution: {execution_session.execution_id}")

        return checkpoint_id

    def resume_from_checkpoint(self, execution_id: str) -> Optional[ExecutionSession]:
        """
        Resume execution from the last checkpoint

        Args:
            execution_id: Execution ID to resume

        Returns:
            ExecutionSession restored from checkpoint, or None if no checkpoint found
        """
        execution = self.executions_store.get_execution(execution_id)
        if not execution or not execution.last_checkpoint:
            logger.warning(f"No checkpoint found for execution: {execution_id}")
            return None

        import json
        try:
            checkpoint_data = json.loads(execution.last_checkpoint)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid checkpoint data for execution {execution_id}: {e}")
            return None

        # Validate checkpoint data
        if not self._validate_checkpoint_data(checkpoint_data):
            logger.error(f"Invalid checkpoint structure for execution {execution_id}")
            return None

        # Reconstruct Task from checkpoint
        from backend.app.models.workspace import Task, TaskStatus

        task = Task(
            id=checkpoint_data["execution_id"],
            workspace_id=checkpoint_data["workspace_id"],
            message_id="",  # Will be set by caller
            execution_id=checkpoint_data["execution_id"],
            pack_id="",  # Will be set by caller
            task_type="playbook_execution",
            status=TaskStatus.RUNNING,  # Resuming
            params={"playbook_code": checkpoint_data["playbook_code"]},
            result=None,
            execution_context={
                "playbook_code": checkpoint_data["playbook_code"],
                "current_step_index": checkpoint_data["current_step_index"],
                "total_steps": checkpoint_data["total_steps"],
                "paused_at": checkpoint_data.get("paused_at"),
                "origin_intent_id": checkpoint_data.get("origin_intent_id"),
                "intent_confidence": checkpoint_data.get("intent_confidence"),
                "failure_type": checkpoint_data.get("failure_type"),
                "failure_reason": checkpoint_data.get("failure_reason"),
                "default_cluster": checkpoint_data.get("default_cluster"),
                "last_checkpoint": checkpoint_data,
                "phase_summaries": checkpoint_data.get("phase_summaries", []),
                "supports_resume": checkpoint_data.get("supports_resume", True)
            },
            created_at=datetime.utcnow(),  # Will be overridden by actual creation time
            started_at=datetime.utcnow(),
            completed_at=None,
            error=None,
            notification_sent_at=None,
            displayed_at=None
        )

        # Create ExecutionSession from task and checkpoint data
        execution_session = ExecutionSession.from_task(task)
        execution_session.paused_at = (
            datetime.fromisoformat(checkpoint_data["paused_at"]) if checkpoint_data.get("paused_at") else None
        )

        logger.info(f"Resumed execution from checkpoint: {execution_id}")
        return execution_session

    def _validate_checkpoint_data(self, checkpoint_data: Dict[str, Any]) -> bool:
        """
        Validate checkpoint data structure

        Args:
            checkpoint_data: Checkpoint data to validate

        Returns:
            True if valid, False otherwise
        """
        required_fields = [
            "execution_id", "workspace_id", "playbook_code",
            "current_step_index", "total_steps", "execution_context"
        ]

        for field in required_fields:
            if field not in checkpoint_data:
                logger.error(f"Missing required checkpoint field: {field}")
                return False

        # Validate data types
        if not isinstance(checkpoint_data["current_step_index"], int):
            logger.error("current_step_index must be integer")
            return False

        if not isinstance(checkpoint_data["total_steps"], int):
            logger.error("total_steps must be integer")
            return False

        return True

    def list_checkpoints(self, execution_id: str) -> list:
        """
        List all checkpoints for an execution

        Note: Current implementation only tracks the last checkpoint.
        Future enhancement could store checkpoint history.

        Args:
            execution_id: Execution ID

        Returns:
            List of checkpoint info (currently only the latest)
        """
        execution = self.executions_store.get_execution(execution_id)
        if not execution or not execution.last_checkpoint:
            return []

        import json
        try:
            checkpoint_data = json.loads(execution.last_checkpoint)
            return [{
                "checkpoint_id": f"checkpoint_{execution_id}_{checkpoint_data.get('created_at', 'latest')}",
                "created_at": checkpoint_data.get("created_at"),
                "step_index": checkpoint_data.get("current_step_index"),
                "phase": checkpoint_data.get("phase")
            }]
        except (json.JSONDecodeError, KeyError):
            return []
