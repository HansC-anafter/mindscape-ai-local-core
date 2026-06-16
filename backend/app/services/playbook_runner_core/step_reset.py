"""Step reset orchestration for the playbook runner facade."""

import logging
from typing import Any, Dict

from backend.app.services.playbook_runner_core.session_state import (
    get_or_restore_conversation_manager,
)

logger = logging.getLogger(__name__)


async def reset_current_step(
    runner: Any,
    *,
    execution_id: str,
    profile_id: str = "default-user",
) -> Dict[str, Any]:
    """Reset current step to restart from the beginning of current step."""
    try:
        from backend.app.models.mindscape import EventType
        from backend.app.models.workspace import TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore

        conv_manager = await get_or_restore_conversation_manager(
            execution_id=execution_id,
            active_conversations=runner.active_conversations,
            restore_execution_state_fn=lambda execution_id: runner.state_store.restore_execution_state(
                execution_id,
                runner.playbook_service,
            ),
        )

        tasks_store = TasksStore()
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            raise ValueError(f"Task not found for execution_id: {execution_id}")

        execution_context = task.execution_context or {}
        sandbox_id = execution_context.get("sandbox_id")

        original_step = conv_manager.current_step
        target_step = (
            max(0, conv_manager.current_step - 1)
            if conv_manager.current_step > 0
            else 0
        )

        workspace_id = conv_manager.workspace_id
        if workspace_id:
            try:
                step_index_1based = original_step + 1
                existing_events = runner.store.get_events_by_workspace(
                    workspace_id=workspace_id,
                    limit=200,
                )
                current_step_event = None
                for event in existing_events:
                    if (
                        event.event_type == EventType.PLAYBOOK_STEP
                        and isinstance(event.payload, dict)
                        and event.payload.get("execution_id") == execution_id
                        and event.payload.get("step_index") == step_index_1based
                    ):
                        current_step_event = event
                        break

                if current_step_event and isinstance(current_step_event.payload, dict):
                    updated_payload = current_step_event.payload.copy()
                    if updated_payload.get("status") == "completed":
                        updated_payload["status"] = "running"
                        updated_payload["completed_at"] = None
                        runner.store.update_event(
                            event_id=current_step_event.id,
                            payload=updated_payload,
                        )
                        logger.info(
                            f"Updated step event {current_step_event.id} status from 'completed' to 'running'"
                        )
            except Exception as exc:
                logger.warning(f"Failed to update step event status: {exc}")

        if len(conv_manager.conversation_history) > 5:
            kept_messages = conv_manager.conversation_history[:3]
            for msg in conv_manager.conversation_history[3:-2]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user" or (
                    role == "system" and "tool_call_result" not in content
                ):
                    kept_messages.append(msg)
            kept_messages.extend(conv_manager.conversation_history[-2:])
            conv_manager.conversation_history = kept_messages
        else:
            filtered_history = []
            for msg in conv_manager.conversation_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user" or (
                    role == "system" and "tool_call_result" not in content
                ):
                    filtered_history.append(msg)
            conv_manager.conversation_history = filtered_history

        conv_manager.current_step = target_step

        logger.info(
            f"Reset execution {execution_id} step from {original_step} to {conv_manager.current_step}, conversation history length: {len(conv_manager.conversation_history)}"
        )

        await runner.state_store.save_execution_state(execution_id, conv_manager)

        if sandbox_id:
            execution_context["sandbox_id"] = sandbox_id
            tasks_store.update_task(task.id, execution_context=execution_context)
            logger.info(f"Preserved sandbox_id={sandbox_id} in execution_context")

        if sandbox_id:
            runner.tool_executor.execution_context["sandbox_id"] = sandbox_id
            runner.tool_executor.execution_context["workspace_id"] = workspace_id
            logger.debug(
                f"Restored sandbox_id={sandbox_id} to tool_executor execution_context"
            )

        try:
            if task.status == TaskStatus.SUCCEEDED:
                tasks_store.update_task_status(task.id, TaskStatus.RUNNING)
                logger.info(
                    f"Updated task {task.id} status from SUCCEEDED to RUNNING after step reset"
                )
        except Exception as exc:
            logger.warning(f"Failed to update task status after step reset: {exc}")

        return {
            "execution_id": execution_id,
            "current_step": conv_manager.current_step,
            "previous_step": original_step,
            "conversation_history_length": len(conv_manager.conversation_history),
            "sandbox_id_preserved": sandbox_id is not None,
            "tool_calls_preserved": True,
            "step_event_updated": True,
            "message": f"Step reset from {original_step} to {conv_manager.current_step}. Ready to restart current step. Tool call records preserved in database.",
        }

    except ValueError as exc:
        logger.error(f"Failed to reset step: {exc}")
        raise
    except Exception as exc:
        logger.error(f"Failed to reset current step: {exc}", exc_info=True)
        raise
