"""Plan executor runtime loop."""

import logging
from typing import Any, Dict, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.workspace import ExecutionPlan, SideEffectLevel
from backend.app.services.conversation.plan_executor_core.completion_gates import (
    check_definition_of_done,
    check_quality_gates,
)
from backend.app.services.conversation.plan_executor_core.orchestration import (
    advance_execution_orchestration,
    cleanup_execution_orchestration,
    initialize_execution_orchestration,
)
from backend.app.services.conversation.task_events_emitter import TaskEventsEmitter

logger = logging.getLogger(__name__)


async def execute_plan(
    executor,
    execution_plan: ExecutionPlan,
    ctx: LocalDomainContext,
    message_id: str,
    files: List[str],
    message: str,
    project_id: Optional[str],
    event_emitter: TaskEventsEmitter,
    workspace,
    prevent_suggestion_creation: bool = False,
    suggestion_creator=None,
) -> Dict[str, Any]:
    results = {
        "executed_tasks": [],
        "suggestion_cards": [],
        "skipped_tasks": [],
    }
    auto_exec_config = workspace.playbook_auto_execution_config if workspace else None

    from backend.app.services.stores.workspace_runtime_profile_store import (
        WorkspaceRuntimeProfileStore,
    )
    from backend.app.utils.runtime_profile import get_resolved_mode

    runtime_profile = None
    if workspace:
        try:
            profile_store = WorkspaceRuntimeProfileStore()
            runtime_profile = await profile_store.get_runtime_profile(workspace.id)
            if runtime_profile:
                runtime_profile.ensure_phase2_fields()
        except Exception as exc:
            logger.debug(f"Failed to load runtime profile: {exc}")

    resolved_mode_enum = (
        get_resolved_mode(workspace, runtime_profile) if workspace else None
    )
    execution_mode = (
        resolved_mode_enum.value
        if resolved_mode_enum
        else (getattr(workspace, "execution_mode", None) or "meeting")
    )
    execution_priority = getattr(workspace, "execution_priority", None) or "medium"
    stop_conditions = runtime_profile.stop_conditions if runtime_profile else None
    retry_count = 0
    error_count = 0

    orchestration_state = await initialize_execution_orchestration(
        execution_plan=execution_plan,
        ctx=ctx,
        workspace=workspace,
        runtime_profile=runtime_profile,
        stop_conditions=stop_conditions,
        message_id=message_id,
        resolve_playbook=executor.playbook_resolver.resolve,
    )

    try:
        for task_index, task_plan in enumerate(execution_plan.tasks, start=1):
            if not advance_execution_orchestration(orchestration_state, task_index):
                break
            if _stop_conditions_met(stop_conditions, error_count, retry_count):
                break

            side_effect_level = executor.plan_builder.determine_side_effect_level(
                task_plan.pack_id
            )
            should_auto_execute = executor._determine_auto_execute(
                task_plan=task_plan,
                side_effect_level=side_effect_level,
                execution_mode=execution_mode,
                execution_priority=execution_priority,
                auto_exec_config=auto_exec_config,
            )
            logger.info(
                f"PlanExecutor: Processing task_plan {task_plan.pack_id}, "
                f"side_effect_level={side_effect_level}, auto_execute={should_auto_execute}, "
                "eligible_agents="
                f"{list(orchestration_state.eligible_agent_ids) if orchestration_state.orchestrator else []}"
            )

            if should_auto_execute and side_effect_level == SideEffectLevel.READONLY:
                task_result = await _handle_readonly_auto_execute(
                    executor,
                    task_plan,
                    ctx,
                    message_id,
                    files,
                    message,
                    project_id,
                    event_emitter,
                    execution_plan,
                    orchestration_state,
                    runtime_profile,
                    retry_count,
                    results,
                    prevent_suggestion_creation,
                    suggestion_creator,
                )
                retry_count = task_result["retry_count"]
                error_count += task_result["error_increment"]
            elif side_effect_level == SideEffectLevel.SOFT_WRITE:
                result = await executor._handle_soft_write_task(
                    task_plan=task_plan,
                    ctx=ctx,
                    message_id=message_id,
                    files=files,
                    message=message,
                    project_id=project_id,
                    event_emitter=event_emitter,
                    auto_exec_config=auto_exec_config,
                    execution_priority=execution_priority,
                    prevent_suggestion_creation=prevent_suggestion_creation,
                    suggestion_creator=suggestion_creator,
                )
                if result:
                    if result.get("executed"):
                        results["executed_tasks"].append(result["result"])
                    elif result.get("suggestion"):
                        results["suggestion_cards"].append(result["result"])
            elif side_effect_level == SideEffectLevel.EXTERNAL_WRITE:
                error_count += await _handle_external_write_task(
                    executor,
                    task_plan,
                    ctx,
                    message_id,
                    event_emitter,
                    results,
                    prevent_suggestion_creation,
                    suggestion_creator,
                )

        check_definition_of_done(
            runtime_profile=runtime_profile,
            stop_conditions=stop_conditions,
            workspace=workspace,
            results=results,
        )
        check_quality_gates(
            runtime_profile=runtime_profile,
            workspace=workspace,
            results=results,
            orchestration_state=orchestration_state,
        )
    finally:
        cleanup_execution_orchestration(orchestration_state)

    return results


