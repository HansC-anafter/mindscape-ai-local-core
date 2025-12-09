"""
Execution State Store
Handles saving and restoring execution state for Playbook runs
"""

import logging
from typing import Dict, Optional, Any

from backend.app.models.workspace import TaskStatus
from backend.app.models.mindscape import EventType
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)


class ExecutionStateStore:
    """Manages execution state persistence for Playbook runs"""

    def __init__(self, store: Any):
        self.store = store

    async def save_execution_state(
        self,
        execution_id: str,
        conv_manager: Any
    ):
        """Save execution state to database for persistence"""
        try:
            tasks_store = TasksStore(db_path=self.store.db_path)
            task = tasks_store.get_task_by_execution_id(execution_id)

            if task:
                execution_context = task.execution_context or {}
                conversation_state_dict = conv_manager.to_dict()
                execution_context["conversation_state"] = conversation_state_dict

                # Update current_step_index to match conv_manager.current_step
                # conv_manager.current_step is 0-based and represents the NEXT step to execute
                # current_step_index should be 0-based and represent the CURRENT completed step
                # So we need to subtract 1, but ensure it's not negative
                current_step_index_0based = max(0, conv_manager.current_step - 1)
                execution_context["current_step_index"] = current_step_index_0based

                # Calculate dynamic total_steps from existing step events
                try:
                    existing_events = self.store.get_events_by_workspace(
                        workspace_id=conv_manager.workspace_id,
                        limit=200
                    )
                    existing_steps = [
                        e for e in existing_events
                        if e.event_type == EventType.PLAYBOOK_STEP
                        and isinstance(e.payload, dict)
                        and e.payload.get('execution_id') == execution_id
                    ]
                    # Total steps is the maximum of current_step_index + 1 and number of existing steps
                    dynamic_total_steps = max(conv_manager.current_step + 1, len(existing_steps))
                    execution_context["total_steps"] = dynamic_total_steps
                except Exception as e:
                    logger.warning(f"Failed to calculate dynamic total_steps in save_execution_state: {e}")
                    # Keep existing total_steps if calculation fails
                    if "total_steps" not in execution_context:
                        execution_context["total_steps"] = conv_manager.current_step + 1

                tasks_store.update_task(task.id, execution_context=execution_context)
                logger.info(f"Saved execution state for {execution_id} to database (current_step={conv_manager.current_step}, current_step_index={current_step_index_0based}, total_steps={execution_context.get('total_steps')}, conversation_length={len(conversation_state_dict.get('conversation_history', []))})")
            else:
                logger.warning(f"Cannot save execution state: Task not found for execution_id {execution_id}")
        except Exception as e:
            logger.error(f"Failed to save execution state for {execution_id}: {e}", exc_info=True)

    async def restore_execution_state(
        self,
        execution_id: str,
        playbook_service: Any
    ) -> Optional[Any]:
        """Restore execution state from database"""
        try:
            tasks_store = TasksStore(db_path=self.store.db_path)
            task = tasks_store.get_task_by_execution_id(execution_id)

            if not task:
                logger.debug(f"Task not found for execution_id: {execution_id}")
                return None

            # Allow restore for RUNNING or SUCCEEDED tasks (to support conversational playbooks)
            # Conversational playbooks may complete initial LLM call but still need user interaction
            allowed_statuses = [TaskStatus.RUNNING, TaskStatus.SUCCEEDED]
            if task.status not in allowed_statuses:
                logger.debug(f"Task {task.id} status {task.status} not in allowed statuses {allowed_statuses}, cannot restore execution state")
                return None

            execution_context = task.execution_context or {}
            conversation_state = execution_context.get("conversation_state")

            if not conversation_state:
                logger.info(f"No conversation_state found in execution_context for {execution_id}. Available keys: {list(execution_context.keys())}")
                return None

            # Restore ConversationManager from saved state
            logger.info(f"Attempting to restore ConversationManager for execution {execution_id} from database")
            from backend.app.services.playbook.conversation_manager import PlaybookConversationManager
            conv_manager = await PlaybookConversationManager.from_dict(
                conversation_state,
                self.store,
                playbook_service
            )

            logger.info(f"Successfully restored ConversationManager for execution {execution_id} (conversation_length={len(conv_manager.conversation_history)})")

            # Reload tools list from cache if workspace_id is available
            if conv_manager.workspace_id:
                try:
                    from backend.app.services.tool_registry import ToolRegistryService
                    import os

                    data_dir = os.getenv("DATA_DIR", "./data")
                    tool_registry = ToolRegistryService(data_dir=data_dir)

                    profile_id_for_tools = conv_manager.profile.id if conv_manager.profile else None
                    if hasattr(tool_registry, 'get_tools_str_cached'):
                        cached_tools_str = tool_registry.get_tools_str_cached(
                            workspace_id=conv_manager.workspace_id,
                            profile_id=profile_id_for_tools,
                            enabled_only=True
                        )
                        conv_manager.cached_tools_str = cached_tools_str
                        logger.info(f"ExecutionStateStore: Reloaded cached tool list for workspace {conv_manager.workspace_id}")
                except Exception as e:
                    logger.warning(f"ExecutionStateStore: Failed to reload tools list during restore: {e}", exc_info=True)

            return conv_manager

        except Exception as e:
            logger.error(f"Failed to restore execution state for {execution_id}: {e}", exc_info=True)
            return None

    async def get_execution_state(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Get execution state (inputs and context) from database.

        Args:
            execution_id: Execution ID

        Returns:
            Dict with execution state including inputs, or None if not found
        """
        try:
            tasks_store = TasksStore(db_path=self.store.db_path)
            task = tasks_store.get_task_by_execution_id(execution_id)

            if not task:
                logger.debug(f"Task not found for execution_id: {execution_id}")
                return None

            execution_context = task.execution_context or {}

            # Extract inputs from params if available
            inputs = {}
            if task.params and isinstance(task.params, dict):
                if "context" in task.params:
                    context = task.params["context"]
                    if isinstance(context, dict):
                        inputs = context
                elif "inputs" in task.params:
                    inputs = task.params.get("inputs", {})

            return {
                "execution_id": execution_id,
                "inputs": inputs,
                "execution_context": execution_context,
                "status": task.status.value if task.status else None,
            }

        except Exception as e:
            logger.error(f"Failed to get execution state for {execution_id}: {e}", exc_info=True)
            return None

    def update_task_step_info(
        self,
        execution_id: str,
        step_index: int,
        total_steps: int,
        playbook_code: Optional[str] = None
    ):
        """
        Update Task's execution_context with current step information.
        This ensures ExecutionSession view model has correct current_step_index and total_steps.

        Args:
            execution_id: Execution ID
            step_index: Current step index (1-based)
            total_steps: Total number of steps
            playbook_code: Playbook code (optional)
        """
        try:
            tasks_store = TasksStore(db_path=self.store.db_path)
            task = tasks_store.get_task(execution_id)

            # Convert step_index from 1-based to 0-based for execution_context
            current_step_index_0based = step_index - 1

            if task and task.execution_context:
                execution_context = task.execution_context.copy()
                execution_context["current_step_index"] = current_step_index_0based
                execution_context["total_steps"] = total_steps
                if playbook_code:
                    execution_context["playbook_code"] = playbook_code
                tasks_store.update_task(execution_id, execution_context=execution_context)
                logger.info(f"ExecutionStateStore: Updated Task {execution_id} execution_context: current_step_index={current_step_index_0based}, total_steps={total_steps}")
            elif task:
                # Task exists but has no execution_context, create one
                execution_context = {
                    "playbook_code": playbook_code or "",
                    "current_step_index": current_step_index_0based,
                    "total_steps": total_steps,
                }
                tasks_store.update_task(execution_id, execution_context=execution_context)
                logger.info(f"ExecutionStateStore: Created execution_context for Task {execution_id}: current_step_index={current_step_index_0based}, total_steps={total_steps}")
        except Exception as e:
            logger.warning(f"ExecutionStateStore: Failed to update Task execution_context: {e}", exc_info=True)

