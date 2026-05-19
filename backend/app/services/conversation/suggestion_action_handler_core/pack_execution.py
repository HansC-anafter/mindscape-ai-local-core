"""execute_pack action helper for SuggestionActionHandler."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.services.capability_registry import get_registry
from .mindscape_actions import build_empty_action_response
from .pack_execution_methods import (
    execute_pack_executor,
    execute_playbook_method,
    execute_unknown_method,
    is_valid_result,
)

logger = logging.getLogger(__name__)


def _utc_now():
    return datetime.now(timezone.utc)


async def handle_execute_pack(
    handler: Any,
    *,
    ctx: LocalDomainContext,
    action_params: Dict[str, Any],
    project_id: Optional[str],
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle execute_pack action from a pending task."""
    task = None
    pack_id = None
    try:
        if not action_params:
            logger.error("action_params is None for execute_pack action")
            raise ValueError("action_params is required for execute_pack action")

        logger.info("_handle_execute_pack called with action_params: %s", action_params)

        pack_id = action_params.get("pack_id")
        task_id = action_params.get("task_id")

        if not pack_id:
            raise ValueError("pack_id is required for execute_pack action")
        if not handler.execution_coordinator:
            raise ValueError("execution_coordinator is required for execute_pack action")

        task = handler.task_manager.tasks_store.get_task(task_id) if task_id else None

        if task:
            original_message_id = task.message_id or message_id or str(uuid.uuid4())
            files = task.params.get("files", []) if task.params else []
            message = task.params.get("message", "") if task.params else ""

            from backend.app.models.workspace import TaskStatus

            try:
                handler.task_manager.tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.SUCCEEDED,
                    result={"action": "executed", "pack_id": pack_id},
                    completed_at=_utc_now(),
                )
            except Exception as exc:
                logger.warning("Failed to update suggestion task status: %s", exc)
        else:
            original_message_id = message_id or str(uuid.uuid4())
            files = action_params.get("files", [])
            message = action_params.get("message", "")

        executable_response = await _handle_executable_task_placeholder(
            handler=handler,
            ctx=ctx,
            task=task,
            pack_id=pack_id,
        )
        if executable_response is not None:
            return executable_response

        from backend.app.services.i18n_service import get_i18n_service

        i18n = get_i18n_service(default_locale=handler.default_locale)
        execute_message = i18n.t(
            "conversation_orchestrator",
            "error.execute_pack",
            pack_id=pack_id,
        )
        handler._create_user_event(
            ctx.workspace_id,
            ctx.actor_id,
            project_id,
            execute_message,
            "execute_pack",
            action_params,
        )

        result = None
        pack_id_lower = pack_id.lower() if pack_id else ""

        if pack_id_lower == "intent_extraction" and task:
            result = await _execute_intent_extraction(
                handler=handler,
                ctx=ctx,
                task=task,
                original_message_id=original_message_id,
            )
        else:
            result = await _execute_non_intent_pack(
                handler=handler,
                ctx=ctx,
                pack_id=pack_id,
                pack_id_lower=pack_id_lower,
                original_message_id=original_message_id,
                files=files,
                message=message,
                project_id=project_id,
                task=task,
                action_params=action_params,
            )

        if is_valid_result(result, pack_id_lower):
            logger.info("Successfully executed pack %s from pending task", pack_id)
        else:
            logger.error(
                "Pack %s execution failed - no valid result or only suggestion cards returned",
                pack_id,
            )
            raise ValueError(f"Pack {pack_id} execution failed: no valid result")

        return build_empty_action_response(ctx.workspace_id)
    except Exception as exc:
        error_message = f"Failed to execute pack {pack_id}: {str(exc)}"
        error_type = type(exc).__name__
        logger.error(error_message, exc_info=True)

        if task:
            from backend.app.models.workspace import TaskStatus

            try:
                handler.task_manager.tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error=error_message,
                    result={
                        "progress": "failed",
                        "progress_percentage": 0,
                        "error": error_message,
                        "error_type": error_type,
                        "pack_id": pack_id,
                    },
                    completed_at=_utc_now(),
                )
                logger.info(
                    "Updated task %s status to FAILED with error: %s",
                    task.id,
                    error_message,
                )
            except Exception as update_error:
                logger.error(
                    "Failed to update task %s status to FAILED: %s",
                    task.id,
                    update_error,
                    exc_info=True,
                )

        raise


