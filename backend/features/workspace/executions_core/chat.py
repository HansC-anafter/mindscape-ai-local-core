"""Execution chat helpers for workspace execution routes."""

import asyncio
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace import ExecutionChatMessage, ExecutionChatMessageType
from backend.app.services.conversation.execution_chat_agent_service import (
    handle_execution_chat_agent_turn,
)
from backend.app.services.conversation.execution_chat_config import (
    resolve_execution_chat_config,
)
from backend.app.services.conversation.execution_chat_service import (
    generate_execution_chat_reply,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.features.workspace.executions_core import ExecutionChatRequest


async def post_execution_chat_payload(
    *,
    workspace_id: str,
    execution_id: str,
    request: ExecutionChatRequest,
    profile_id: str,
    identity_port: Any,
    logger,
) -> dict:
    """Create a user execution chat message and schedule the response path."""
    try:
        store = MindscapeStore()

        ctx = await identity_port.get_current_context(
            workspace_id=workspace_id, profile_id=profile_id
        )

        try:
            msg_type = ExecutionChatMessageType(request.message_type)
        except ValueError:
            msg_type = ExecutionChatMessageType.QUESTION

        user_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.USER,
            channel="workspace",
            profile_id=ctx.actor_id,
            workspace_id=ctx.workspace_id,
            event_type=EventType.EXECUTION_CHAT,
            payload={
                "execution_id": execution_id,
                "step_id": request.step_id,
                "role": "user",
                "speaker": ctx.actor_id,
                "content": request.content,
                "message_type": msg_type.value,
            },
            entity_ids=[execution_id] + ([request.step_id] if request.step_id else []),
            metadata={"is_execution_chat": True},
        )

        store.create_event(user_event)

        user_message = ExecutionChatMessage.from_mind_event(user_event)
        user_message_dict = (
            user_message.model_dump(mode="json")
            if hasattr(user_message, "model_dump")
            else user_message
        )

        playbook_metadata = None
        should_continue_execution = False
        try:
            from backend.app.services.playbook_service import PlaybookService
            from backend.app.services.stores.tasks_store import TasksStore

            tasks_store = TasksStore(db_path=store.db_path)
            task = tasks_store.get_task_by_execution_id(execution_id)

            if task:
                task_status = (
                    task.status.value
                    if hasattr(task.status, "value")
                    else str(task.status)
                )
                execution_context = task.execution_context or {}
                paused_at = execution_context.get("paused_at")
                current_step = execution_context.get("current_step", {})
                step_status = (
                    current_step.get("status")
                    if isinstance(current_step, dict)
                    else None
                )
                step_requires_confirmation = (
                    current_step.get("requires_confirmation", False)
                    if isinstance(current_step, dict)
                    else False
                )
                step_confirmation_status = (
                    current_step.get("confirmation_status")
                    if isinstance(current_step, dict)
                    else None
                )

                should_continue_execution = (
                    task_status == "waiting_confirmation"
                    or task_status == "paused"
                    or paused_at is not None
                    or step_status == "waiting_confirmation"
                    or (
                        step_requires_confirmation
                        and step_confirmation_status == "pending"
                    )
                )

                logger.info(
                    f"Execution {execution_id} status check: task_status={task_status}, paused_at={paused_at}, step_status={step_status}, step_requires_confirmation={step_requires_confirmation}, step_confirmation_status={step_confirmation_status}, should_continue={should_continue_execution}"
                )

                if task.execution_context:
                    playbook_code = task.execution_context.get("playbook_code")
                    if playbook_code:
                        playbook_service = PlaybookService(store=store)
                        playbook = await playbook_service.get_playbook(
                            playbook_code=playbook_code,
                            locale=(
                                ctx.workspace.default_locale
                                if hasattr(ctx, "workspace") and ctx.workspace
                                else "zh-TW"
                            ),
                            workspace_id=ctx.workspace_id,
                        )
                        if playbook:
                            playbook_metadata = playbook.metadata
        except Exception as exc:
            logger.warning(
                f"Failed to load playbook metadata or check execution status: {exc}"
            )

        async def handle_execution_response():
            """Async task to either continue execution or generate chat reply."""
            try:
                chat_config = resolve_execution_chat_config(playbook_metadata)
                chat_mode = chat_config.mode

                if chat_mode == "agent":
                    logger.info(
                        f"Handling execution chat for {execution_id} via agent mode"
                    )
                    try:
                        await handle_execution_chat_agent_turn(
                            execution_id=execution_id,
                            ctx=ctx,
                            user_message=request.content,
                            user_message_id=user_event.id,
                            playbook_metadata=playbook_metadata,
                            profile_id=profile_id,
                        )
                    except Exception as exc:
                        logger.error(
                            f"Execution chat agent failed for {execution_id}: {exc}",
                            exc_info=True,
                        )
                        await generate_execution_chat_reply(
                            execution_id=execution_id,
                            ctx=ctx,
                            user_message=request.content,
                            user_message_id=user_event.id,
                            playbook_metadata=playbook_metadata,
                        )
                elif should_continue_execution:
                    logger.info(
                        f"Auto-continuing execution {execution_id} via execution chat"
                    )
                    from backend.app.services.playbook_runner import PlaybookRunner

                    playbook_runner = PlaybookRunner()

                    try:
                        result = await playbook_runner.continue_playbook_execution(
                            execution_id=execution_id,
                            user_message=request.content,
                            profile_id=profile_id,
                        )
                        logger.info(f"Successfully continued execution {execution_id}")
                    except Exception as exc:
                        logger.error(
                            f"Failed to continue execution {execution_id}: {exc}",
                            exc_info=True,
                        )
                        await generate_execution_chat_reply(
                            execution_id=execution_id,
                            ctx=ctx,
                            user_message=request.content,
                            user_message_id=user_event.id,
                            playbook_metadata=playbook_metadata,
                        )
                else:
                    logger.info(
                        f"Generating chat reply for execution {execution_id} (discussion mode)"
                    )
                    result = await generate_execution_chat_reply(
                        execution_id=execution_id,
                        ctx=ctx,
                        user_message=request.content,
                        user_message_id=user_event.id,
                        playbook_metadata=playbook_metadata,
                    )
                    logger.info(
                        f"Generated assistant reply for execution {execution_id}"
                    )
            except Exception as exc:
                logger.error(
                    f"Failed to handle execution response: {exc}", exc_info=True
                )

        asyncio.create_task(handle_execution_response())

        return {"message": user_message_dict, "status": "sent"}

    except Exception as exc:
        logger.error(f"Failed to post execution chat: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
