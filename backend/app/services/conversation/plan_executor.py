"""
Plan Executor

Executes execution plans by coordinating task plans based on side_effect_level
and auto-execute configuration.
"""

import logging
from typing import Dict, Any, Optional, List, Callable

from ...core.domain_context import LocalDomainContext
from ...models.workspace import ExecutionPlan, SideEffectLevel
from ...models.playbook import PlanContext

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

        # Use get_resolved_mode() to respect runtime_profile.default_mode priority
        from backend.app.utils.runtime_profile import get_resolved_mode
        from backend.app.services.stores.workspace_runtime_profile_store import WorkspaceRuntimeProfileStore

        # Load runtime profile if available
        runtime_profile = None
        if workspace:
            try:
                # Get db_path from tasks_store (which has db_path attribute)
                db_path = getattr(self.tasks_store, 'db_path', None)
                if db_path:
                    profile_store = WorkspaceRuntimeProfileStore(db_path=db_path)
                    runtime_profile = profile_store.get_runtime_profile(workspace.id)
                    # Ensure Phase 2 fields are initialized
                    if runtime_profile:
                        runtime_profile.ensure_phase2_fields()
            except Exception as e:
                logger.debug(f"Failed to load runtime profile: {e}")

        resolved_mode_enum = get_resolved_mode(workspace, runtime_profile) if workspace else None
        execution_mode = resolved_mode_enum.value if resolved_mode_enum else (getattr(workspace, "execution_mode", None) or "qa")
        execution_priority = getattr(workspace, "execution_priority", None) or "medium"

        # Initialize StopConditions tracking (Phase 2)
        stop_conditions = runtime_profile.stop_conditions if runtime_profile else None
        retry_count = 0
        error_count = 0

        # Phase 2: Multi-Agent Orchestration Setup
        multi_agent_orchestrator = None
        registered_execution_ids = []  # Track all registered execution_ids for cleanup
        primary_execution_id = None  # Track primary execution_id for event association

        # Use try-finally to ensure cleanup even on exceptions (P3: Recycling Mechanism)
        try:
            if runtime_profile and runtime_profile.topology_routing:
                try:
                    from backend.app.services.orchestration.multi_agent_orchestrator import MultiAgentOrchestrator
                    from backend.app.services.orchestration.topology_validator import TopologyValidator, TopologyValidationError

                    # Collect agent_roster from all playbooks in execution plan
                    agent_roster = {}
                    for task_plan in execution_plan.tasks:
                        try:
                            resolved_playbook = await self.playbook_resolver.resolve(
                                pack_id=task_plan.pack_id,
                                ctx=ctx
                            )
                            if resolved_playbook and resolved_playbook.playbook and resolved_playbook.playbook.agent_roster:
                                # Merge agent rosters (later playbooks override earlier ones if agent_id conflicts)
                                agent_roster.update(resolved_playbook.playbook.agent_roster)
                        except Exception as e:
                            logger.debug(f"Failed to load agent_roster from playbook {task_plan.pack_id}: {e}")

                    # Validate topology - fail-fast if topology is configured but roster is missing
                    validator = TopologyValidator()
                    if not agent_roster:
                        # If topology is configured but no agent_roster found, fail-fast
                        raise ValueError(
                            f"Topology routing is configured but no agent_roster found in playbooks. "
                            f"Please ensure playbooks define agent_roster when using topology_routing."
                        )

                    try:
                        validator.validate(runtime_profile.topology_routing, agent_roster)
                        logger.info(f"Topology validated successfully: {len(agent_roster)} agents in roster")
                    except TopologyValidationError as e:
                        logger.error(f"Topology validation failed: {e}")
                        # Fail-fast: raise error if topology is invalid
                        raise ValueError(f"Invalid topology configuration: {e}")

                    # Get event store for event recording
                    from backend.app.services.stores.events_store import EventsStore
                    db_path = getattr(self.tasks_store, 'db_path', None)
                    event_store = EventsStore(db_path=db_path) if db_path else None

                    # Initialize MultiAgentOrchestrator (execution_id will be set later when available)
                    multi_agent_orchestrator = MultiAgentOrchestrator(
                        agent_roster=agent_roster,
                        topology=runtime_profile.topology_routing,
                        loop_budget=runtime_profile.loop_budget if runtime_profile else None,
                        stop_conditions=stop_conditions,
                        workspace_id=workspace.id if workspace else None,
                        profile_id=getattr(runtime_profile, 'profile_id', None),
                        event_store=event_store
                    )
                    logger.info(f"MultiAgentOrchestrator initialized with {len(agent_roster)} agents")

                    # Phase 2: Register orchestrator in global registry for tool_executor access
                    from backend.app.services.orchestration.orchestrator_registry import get_orchestrator_registry
                    orchestrator_registry = get_orchestrator_registry()
                    # Use message_id as execution_id for registration (will be updated when we get actual execution_id)
                    orchestrator_registry.register(message_id, multi_agent_orchestrator)

                    # Phase 2: Initialize agent flow - get initial agent(s)
                    initial_agents = multi_agent_orchestrator.get_next_agents(current_agent_id=None)
                    if initial_agents:
                        # Set first agent as current
                        multi_agent_orchestrator.set_current_agent(initial_agents[0])
                        logger.info(f"MultiAgentOrchestrator: Starting with agent '{initial_agents[0]}'")
                    else:
                        logger.warning("MultiAgentOrchestrator: No initial agents found")
                except Exception as e:
                    logger.warning(f"Failed to initialize MultiAgentOrchestrator: {e}", exc_info=True)
                    # Don't fail execution if orchestration setup fails, but log warning

            from backend.app.shared.execution_thresholds import (
                get_threshold,
                should_auto_execute_readonly,
            )

            # Phase 2: Track current agent for multi-agent orchestration
            current_agent_id = None
            task_index = 0

            for task_plan in execution_plan.tasks:
                task_index += 1

                # Phase 2: Multi-Agent Orchestration - determine which agent should handle this task
                if multi_agent_orchestrator:
                    # Check if we should transition to next agent based on topology
                    next_agents = multi_agent_orchestrator.get_next_agents(current_agent_id=current_agent_id)

                    if next_agents and current_agent_id != next_agents[0]:
                        # Transition to next agent
                        new_agent_id = next_agents[0]
                        multi_agent_orchestrator.set_current_agent(new_agent_id)
                        current_agent_id = new_agent_id
                        logger.info(f"MultiAgentOrchestrator: Transitioned to agent '{current_agent_id}'")

                        # Record turn when switching agents (conversation turn)
                        multi_agent_orchestrator.record_turn()
                    elif current_agent_id is None and next_agents:
                        # First task - set initial agent
                        current_agent_id = next_agents[0]
                        multi_agent_orchestrator.set_current_agent(current_agent_id)
                        logger.info(f"MultiAgentOrchestrator: Starting with agent '{current_agent_id}'")

                    # Record iteration at start of each task (if this is a new iteration)
                    # For sequential pattern, each task is a step; for loop pattern, we track iterations separately
                    if multi_agent_orchestrator.topology.default_pattern == "loop":
                        # In loop pattern, record iteration when starting a new cycle
                        if task_index == 1 or (task_index > 1 and current_agent_id == multi_agent_orchestrator.state.visited_agents[0] if multi_agent_orchestrator.state.visited_agents else False):
                            multi_agent_orchestrator.record_iteration()

                    # Check MultiAgentOrchestrator stop conditions before processing task
                    if multi_agent_orchestrator.should_stop():
                        logger.warning(
                            f"MultiAgentOrchestrator: Stop conditions met. "
                            f"State: iteration={multi_agent_orchestrator.state.iteration_count}, "
                            f"turn={multi_agent_orchestrator.state.turn_count}, "
                            f"step={multi_agent_orchestrator.state.step_count}, "
                            f"tool_call={multi_agent_orchestrator.state.tool_call_count}, "
                            f"error={multi_agent_orchestrator.state.error_count}"
                        )
                        break

                # Check StopConditions before processing each task (Phase 2)
                if stop_conditions:
                    # Check max_errors
                    if error_count >= stop_conditions.max_errors:
                        logger.warning(
                            f"StopConditions: Max errors reached ({error_count}/{stop_conditions.max_errors}). "
                            f"Stopping execution."
                        )
                        break

                    # Check max_retries
                    if retry_count >= stop_conditions.max_retries:
                        logger.warning(
                            f"StopConditions: Max retries reached ({retry_count}/{stop_conditions.max_retries}). "
                            f"Stopping execution."
                        )
                        break

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
                    f"side_effect_level={side_effect_level}, auto_execute={should_auto_execute}, "
                    f"current_agent={current_agent_id if multi_agent_orchestrator else None}"
                )

                if should_auto_execute and side_effect_level == SideEffectLevel.READONLY:
                    # Phase 2: Record step in MultiAgentOrchestrator
                    if multi_agent_orchestrator:
                        multi_agent_orchestrator.record_step()

                    result = await self._execute_readonly_task(
                        task_plan=task_plan,
                        ctx=ctx,
                        message_id=message_id,
                        files=files,
                        message=message,
                        project_id=project_id,
                        event_emitter=event_emitter,
                        execution_plan=execution_plan,
                        multi_agent_orchestrator=multi_agent_orchestrator,  # Pass orchestrator for tool call tracking
                        registered_execution_ids=registered_execution_ids,  # Pass for tracking registered IDs
                    )
                    if result:
                        results["executed_tasks"].append(result)
                        logger.info(
                            f"PlanExecutor: READONLY task {task_plan.pack_id} completed"
                        )
                    else:
                        error_count += 1  # Track error count for StopConditions (Phase 2)
                        # Phase 2: Record error in MultiAgentOrchestrator
                        if multi_agent_orchestrator:
                            multi_agent_orchestrator.record_error()

                        # Apply RecoveryPolicy if available (Phase 2)
                        if runtime_profile and runtime_profile.recovery_policy:
                            try:
                                from backend.app.services.conversation.recovery_handler import RecoveryHandler
                                import asyncio

                                recovery_handler = RecoveryHandler(runtime_profile.recovery_policy)

                                # Create a retry function (if needed)
                                async def retry_readonly_task():
                                    return await self._execute_readonly_task(
                                        task_plan=task_plan,
                                        ctx=ctx,
                                        message_id=message_id,
                                        files=files,
                                        message=message,
                                        project_id=project_id,
                                        event_emitter=event_emitter,
                                        execution_plan=execution_plan,
                                        multi_agent_orchestrator=multi_agent_orchestrator,
                                        registered_execution_ids=registered_execution_ids,
                                    )

                                recovery_result = await recovery_handler.handle_error(
                                    error=Exception("Readonly task execution failed"),
                                    operation=f"execute_readonly_task({task_plan.pack_id})",
                                    retry_func=retry_readonly_task,
                                    retry_count=retry_count
                                )

                                if recovery_result["action"] == "retry" and recovery_result["retry_after"] is not None:
                                    # Wait before retry
                                    await asyncio.sleep(recovery_result["retry_after"])
                                    retry_count += 1
                                    # Retry the task
                                    retry_result = await retry_readonly_task()
                                    if retry_result:
                                        results["executed_tasks"].append(retry_result)
                                        logger.info(f"RecoveryPolicy: Retry succeeded for {task_plan.pack_id}")
                                        continue  # Skip to next task

                                elif recovery_result["action"] == "fallback":
                                    fallback_info = await recovery_handler.apply_fallback_mode(
                                        recovery_result["fallback_mode"],
                                        f"execute_readonly_task({task_plan.pack_id})"
                                    )
                                    logger.info(f"RecoveryPolicy: Applied fallback mode: {fallback_info['mode']}")
                                    # Continue with fallback mode restrictions
                            except Exception as e:
                                logger.warning(f"RecoveryPolicy handling failed: {e}", exc_info=True)

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
                            error_count += 1  # Track error count for StopConditions (Phase 2)
                            self.error_policy.warn_and_continue(
                                f"Failed to create suggestion card for EXTERNAL_WRITE task {task_plan.pack_id}"
                            )
                            results["skipped_tasks"].append(task_plan.pack_id)

            # Check definition_of_done after execution (Phase 2 StopConditions)
            definition_of_done_passed = True
            if stop_conditions and stop_conditions.definition_of_done:
                logger.info(f"StopConditions: Checking definition_of_done: {stop_conditions.definition_of_done}")

                # Get changed files from execution results
                changed_files = []
                for executed_task in results.get("executed_tasks", []):
                    if isinstance(executed_task, dict) and executed_task.get("changed_files"):
                        changed_files.extend(executed_task["changed_files"])

                # Implement actual criteria checking
                for criterion in stop_conditions.definition_of_done:
                    criterion_lower = criterion.lower().strip()

                    if criterion_lower == "lint passed":
                        # Check if lint passed (reuse QualityGateChecker logic)
                        if runtime_profile and runtime_profile.quality_gates:
                            from backend.app.services.conversation.quality_gate_checker import QualityGateChecker
                            quality_checker = QualityGateChecker(
                                workspace_id=workspace.id if workspace else None,
                                project_path=None
                            )
                            lint_result = quality_checker._check_lint(changed_files)
                            if not lint_result.get("passed", False):
                                logger.warning(f"DefinitionOfDone: 'lint passed' failed: {lint_result.get('errors', [])}")
                                definition_of_done_passed = False
                        else:
                            logger.warning("DefinitionOfDone: 'lint passed' required but quality_gates not configured")
                            definition_of_done_passed = False

                    elif criterion_lower == "tests passed":
                        # Check if tests passed
                        if runtime_profile and runtime_profile.quality_gates:
                            from backend.app.services.conversation.quality_gate_checker import QualityGateChecker
                            quality_checker = QualityGateChecker(
                                workspace_id=workspace.id if workspace else None,
                                project_path=None
                            )
                            test_result = quality_checker._check_tests()
                            if not test_result.get("passed", False):
                                logger.warning(f"DefinitionOfDone: 'tests passed' failed: {test_result.get('errors', [])}")
                                definition_of_done_passed = False
                        else:
                            logger.warning("DefinitionOfDone: 'tests passed' required but quality_gates not configured")
                            definition_of_done_passed = False

                    elif criterion_lower == "docs updated":
                        # Check if docs were updated
                        doc_extensions = [".md", ".rst", ".txt"]
                        doc_dirs = ["docs", "doc", "documentation"]
                        has_doc_changes = False
                        if changed_files:
                            has_doc_changes = any(
                                any(ext in f for ext in doc_extensions) or
                                any(doc_dir in f for doc_dir in doc_dirs)
                                for f in changed_files
                            )
                        if not has_doc_changes:
                            logger.warning("DefinitionOfDone: 'docs updated' failed: No documentation files were modified")
                            definition_of_done_passed = False

                    else:
                        logger.warning(f"DefinitionOfDone: Unknown criterion '{criterion}', treating as passed")

            if not definition_of_done_passed:
                logger.error("DefinitionOfDone: Not all criteria passed. Execution marked as incomplete.")
                # Fail-close: raise exception to block completion
                raise ValueError(
                    f"DefinitionOfDone not met. Failed criteria: {stop_conditions.definition_of_done}. "
                    f"Execution cannot be marked as complete."
                )
            else:
                logger.info("DefinitionOfDone: All criteria passed")

            # Check QualityGates after execution (Phase 2)
            if runtime_profile and runtime_profile.quality_gates:
                try:
                    from backend.app.services.conversation.quality_gate_checker import QualityGateChecker

                    # Get changed files from execution results (if available)
                    changed_files = []
                    for executed_task in results.get("executed_tasks", []):
                        if isinstance(executed_task, dict) and executed_task.get("changed_files"):
                            changed_files.extend(executed_task["changed_files"])

                    # Get event store for event recording
                    from backend.app.services.stores.events_store import EventsStore
                    db_path = getattr(self.tasks_store, 'db_path', None)
                    event_store = EventsStore(db_path=db_path) if db_path else None

                    # Use primary execution_id (from first task launch) for event association
                    # This ensures quality gate events are properly associated with the execution
                    execution_id_for_quality = primary_execution_id
                    if not execution_id_for_quality and results.get("executed_tasks"):
                        # Fallback: try to get from first task if primary_execution_id not available
                        first_task = results["executed_tasks"][0]
                        if isinstance(first_task, dict):
                            execution_id_for_quality = first_task.get("execution_id")

                    # Create quality gate checker
                    quality_checker = QualityGateChecker(
                        workspace_id=workspace.id if workspace else None,
                        project_path=None,  # Will use current working directory
                        execution_id=execution_id_for_quality,
                        profile_id=getattr(runtime_profile, 'profile_id', None) if runtime_profile else None,
                        event_store=event_store
                    )

                    # Check quality gates
                    quality_result = quality_checker.check_quality_gates(
                        quality_gates=runtime_profile.quality_gates,
                        execution_result={"executed_tasks": results.get("executed_tasks", [])},
                        changed_files=changed_files if changed_files else None
                    )

                    if not quality_result.passed:
                        logger.error(
                            f"QualityGates: Failed gates: {quality_result.failed_gates}. "
                            f"Details: {quality_result.details}"
                        )
                        # Fail-close: raise exception to block execution completion
                        failed_gates_str = ", ".join(quality_result.failed_gates)
                        raise ValueError(
                            f"QualityGates not passed. Failed gates: {failed_gates_str}. "
                            f"Details: {quality_result.details}. "
                            f"Execution cannot be marked as complete."
                        )
                    else:
                        logger.info("QualityGates: All checks passed")
                except ValueError:
                    raise  # Re-raise quality gate failures
                except Exception as e:
                    logger.error(f"QualityGates check failed: {e}", exc_info=True)
                    # Fail-close: if quality gate check fails, block execution
                    raise ValueError(
                        f"QualityGates check encountered an error: {e}. "
                        f"Execution cannot be marked as complete."
                    )

        finally:
            # P3: Recycling Mechanism - Ensure cleanup even on exceptions
            # This finally block ensures orchestrator is cleaned up whether execution succeeds or fails
            if multi_agent_orchestrator:
                try:
                    from backend.app.services.orchestration.orchestrator_registry import get_orchestrator_registry
                    orchestrator_registry = get_orchestrator_registry()

                    # Use unregister_by_orchestrator to clean up all keys for this orchestrator instance
                    # This is safer than unregistering individual keys, as it handles duplicate registrations
                    # and ensures all keys (execution_id, message_id, trace_id) are cleaned up
                    orchestrator_registry.unregister_by_orchestrator(multi_agent_orchestrator)
                    logger.debug(
                        f"OrchestratorRegistry: Cleaned up orchestrator registrations "
                        f"(was registered with {len(registered_execution_ids)} keys: {registered_execution_ids})"
                    )
                except Exception as e:
                    logger.warning(f"Failed to cleanup orchestrator registrations: {e}", exc_info=True)

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
        ctx: LocalDomainContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        event_emitter: TaskEventsEmitter,
        execution_plan: Optional[ExecutionPlan] = None,
        multi_agent_orchestrator: Optional[Any] = None,  # Phase 2: MultiAgentOrchestrator for tracking
        registered_execution_ids: Optional[List[str]] = None,  # Phase 2: Track registered execution IDs
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

        try:
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
                    # Note: orchestrator is registered in OrchestratorRegistry and will be accessed by tool_executor via execution_id
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
                except Exception as e:
                    logger.error(f"Failed to launch execution: {e}", exc_info=True)
                    raise

                    execution_id = launch_result.get("execution_id")
                if not execution_id:
                    self.error_policy.handle_missing_execution_id(
                        resolved_playbook.code, launch_result.get("raw_result")
                    )

                # Track primary execution_id (from first task) for event association
                if execution_id and primary_execution_id is None:
                    primary_execution_id = execution_id

                # Phase 2: Update orchestrator registration with actual execution_id
                if execution_id and multi_agent_orchestrator:
                    # Update orchestrator with execution_id for event recording
                    multi_agent_orchestrator.execution_id = execution_id

                    from backend.app.services.orchestration.orchestrator_registry import get_orchestrator_registry
                    orchestrator_registry = get_orchestrator_registry()

                    # Register with actual execution_id (primary key)
                    # Only register if not already registered with this key (avoid duplicate registration)
                    if execution_id not in registered_execution_ids:
                        orchestrator_registry.register(execution_id, multi_agent_orchestrator)
                        registered_execution_ids.append(execution_id)
                        logger.info(
                            f"OrchestratorRegistry: Registered orchestrator for execution_id={execution_id} "
                            f"(tool_executor will use this key for tool_call counting)"
                        )
                    else:
                        logger.debug(f"OrchestratorRegistry: execution_id={execution_id} already registered, skipping duplicate")

                    # Also register with message_id as fallback (if not already registered)
                    # This ensures backward compatibility if some code paths use message_id
                    if message_id and message_id not in registered_execution_ids:
                        orchestrator_registry.register(message_id, multi_agent_orchestrator)
                        registered_execution_ids.append(message_id)
                        logger.debug(f"OrchestratorRegistry: Also registered with message_id={message_id} as fallback")

                    # Register trace_id if available (for tool_executor fallback)
                    trace_id = message_id  # Use message_id as trace_id (as per launch call)
                    if trace_id and trace_id not in registered_execution_ids:
                        orchestrator_registry.register(trace_id, multi_agent_orchestrator)
                        registered_execution_ids.append(trace_id)
                        logger.debug(f"OrchestratorRegistry: Also registered with trace_id={trace_id} as fallback")

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
            else:
                # Handle case when execution_plan is None
                return {
                    "pack_id": pack_id,
                    "playbook_code": resolved_playbook.code,
                    "execution_id": None,
                }

        except Exception as e:
            self.error_policy.handle_execution_error(
                f"launch playbook {resolved_playbook.code}", e, raise_on_error=True
            )

    async def _handle_execution_failure(
        self,
        task_plan,
        ctx: LocalDomainContext,
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
        ctx: LocalDomainContext,
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
