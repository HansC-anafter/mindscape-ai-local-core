"""
Plan Executor

Executes execution plans by coordinating task plans based on side_effect_level
and auto-execute configuration.
"""

import logging
from typing import Dict, Any, Optional, List, Callable

from ...models.workspace import ExecutionPlan, SideEffectLevel
from ...models.playbook import PlanContext
from ...core.execution_context import ExecutionContext

from .plan_preparer import PlanPreparer
from .playbook_resolver import PlaybookResolver
from .execution_launcher import ExecutionLauncher
from .task_events_emitter import TaskEventsEmitter
from .error_policy import ErrorPolicy

logger = logging.getLogger(__name__)


class PlanExecutor:
    """
    Executes execution plans

    Responsibilities:
    - Process task plans based on side_effect_level
    - Determine auto-execute based on execution_mode and config
    - Route to appropriate handlers (readonly execution, suggestion creation)
    - Coordinate PlanPreparer, PlaybookResolver, ExecutionLauncher
    """

    def __init__(
        self,
        plan_preparer: PlanPreparer,
        playbook_resolver: PlaybookResolver,
        execution_launcher: ExecutionLauncher,
        error_policy: ErrorPolicy,
        plan_builder,
        tasks_store,
    ):
        """
        Initialize PlanExecutor

        Args:
            plan_preparer: PlanPreparer instance
            playbook_resolver: PlaybookResolver instance
            execution_launcher: ExecutionLauncher instance
            error_policy: ErrorPolicy instance
            plan_builder: PlanBuilder instance
            tasks_store: TasksStore instance
        """
        self.plan_preparer = plan_preparer
        self.playbook_resolver = playbook_resolver
        self.execution_launcher = execution_launcher
        self.error_policy = error_policy
        self.plan_builder = plan_builder
        self.tasks_store = tasks_store

    async def execute_plan(
        self,
        execution_plan: ExecutionPlan,
        ctx: ExecutionContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        event_emitter: TaskEventsEmitter,
        workspace,
        prevent_suggestion_creation: bool = False,
        suggestion_creator=None,
    ) -> Dict[str, Any]:
        """
        Execute execution plan based on side_effect_level

        Args:
            execution_plan: Execution plan with tasks
            ctx: Execution context
            message_id: Message/event ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID
            event_emitter: TaskEventsEmitter instance
            workspace: Workspace instance
            prevent_suggestion_creation: Whether to prevent suggestion creation
            suggestion_creator: Optional SuggestionCardCreator instance

        Returns:
            Dict with execution results
        """
        """
        Execute execution plan based on side_effect_level

        Args:
            execution_plan: Execution plan with tasks
            ctx: Execution context
            message_id: Message/event ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID
            event_emitter: TaskEventsEmitter instance
            workspace: Workspace instance
            prevent_suggestion_creation: Whether to prevent suggestion creation
            suggestion_creator: Optional SuggestionCardCreator instance

        Returns:
            Dict with execution results
        """
        results = {
            "executed_tasks": [],
            "suggestion_cards": [],
            "skipped_tasks": [],
        }

        auto_exec_config = (
            workspace.playbook_auto_execution_config if workspace else None
        )

        execution_mode = getattr(workspace, "execution_mode", None) or "qa"
        execution_priority = getattr(workspace, "execution_priority", None) or "medium"

        from backend.app.shared.execution_thresholds import (
            get_threshold,
            should_auto_execute_readonly,
        )

        for task_plan in execution_plan.tasks:
            side_effect_level = self.plan_builder.determine_side_effect_level(
                task_plan.pack_id
            )

            should_auto_execute = self._determine_auto_execute(
                task_plan=task_plan,
                side_effect_level=side_effect_level,
                execution_mode=execution_mode,
                execution_priority=execution_priority,
                auto_exec_config=auto_exec_config,
            )

            logger.info(
                f"PlanExecutor: Processing task_plan {task_plan.pack_id}, "
                f"side_effect_level={side_effect_level}, auto_execute={should_auto_execute}"
            )

            if should_auto_execute and side_effect_level == SideEffectLevel.READONLY:
                result = await self._execute_readonly_task(
                    task_plan=task_plan,
                    ctx=ctx,
                    message_id=message_id,
                    files=files,
                    message=message,
                    project_id=project_id,
                    event_emitter=event_emitter,
                    execution_plan=execution_plan,
                )
                if result:
                    results["executed_tasks"].append(result)
                    logger.info(
                        f"PlanExecutor: READONLY task {task_plan.pack_id} completed"
                    )
                else:
                    await self._handle_execution_failure(
                        task_plan=task_plan,
                        ctx=ctx,
                        message_id=message_id,
                        results=results,
                        prevent_suggestion_creation=prevent_suggestion_creation,
                        suggestion_creator=suggestion_creator,
                        event_emitter=event_emitter,
                    )

            elif side_effect_level == SideEffectLevel.SOFT_WRITE:
                result = await self._handle_soft_write_task(
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
                    else:
                        self.error_policy.warn_and_continue(
                            f"Failed to create suggestion card for EXTERNAL_WRITE task {task_plan.pack_id}"
                        )
                        results["skipped_tasks"].append(task_plan.pack_id)

        return results

    def _determine_auto_execute(
        self,
        task_plan,
        side_effect_level: SideEffectLevel,
        execution_mode: str,
        execution_priority: str,
        auto_exec_config: Optional[Dict[str, Any]],
    ) -> bool:
        """
        Determine if task should auto-execute based on execution_mode and config

        Args:
            task_plan: Task plan
            side_effect_level: Side effect level
            execution_mode: Execution mode (qa/execution/hybrid)
            execution_priority: Execution priority (low/medium/high)
            auto_exec_config: Optional auto-execution config

        Returns:
            True if should auto-execute, False otherwise
        """
        should_auto_execute = task_plan.auto_execute

        llm_confidence = (
            task_plan.params.get("llm_analysis", {}).get("confidence", 0.0)
            if task_plan.params
            else 0.0
        )

        if (
            execution_mode in ("execution", "hybrid")
            and side_effect_level == SideEffectLevel.READONLY
        ):
            from backend.app.shared.execution_thresholds import should_auto_execute_readonly

            should_auto_execute = should_auto_execute_readonly(
                execution_priority, llm_confidence
            )
            logger.info(
                f"PlanExecutor: READONLY task {task_plan.pack_id} auto-execute={should_auto_execute} "
                f"(execution_mode={execution_mode}, priority={execution_priority}, confidence={llm_confidence:.2f})"
            )

        elif auto_exec_config and task_plan.pack_id in auto_exec_config:
            from backend.app.shared.execution_thresholds import get_threshold

            playbook_config = auto_exec_config[task_plan.pack_id]
            default_threshold = get_threshold(execution_priority)
            confidence_threshold = playbook_config.get(
                "confidence_threshold", default_threshold
            )
            auto_execute_enabled = playbook_config.get("auto_execute", False)

            if auto_execute_enabled and llm_confidence >= confidence_threshold:
                should_auto_execute = True
                logger.info(
                    f"PlanExecutor: Playbook {task_plan.pack_id} meets auto-exec threshold "
                    f"(confidence={llm_confidence:.2f} >= {confidence_threshold:.2f})"
                )
            else:
                should_auto_execute = False
                logger.info(
                    f"PlanExecutor: Playbook {task_plan.pack_id} does not meet auto-exec threshold "
                    f"(confidence={llm_confidence:.2f} < {confidence_threshold:.2f})"
                )

        return should_auto_execute

    async def _execute_readonly_task(
        self,
        task_plan,
        ctx: ExecutionContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        event_emitter: TaskEventsEmitter,
        execution_plan: Optional[ExecutionPlan] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute readonly task using coordination modules

        Args:
            task_plan: Task plan
            ctx: Execution context
            message_id: Message ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID
            event_emitter: TaskEventsEmitter instance
            execution_plan: Optional execution plan (for plan_node mode)

        Returns:
            Execution result dict or None if failed
        """
        pack_id = task_plan.pack_id

        prepared_plan = await self.plan_preparer.prepare_plan(
            task_plan=task_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
        )

        resolved_playbook = await self.playbook_resolver.resolve(
            pack_id=prepared_plan.pack_id, ctx=ctx
        )

        if not resolved_playbook:
            self.error_policy.warn_and_continue(
                f"Could not resolve playbook for pack {pack_id}"
            )
            return None

        plan_context = None
        plan_id = None
        task_id = task_plan.params.get("step_id") if task_plan.params else None
        if execution_plan:
            plan_id = execution_plan.id
            plan_context = PlanContext(
                plan_summary=execution_plan.plan_summary or "",
                reasoning=execution_plan.reasoning or "",
                steps=[step.dict() if hasattr(step, 'dict') else step for step in execution_plan.steps],
                dependencies=task_plan.params.get("depends_on", []) if task_plan.params else [],
            )

        try:
            launch_result = await self.execution_launcher.launch(
                playbook_code=resolved_playbook.code,
                inputs=prepared_plan.playbook_inputs,
                ctx=ctx,
                project_meta=prepared_plan.project_meta,
                project_id=project_id,
                plan_id=plan_id,
                task_id=task_id,
                plan_context=plan_context,
                trace_id=message_id,  # Use message_id as trace_id
            )

            execution_id = launch_result.get("execution_id")
            if not execution_id:
                self.error_policy.handle_missing_execution_id(
                    resolved_playbook.code, launch_result.get("raw_result")
                )

            if execution_id:
                task = self.tasks_store.get_task_by_execution_id(execution_id)
                if task:
                    event_emitter.emit_task_created(
                        task_id=task.id,
                        pack_id=pack_id,
                        playbook_code=resolved_playbook.code,
                        status=task.status.value
                        if hasattr(task.status, "value")
                        else str(task.status),
                        task_type=task.task_type,
                        workspace_id=ctx.workspace_id,
                        execution_id=execution_id,
                    )
                elif execution_id:
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

        except Exception as e:
            self.error_policy.handle_execution_error(
                f"launch playbook {resolved_playbook.code}", e, raise_on_error=True
            )

    async def _handle_execution_failure(
        self,
        task_plan,
        ctx: ExecutionContext,
        message_id: str,
        results: Dict[str, Any],
        prevent_suggestion_creation: bool,
        suggestion_creator,
        event_emitter: TaskEventsEmitter,
    ) -> None:
        """
        Handle execution failure by creating suggestion card or skipping

        Args:
            task_plan: Task plan
            ctx: Execution context
            results: Results dict to update
            prevent_suggestion_creation: Whether to prevent suggestion creation
            suggestion_creator: Optional SuggestionCardCreator instance
            event_emitter: TaskEventsEmitter instance
        """
        pack_id_lower = task_plan.pack_id.lower() if task_plan.pack_id else ""

        if pack_id_lower == "intent_extraction":
            logger.error(
                f"PlanExecutor: intent_extraction execution failed in fallback path. "
                f"This should not happen - intent_extraction should be handled by IntentInfraService."
            )
            results["skipped_tasks"].append(task_plan.pack_id)
        elif not prevent_suggestion_creation and suggestion_creator:
            # Check for existing pending tasks to avoid infinite loop
            pending_tasks = self.tasks_store.list_pending_tasks(
                ctx.workspace_id, exclude_cancelled=True
            )
            existing_pending = [
                t for t in pending_tasks if t.pack_id == task_plan.pack_id
            ]

            if existing_pending:
                logger.info(
                    f"PlanExecutor: Found existing pending task for {task_plan.pack_id}, skipping suggestion creation"
                )
                results["skipped_tasks"].append(task_plan.pack_id)
            else:
                suggestion = await suggestion_creator.create_suggestion_card(
                    task_plan=task_plan,
                    workspace_id=ctx.workspace_id,
                    message_id=message_id,
                    event_emitter=event_emitter,
                )
                if suggestion:
                    results["suggestion_cards"].append(suggestion)

    async def _handle_soft_write_task(
        self,
        task_plan,
        ctx: ExecutionContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        event_emitter: TaskEventsEmitter,
        auto_exec_config: Optional[Dict[str, Any]],
        execution_priority: str,
        prevent_suggestion_creation: bool,
        suggestion_creator,
    ) -> Optional[Dict[str, Any]]:
        """
        Handle SOFT_WRITE task (may auto-execute or create suggestion)

        Args:
            task_plan: Task plan
            ctx: Execution context
            message_id: Message ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID
            event_emitter: TaskEventsEmitter instance
            auto_exec_config: Optional auto-execution config
            execution_priority: Execution priority
            prevent_suggestion_creation: Whether to prevent suggestion creation
            suggestion_creator: Optional SuggestionCardCreator instance

        Returns:
            Dict with "executed" or "suggestion" key, or None
        """
        # Check if should auto-execute based on workspace config
        should_auto_execute_soft = False
        if auto_exec_config and task_plan.pack_id in auto_exec_config:
            from backend.app.shared.execution_thresholds import get_threshold

            playbook_config = auto_exec_config[task_plan.pack_id]
            default_threshold = get_threshold(execution_priority)
            confidence_threshold = playbook_config.get(
                "confidence_threshold", default_threshold
            )
            auto_execute_enabled = playbook_config.get("auto_execute", False)

            llm_confidence = (
                task_plan.params.get("llm_analysis", {}).get("confidence", 0.0)
                if task_plan.params
                else 0.0
            )

            if auto_execute_enabled and llm_confidence >= confidence_threshold:
                should_auto_execute_soft = True
                logger.info(
                    f"PlanExecutor: SOFT_WRITE playbook {task_plan.pack_id} meets auto-exec threshold, executing directly"
                )

                playbook_context = task_plan.params.get(
                    "context", task_plan.params.copy() if task_plan.params else {}
                )
                if task_plan.params:
                    playbook_context.update(task_plan.params)

                return None

        if not prevent_suggestion_creation and suggestion_creator:
            logger.info(
                f"PlanExecutor: Creating suggestion card for SOFT_WRITE task {task_plan.pack_id}"
            )
            suggestion = await suggestion_creator.create_suggestion_card(
                task_plan=task_plan,
                workspace_id=ctx.workspace_id,
                message_id=message_id,
                event_emitter=event_emitter,
            )
            if suggestion:
                logger.info(
                    f"PlanExecutor: Suggestion card created for {task_plan.pack_id}"
                )
                return {"suggestion": True, "result": suggestion}

        return None