def _stop_conditions_met(stop_conditions, error_count: int, retry_count: int) -> bool:
    if not stop_conditions:
        return False
    if error_count >= stop_conditions.max_errors:
        logger.warning(
            f"StopConditions: Max errors reached ({error_count}/{stop_conditions.max_errors}). "
            "Stopping execution."
        )
        return True
    if retry_count >= stop_conditions.max_retries:
        logger.warning(
            f"StopConditions: Max retries reached ({retry_count}/{stop_conditions.max_retries}). "
            "Stopping execution."
        )
        return True
    return False


async def _handle_readonly_auto_execute(
    executor,
    task_plan,
    ctx,
    message_id,
    files,
    message,
    project_id,
    event_emitter,
    execution_plan,
    orchestration_state,
    runtime_profile,
    retry_count,
    results,
    prevent_suggestion_creation,
    suggestion_creator,
) -> Dict[str, int]:
    if orchestration_state.orchestrator:
        orchestration_state.orchestrator.record_step()

    result = await executor._execute_readonly_task(
        task_plan=task_plan,
        ctx=ctx,
        message_id=message_id,
        files=files,
        message=message,
        project_id=project_id,
        event_emitter=event_emitter,
        execution_plan=execution_plan,
        orchestration_state=orchestration_state,
    )
    if result:
        orchestration_state.remember_primary_execution_id(result.get("execution_id"))
        results["executed_tasks"].append(result)
        logger.info(f"PlanExecutor: READONLY task {task_plan.pack_id} completed")
        return {"retry_count": retry_count, "error_increment": 0}

    if orchestration_state.orchestrator:
        orchestration_state.orchestrator.record_error()
    recovery_result = await _apply_recovery_policy(
        executor=executor,
        task_plan=task_plan,
        ctx=ctx,
        message_id=message_id,
        files=files,
        message=message,
        project_id=project_id,
        event_emitter=event_emitter,
        execution_plan=execution_plan,
        orchestration_state=orchestration_state,
        runtime_profile=runtime_profile,
        retry_count=retry_count,
        results=results,
    )
    retry_count = recovery_result["retry_count"]
    if not recovery_result["recovered"]:
        await executor._handle_execution_failure(
            task_plan=task_plan,
            ctx=ctx,
            message_id=message_id,
            results=results,
            prevent_suggestion_creation=prevent_suggestion_creation,
            suggestion_creator=suggestion_creator,
            event_emitter=event_emitter,
        )
    return {"retry_count": retry_count, "error_increment": 1}


async def _apply_recovery_policy(
    *,
    executor,
    task_plan,
    ctx,
    message_id,
    files,
    message,
    project_id,
    event_emitter,
    execution_plan,
    orchestration_state,
    runtime_profile,
    retry_count,
    results,
) -> Dict[str, Any]:
    if not runtime_profile or not runtime_profile.recovery_policy:
        return {"retry_count": retry_count, "recovered": False}
    recovered = False
    try:
        import asyncio

        from backend.app.services.conversation.recovery_handler import RecoveryHandler

        recovery_handler = RecoveryHandler(
            runtime_profile.recovery_policy,
            max_retries=runtime_profile.stop_conditions.max_retries,
        )

        async def retry_readonly_task():
            return await executor._execute_readonly_task(
                task_plan=task_plan,
                ctx=ctx,
                message_id=message_id,
                files=files,
                message=message,
                project_id=project_id,
                event_emitter=event_emitter,
                execution_plan=execution_plan,
                orchestration_state=orchestration_state,
            )

        recovery_result = await recovery_handler.handle_error(
            error=Exception("Readonly task execution failed"),
            operation=f"execute_readonly_task({task_plan.pack_id})",
            retry_func=retry_readonly_task,
            retry_count=retry_count,
        )
        if recovery_result["action"] == "retry" and recovery_result["retry_after"] is not None:
            await asyncio.sleep(recovery_result["retry_after"])
            retry_count += 1
            retry_result = await retry_readonly_task()
            if retry_result:
                results["executed_tasks"].append(retry_result)
                logger.info(f"RecoveryPolicy: Retry succeeded for {task_plan.pack_id}")
                recovered = True
        elif recovery_result["action"] == "fallback":
            fallback_info = await recovery_handler.apply_fallback_mode(
                recovery_result["fallback_mode"],
                f"execute_readonly_task({task_plan.pack_id})",
            )
            logger.info(
                f"RecoveryPolicy: Applied fallback mode: {fallback_info['mode']}"
            )
    except Exception as exc:
        logger.warning(f"RecoveryPolicy handling failed: {exc}", exc_info=True)
    return {"retry_count": retry_count, "recovered": recovered}


async def _handle_external_write_task(
    executor,
    task_plan,
    ctx,
    message_id,
    event_emitter,
    results,
    prevent_suggestion_creation,
    suggestion_creator,
) -> int:
    if not prevent_suggestion_creation and suggestion_creator:
        logger.info(
            f"PlanExecutor: Creating suggestion card for EXTERNAL_WRITE task {task_plan.pack_id}"
        )
        suggestion = await suggestion_creator.create_suggestion_card(
            task_plan=task_plan,
            workspace_id=ctx.workspace_id,
            message_id=message_id,
            event_emitter=event_emitter,
        )
        if suggestion:
            results["suggestion_cards"].append(suggestion)
            logger.info(
                f"PlanExecutor: Suggestion card created for {task_plan.pack_id}"
            )
            return 0
        else:
            executor.error_policy.warn_and_continue(
                f"Failed to create suggestion card for EXTERNAL_WRITE task {task_plan.pack_id}"
            )
            results["skipped_tasks"].append(task_plan.pack_id)
            return 1
    return 0