async def _handle_executable_task_placeholder(
    *,
    handler: Any,
    ctx: LocalDomainContext,
    task: Optional[Any],
    pack_id: str,
) -> Optional[Dict[str, Any]]:
    if not pack_id.startswith("executable_task_") or not task:
        return None

    executable_task_text = task.result.get("executable_task") if task.result else None
    if not executable_task_text:
        executable_task_text = (
            task.params.get("executable_task") if task.params else None
        )

    if not executable_task_text:
        raise ValueError("executable_task text not found in task result or params")

    logger.info(
        "[SuggestionActionHandler] Re-analyzing intent for executable_task: %s",
        executable_task_text[:50],
    )
    try:
        from backend.features.workspace.chat.playbook.executor import (
            execute_playbook_for_hybrid_mode,
        )

        store = (
            handler.execution_coordinator.store
            if hasattr(handler.execution_coordinator, "store")
            else handler.store
        )
        if not store:
            raise ValueError("Store not available for re-analyzing intent")

        profile_id = ctx.actor_id
        profile = None
        if profile_id:
            try:
                profile = await store.get_profile(profile_id)
            except Exception as exc:
                logger.warning("Failed to get profile %s: %s", profile_id, exc)

        execution_result = await execute_playbook_for_hybrid_mode(
            message=executable_task_text,
            executable_tasks=[executable_task_text],
            workspace_id=ctx.workspace_id,
            profile_id=profile_id,
            profile=profile,
            store=store,
            files=None,
        )

        if execution_result:
            logger.info(
                "[SuggestionActionHandler] Playbook %s executed for executable_task",
                execution_result["playbook_code"],
            )
            return {
                "workspace_id": ctx.workspace_id,
                "display_events": [],
                "triggered_playbook": {
                    "playbook_code": execution_result["playbook_code"],
                    "execution_id": execution_result.get("execution_id"),
                    "status": "triggered",
                },
                "pending_tasks": [],
            }

        logger.warning(
            "[SuggestionActionHandler] No playbook found for executable_task: %s",
            executable_task_text[:50],
        )
        return {
            "workspace_id": ctx.workspace_id,
            "display_events": [],
            "triggered_playbook": None,
            "pending_tasks": [],
        }
    except Exception as exc:
        logger.error(
            "[SuggestionActionHandler] Failed to re-analyze intent for executable_task: %s",
            exc,
            exc_info=True,
        )
        raise ValueError(f"Failed to execute executable task: {str(exc)}") from exc


async def _execute_intent_extraction(
    *,
    handler: Any,
    ctx: LocalDomainContext,
    task: Any,
    original_message_id: str,
) -> Dict[str, Any]:
    from backend.app.models.workspace import TaskStatus

    try:
        extraction_result = await handler.intent_infra.handle_extraction_task(
            ctx=ctx,
            task=task,
            original_message_id=original_message_id,
        )
        logger.info(
            "Intent extraction task %s handle_extraction_task returned: %s",
            task.id,
            extraction_result,
        )
        handler.task_manager.tasks_store.update_task_status(
            task_id=task.id,
            status=TaskStatus.SUCCEEDED,
            error=None,
            completed_at=_utc_now(),
        )

        try:
            handler.task_manager.tasks_store.update_task(task.id, execution_id=None)
            logger.info("Cleared execution_id for intent_extraction task %s", task.id)
        except Exception as exc:
            logger.warning(
                "Failed to clear execution_id for intent_extraction task: %s",
                exc,
            )

        logger.info("Intent extraction task %s completed via IntentInfraService", task.id)
        result = {
            "pack_id": "intent_extraction",
            "intents_added": (
                extraction_result.get("intents_added", 0)
                if extraction_result
                else 0
            ),
            "timeline_item_id": (
                extraction_result.get("timeline_item_id") if extraction_result else None
            ),
            "executed_tasks": [task.id],
        }
        logger.info("Intent extraction result prepared: %s", result)
        return result
    except Exception as exc:
        logger.error("Error in intent_extraction execution: %s", exc, exc_info=True)
        raise


async def _execute_non_intent_pack(
    *,
    handler: Any,
    ctx: LocalDomainContext,
    pack_id: str,
    pack_id_lower: str,
    original_message_id: str,
    files,
    message: str,
    project_id: Optional[str],
    task: Optional[Any],
    action_params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    execution_method = None
    registry = get_registry()

    logger.info(
        "SuggestionActionHandler: Checking PlaybookService for %s, default_locale=%s, type=%s",
        pack_id,
        handler.default_locale,
        type(handler.default_locale),
    )
    playbook_found = None
    try:
        playbook = await handler.playbook_service.get_playbook(
            playbook_code=pack_id,
            locale=handler.default_locale,
            workspace_id=ctx.workspace_id,
        )
        if playbook:
            execution_method = "playbook"
            playbook_found = playbook.metadata.playbook_code
            logger.info(
                "Pack %s found in PlaybookService, execution method: %s, playbook_code: %s",
                pack_id,
                execution_method,
                playbook_found,
            )
        else:
            logger.debug("Pack %s not found in PlaybookService (returned None)", pack_id)
    except Exception as exc:
        logger.warning(
            "Pack %s error checking PlaybookService: %s: %s",
            pack_id,
            type(exc).__name__,
            exc,
        )

    if not execution_method:
        execution_method = registry.get_execution_method(pack_id)
        logger.info(
            "Pack %s execution method from CapabilityRegistry: %s",
            pack_id,
            execution_method,
        )

    result = None
    if execution_method == "pack_executor":
        result = await execute_pack_executor(
            handler=handler,
            ctx=ctx,
            pack_id=pack_id,
            pack_id_lower=pack_id_lower,
            original_message_id=original_message_id,
            files=files,
            message=message,
            project_id=project_id,
            task=task,
            action_params=action_params,
        )

    if execution_method == "playbook":
        result = await execute_playbook_method(
            handler=handler,
            ctx=ctx,
            pack_id=pack_id,
            playbook_found=playbook_found,
            registry=registry,
            files=files,
            message=message,
            task=task,
            action_params=action_params,
        )
    else:
        result = await execute_unknown_method(
            handler=handler,
            ctx=ctx,
            pack_id=pack_id,
            pack_id_lower=pack_id_lower,
            registry=registry,
            original_message_id=original_message_id,
            files=files,
            message=message,
            project_id=project_id,
            task=task,
            action_params=action_params,
            prior_result=result,
        )

    return result
