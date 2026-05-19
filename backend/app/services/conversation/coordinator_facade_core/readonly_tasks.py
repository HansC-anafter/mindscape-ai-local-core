"""Readonly task execution helper for CoordinatorFacade."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter

logger = logging.getLogger(__name__)


async def execute_readonly_task(
    *,
    facade: Any,
    task_plan: Any,
    ctx: LocalDomainContext,
    message_id: str,
    files: List[str],
    message: str,
    project_id: Optional[str],
    event_emitter: TaskEventsEmitter,
) -> Optional[Dict[str, Any]]:
    """Execute a readonly task automatically or delegate special packs."""
    pack_id = task_plan.pack_id
    pack_id_lower = pack_id.lower() if pack_id else ""

    if pack_id_lower == "intent_extraction":
        logger.error(
            "CoordinatorFacade: intent_extraction should not reach _execute_readonly_task. "
            "This indicates a routing issue. Task should be handled by IntentInfraService."
        )
        raise ValueError(
            "intent_extraction should be handled by IntentInfraService, not CoordinatorFacade."
        )

    if pack_id == "semantic_seeds":
        return await facade.special_pack_executors.execute_semantic_seeds(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.actor_id,
            message_id=message_id,
            files=files,
            message=message,
            event_emitter=event_emitter,
        )

    execution_method = None

    if facade.playbook_service:
        try:
            playbook = await facade.playbook_service.get_playbook(
                playbook_code=pack_id,
                locale=facade.default_locale,
                workspace_id=ctx.workspace_id,
            )
            if playbook:
                execution_method = "playbook"
                logger.info(
                    "CoordinatorFacade: Pack %s found in PlaybookService, execution method: %s",
                    pack_id,
                    execution_method,
                )
        except Exception as exc:
            logger.warning(
                "CoordinatorFacade: Playbook %s error in PlaybookService: %s: %s",
                pack_id,
                type(exc).__name__,
                exc,
            )

    if not execution_method:
        from backend.app.services.capability_registry import get_registry

        registry = get_registry()
        execution_method = registry.get_execution_method(pack_id)
        logger.info(
            "CoordinatorFacade: Pack %s execution method from CapabilityRegistry: %s",
            pack_id,
            execution_method,
        )

    if execution_method == "playbook":
        prepared_plan = await facade.plan_preparer.prepare_plan(
            task_plan=task_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
        )

        resolved_playbook = await facade.playbook_resolver.resolve(
            pack_id=prepared_plan.pack_id,
            ctx=ctx,
        )

        if not resolved_playbook:
            facade.error_policy.warn_and_continue(
                f"Could not resolve playbook for pack {pack_id}"
            )
            return None

        try:
            launch_result = await facade.execution_launcher.launch(
                playbook_code=resolved_playbook.code,
                inputs=prepared_plan.playbook_inputs,
                ctx=ctx,
                project_meta=prepared_plan.project_meta,
                project_id=project_id,
            )

            execution_id = launch_result.get("execution_id")
            if not execution_id:
                facade.error_policy.handle_missing_execution_id(
                    resolved_playbook.code,
                    launch_result.get("raw_result"),
                )

            if execution_id:
                task = facade.tasks_store.get_task_by_execution_id(execution_id)
                if task:
                    event_emitter.emit_task_created(
                        task_id=task.id,
                        pack_id=pack_id,
                        playbook_code=resolved_playbook.code,
                        status=(
                            task.status.value
                            if hasattr(task.status, "value")
                            else str(task.status)
                        ),
                        task_type=task.task_type,
                        workspace_id=ctx.workspace_id,
                        execution_id=execution_id,
                    )
                else:
                    event_emitter.emit_task_created(
                        task_id=execution_id,
                        pack_id=pack_id,
                        playbook_code=resolved_playbook.code,
                        status="running",
                        task_type="playbook_execution",
                        workspace_id=ctx.workspace_id,
                        execution_id=execution_id,
                    )

            return {
                "pack_id": pack_id,
                "playbook_code": resolved_playbook.code,
                "execution_id": execution_id,
            }
        except Exception as exc:
            facade.error_policy.handle_execution_error(
                f"launch playbook {resolved_playbook.code}",
                exc,
                raise_on_error=True,
            )

    if execution_method == "pack_executor":
        facade.error_policy.warn_and_continue(
            f"Pack {pack_id} has pack_executor but no handler in CoordinatorFacade"
        )
        return None

    facade.error_policy.warn_and_continue(
        f"Unknown execution method for pack {pack_id}: {execution_method}"
    )
    return None
