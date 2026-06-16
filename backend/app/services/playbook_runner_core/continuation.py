"""Continuation orchestration for the playbook runner facade."""

import logging
import uuid
from typing import Any, Dict

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.services.execution_core.clock import utc_now as _utc_now
from backend.app.services.playbook_runner_core.execution_runtime import (
    get_llm_provider,
    load_and_apply_executor_route_context,
    run_playbook_assistant_turn,
)
from backend.app.services.playbook_runner_core.session_state import (
    get_or_restore_conversation_manager,
)

logger = logging.getLogger(__name__)


async def continue_playbook_execution(
    runner: Any,
    *,
    execution_id: str,
    user_message: str,
    profile_id: str = "default-user",
) -> Dict[str, Any]:
    """Continue an ongoing playbook execution through the runner facade."""
    try:
        conv_manager = await get_or_restore_conversation_manager(
            execution_id=execution_id,
            active_conversations=runner.active_conversations,
            restore_execution_state_fn=lambda execution_id: runner.state_store.restore_execution_state(
                execution_id,
                runner.playbook_service,
            ),
        )

        conv_manager.add_user_message(user_message)

        try:
            project_id = (
                getattr(conv_manager.project, "id", None)
                if conv_manager.project
                else None
            )
            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
                actor=EventActor.USER,
                channel="playbook",
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=conv_manager.workspace_id,
                event_type=EventType.MESSAGE,
                payload={
                    "execution_id": execution_id,
                    "playbook_code": (
                        conv_manager.playbook.metadata.playbook_code
                        if conv_manager.playbook
                        else None
                    ),
                    "message": user_message[:500],
                    "role": "user",
                },
                entity_ids=[project_id] if project_id else [],
                metadata={},
            )
            runner.store.create_event(event)
        except Exception as exc:
            logger.warning(f"Failed to record user message event: {exc}")

        provider = get_llm_provider(runner, profile_id)
        workspace_id = conv_manager.workspace_id
        route_context = await load_and_apply_executor_route_context(
            runner,
            conv_manager,
            workspace_id,
            reuse_existing=True,
        )
        sandbox_id_from_context = getattr(conv_manager, "sandbox_id", None)
        max_iterations = 15 if conv_manager.auto_execute else 5
        assistant_response, used_tools = await run_playbook_assistant_turn(
            runner=runner,
            conv_manager=conv_manager,
            execution_id=execution_id,
            profile_id=profile_id,
            provider=provider,
            route_context=route_context,
            purpose="playbook_runner.continue",
            workspace_id=workspace_id,
            sandbox_id=sandbox_id_from_context,
            max_iterations=max_iterations,
        )

        structured_output = conv_manager.extract_structured_output(assistant_response)
        is_complete = structured_output is not None

        project_id = (
            getattr(conv_manager.project, "id", None) if conv_manager.project else None
        )
        playbook_code = (
            conv_manager.playbook.metadata.playbook_code
            if conv_manager.playbook
            else None
        )
        workspace_id = conv_manager.workspace_id

        step_event, total_steps = runner.step_recorder.record_continuation_step(
            execution_id=execution_id,
            profile_id=profile_id,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            conv_manager=conv_manager,
            assistant_response=assistant_response,
            used_tools=used_tools,
            project_id=project_id,
        )

        if is_complete and structured_output and step_event:
            runner.step_recorder.finalize_step_with_output(
                step_event=step_event,
                execution_id=execution_id,
                structured_output=structured_output,
            )

        if is_complete:
            conv_manager.extracted_data = structured_output
            runner.task_manager.update_task_status_to_succeeded(
                execution_id=execution_id,
                structured_output=structured_output,
            )
            runner.cleanup_execution(execution_id)
            logger.info(f"Cleaned up execution {execution_id} from active_conversations")

        if is_complete:
            try:
                profile = conv_manager.profile
                playbook = conv_manager.playbook
                playbook_code = playbook.metadata.playbook_code if playbook else None

                tool_name = "habit_learning.observe_playbook_execution"
                try:
                    await runner._run_tool(
                        tool_name,
                        profile_id=profile_id,
                        playbook_code=playbook_code,
                        execution_data={
                            "execution_id": execution_id,
                            "conversation_length": len(
                                conv_manager.conversation_history
                            ),
                        },
                        project_id=(
                            getattr(conv_manager.project, "id", None)
                            if conv_manager.project
                            else None
                        ),
                    )
                except ValueError as exc:
                    logger.warning(
                        f"Tool {tool_name} not found in capability registry: {exc}"
                    )
            except Exception as exc:
                logger.warning(
                    f"Failed to observe habits from playbook execution: {exc}"
                )

        await runner.state_store.save_execution_state(execution_id, conv_manager)

        result = {
            "execution_id": execution_id,
            "message": assistant_response,
            "is_complete": is_complete,
            "structured_output": structured_output,
            "conversation_history": conv_manager.conversation_history,
        }

        execution_state = await runner.state_store.get_execution_state(execution_id)
        if execution_state and execution_state.get("inputs"):
            thread_id = execution_state["inputs"].get("thread_id")
            if thread_id:
                try:
                    await runner.context_injector.extract_context_updates(
                        execution_id=execution_id,
                        thread_id=thread_id,
                        execution_result=result,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Failed to extract Story Thread context updates: {exc}",
                        exc_info=True,
                    )

        return result

    except Exception as exc:
        logger.error(f"Failed to continue playbook execution: {exc}")
        raise
