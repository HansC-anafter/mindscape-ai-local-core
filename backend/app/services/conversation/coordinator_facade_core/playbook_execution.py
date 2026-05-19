"""Playbook execution helpers for CoordinatorFacade."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace import SideEffectLevel
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter
from backend.app.services.i18n_service import get_i18n_service

logger = logging.getLogger(__name__)


def utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


async def execute_playbook(
    *,
    facade: Any,
    playbook_code: str,
    playbook_context: Dict[str, Any],
    workspace_id: str,
    profile_id: str,
    message_id: str,
    project_id: Optional[str],
) -> Dict[str, Any]:
    """Execute a playbook by building the local domain context."""
    ctx = LocalDomainContext(
        actor_id=profile_id,
        workspace_id=workspace_id,
        tags={"mode": "local"},
    )
    return await facade.create_execution_with_ctx(
        playbook_code=playbook_code,
        playbook_context=playbook_context,
        ctx=ctx,
        message_id=message_id,
        project_id=project_id,
    )


async def create_execution_with_ctx(
    *,
    facade: Any,
    playbook_code: str,
    playbook_context: Dict[str, Any],
    ctx: LocalDomainContext,
    message_id: str,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create execution based on side effect level and suggestion confirmation."""
    side_effect_level = facade.plan_builder.determine_side_effect_level(playbook_code)
    from_suggestion_action = playbook_context.get("from_suggestion_action", False)

    logger.info(
        "CoordinatorFacade.create_execution_with_ctx: playbook=%s, side_effect_level=%s, from_suggestion_action=%s",
        playbook_code,
        side_effect_level,
        from_suggestion_action,
    )

    event_emitter = TaskEventsEmitter()

    if from_suggestion_action:
        logger.info(
            "CoordinatorFacade: Executing playbook %s directly (user confirmed from suggestion)",
            playbook_code,
        )
        result = await facade._execute_readonly_playbook(
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            ctx=ctx,
            message_id=message_id,
            project_id=project_id,
            event_emitter=event_emitter,
        )
        return {
            "status": "started",
            "execution_id": result.get("execution_id"),
            "task_id": result.get("task_id"),
        }

    if side_effect_level == SideEffectLevel.READONLY:
        logger.info(
            "CoordinatorFacade: Executing READONLY playbook %s directly",
            playbook_code,
        )
        result = await facade._execute_readonly_playbook(
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            ctx=ctx,
            message_id=message_id,
            project_id=project_id,
            event_emitter=event_emitter,
        )
        return {
            "status": "started",
            "execution_id": result.get("execution_id"),
            "task_id": result.get("task_id"),
        }

    logger.info(
        "CoordinatorFacade: Creating suggestion card for %s playbook %s",
        side_effect_level,
        playbook_code,
    )
    result = await facade.suggestion_card_creator.create_playbook_suggestion(
        playbook_code=playbook_code,
        playbook_context=playbook_context,
        workspace_id=ctx.workspace_id,
        message_id=message_id,
        event_emitter=event_emitter,
    )
    return {
        "status": "suggestion",
        "task_id": result.get("task_id"),
    }


async def execute_readonly_playbook(
    *,
    facade: Any,
    playbook_code: str,
    playbook_context: Dict[str, Any],
    ctx: LocalDomainContext,
    message_id: str,
    project_id: Optional[str],
    event_emitter: TaskEventsEmitter,
) -> Dict[str, Any]:
    """Execute a readonly playbook and emit the assistant response event."""
    try:
        playbook_inputs = playbook_context.copy()
        playbook_inputs["workspace_id"] = ctx.workspace_id

        project_meta = None
        if project_id:
            project_meta = await facade.plan_preparer._load_project_meta(
                project_id,
                ctx.workspace_id,
            )
            if project_meta:
                playbook_inputs = facade.execution_launcher._ensure_project_metadata(
                    playbook_inputs,
                    project_meta,
                )

        launch_result = await facade.execution_launcher.launch(
            playbook_code=playbook_code,
            inputs=playbook_inputs,
            ctx=ctx,
            project_meta=project_meta,
            project_id=project_id,
        )

        execution_result = launch_result.get("raw_result")
        execution_id = launch_result.get("execution_id")
        execution_mode = launch_result.get("execution_mode", "conversation")

        if not execution_id:
            facade.error_policy.handle_missing_execution_id(
                playbook_code,
                execution_result,
            )

        i18n = get_i18n_service(default_locale=facade.default_locale)

        if execution_mode == "workflow":
            assistant_response = i18n.t(
                "conversation_orchestrator",
                "workflow.started",
                playbook_code=playbook_code,
                default=f"Started workflow execution for {playbook_code}",
            )
        else:
            assistant_response = execution_result.get("result", {}).get(
                "message",
                i18n.t(
                    "conversation_orchestrator",
                    "workflow.started",
                    playbook_code=playbook_code,
                    default=f"Started execution for {playbook_code}",
                ),
            )

        assistant_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=utc_now(),
            actor=EventActor.ASSISTANT,
            channel="local_workspace",
            profile_id=ctx.actor_id,
            project_id=project_id,
            workspace_id=ctx.workspace_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": assistant_response,
                "response_to": message_id,
                "playbook_code": playbook_code,
            },
            entity_ids=[],
            metadata={},
        )
        facade.store.create_event(assistant_event)

        task = await facade.task_creator.create_or_get_task(
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            ctx=ctx,
            message_id=message_id,
            execution_id=execution_id,
            execution_result=execution_result,
            execution_mode=execution_mode,
        )

        event_emitter.emit_task_created(
            task_id=task.id,
            pack_id=playbook_code,
            status=(
                task.status.value if hasattr(task.status, "value") else str(task.status)
            ),
            task_type=task.task_type,
            workspace_id=ctx.workspace_id,
        )

        await facade.task_manager.check_and_update_task_status(
            task=task,
            execution_id=execution_id,
            playbook_code=playbook_code,
        )

        return {
            "status": "started",
            "playbook_code": playbook_code,
            "execution_id": execution_id,
            "task_id": task.id,
            "message": assistant_response,
        }
    except Exception as exc:
        facade.error_policy.handle_execution_error(f"start playbook {playbook_code}", exc)
        i18n = get_i18n_service(default_locale=facade.default_locale)
        return {
            "status": "failed",
            "playbook_code": playbook_code,
            "error": str(exc),
            "message": i18n.t(
                "conversation_orchestrator",
                "workflow.failed",
                playbook_code=playbook_code,
                error=str(exc),
            ),
        }
