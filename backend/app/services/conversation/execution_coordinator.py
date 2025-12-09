"""
Execution Coordinator

Coordinates pack and playbook execution based on side_effect_level.
Handles readonly auto-execution, soft_write suggestion cards, and external_write confirmation.
"""

import logging
import sys
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import uuid

from ...models.workspace import Task, TaskStatus, TimelineItem, TimelineItemType, SideEffectLevel, ExecutionPlan, ExecutionSession
from ...models.mindscape import MindEvent, EventType, EventActor
from ...services.mindscape_store import MindscapeStore
from ...services.stores.tasks_store import TasksStore
from ...services.stores.timeline_items_store import TimelineItemsStore
from ...core.execution_context import ExecutionContext
from ...shared.llm_provider_helper import get_llm_provider_from_settings

logger = logging.getLogger(__name__)


class ExecutionCoordinator:
    """Coordinates pack and playbook execution based on side_effect_level"""

    def __init__(
        self,
        store: MindscapeStore,
        tasks_store: TasksStore,
        timeline_items_store: TimelineItemsStore,
        task_manager,
        plan_builder,
        playbook_runner,
        message_generator,
        default_locale: str = "en",
        playbook_service=None
    ):
        """
        Initialize ExecutionCoordinator

        Args:
            store: MindscapeStore instance
            tasks_store: TasksStore instance
            timeline_items_store: TimelineItemsStore instance
            task_manager: TaskManager instance
            plan_builder: PlanBuilder instance
            playbook_runner: PlaybookRunner instance
            message_generator: MessageGenerator instance
            default_locale: Default locale for i18n
            playbook_service: PlaybookService instance (optional, for unified query)
        """
        self.store = store
        self.tasks_store = tasks_store
        self.timeline_items_store = timeline_items_store
        self.task_manager = task_manager
        self.plan_builder = plan_builder
        self.playbook_runner = playbook_runner
        self.message_generator = message_generator
        self.default_locale = default_locale
        self.playbook_service = playbook_service
        from ...services.config_store import ConfigStore
        self.config_store = ConfigStore(db_path=store.db_path)
        from ...services.playbook_run_executor import PlaybookRunExecutor
        self.playbook_run_executor = PlaybookRunExecutor()

    async def execute_plan(
        self,
        execution_plan: ExecutionPlan,
        workspace_id: str,
        profile_id: str,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str] = None,
        task_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Execute execution plan based on side_effect_level

        Args:
            execution_plan: Execution plan with tasks
            workspace_id: Workspace ID
            profile_id: User profile ID
            message_id: Message/event ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID

        Returns:
            Dict with execution results
        """
        ctx = ExecutionContext(
            actor_id=profile_id,
            workspace_id=workspace_id,
            tags={"mode": "local"}
        )
        return await self.execute_plan_with_ctx(
            execution_plan=execution_plan,
            ctx=ctx,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id,
            task_event_callback=task_event_callback
        )

    async def execute_plan_with_ctx(
        self,
        execution_plan: ExecutionPlan,
        ctx: ExecutionContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str] = None,
        task_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        prevent_suggestion_creation: bool = False
    ) -> Dict[str, Any]:
        """
        Execute execution plan based on side_effect_level (using ExecutionContext)

        Args:
            execution_plan: Execution plan with tasks
            ctx: Execution context
            message_id: Message/event ID
            files: List of file IDs
            message: User message
            project_id: Optional project ID

        Returns:
            Dict with execution results
        """
        # Resolve Mind Lens if not already set
        # Mind Lens is a Cloud extension, accessed via API
        if ctx.mind_lens is None:
            try:
                import os
                import httpx
                cloud_api_url = os.getenv("CLOUD_API_URL")
                if cloud_api_url:
                    playbook_id = None
                    if execution_plan.tasks:
                        first_task = execution_plan.tasks[0]
                        playbook_id = getattr(first_task, 'playbook_id', None)

                    # Call Cloud API to resolve Mind Lens
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{cloud_api_url}/mind-lens/resolve",
                            json={
                                "user_id": ctx.actor_id,
                                "workspace_id": ctx.workspace_id,
                                "playbook_id": playbook_id,
                                "role_hint": None,
                            },
                            timeout=5.0,
                        )
                        if response.status_code == 200:
                            ctx.mind_lens = response.json()
            except Exception as e:
                # Mind Lens not available, continue without it
                logger.debug(f"Mind Lens not available: {e}")

        results = {
            "executed_tasks": [],
            "suggestion_cards": [],
            "skipped_tasks": []
        }

        # Store callback for task events
        self.task_event_callback = task_event_callback

        # Get workspace auto-execution config
        workspace = self.store.workspaces.get_workspace(ctx.workspace_id)
        auto_exec_config = workspace.playbook_auto_execution_config if workspace else None

        # Get execution mode settings for threshold adjustment
        execution_mode = getattr(workspace, 'execution_mode', None) or "qa"
        execution_priority = getattr(workspace, 'execution_priority', None) or "medium"

        # Import threshold utilities
        from backend.app.shared.execution_thresholds import get_threshold, should_auto_execute_readonly

        for task_plan in execution_plan.tasks:
            side_effect_level = self.plan_builder.determine_side_effect_level(task_plan.pack_id)

            # Check if playbook has custom auto-execution config
            should_auto_execute = task_plan.auto_execute

            # Get confidence from task_plan params (from LLM analysis)
            llm_confidence = task_plan.params.get('llm_analysis', {}).get('confidence', 0.0) if task_plan.params else 0.0

            # For execution/hybrid mode with READONLY tasks, use workspace's execution_priority
            if execution_mode in ("execution", "hybrid") and side_effect_level == SideEffectLevel.READONLY:
                should_auto_execute = should_auto_execute_readonly(execution_priority, llm_confidence)
                logger.info(f"ExecutionCoordinator: READONLY task {task_plan.pack_id} auto-execute={should_auto_execute} (execution_mode={execution_mode}, priority={execution_priority}, confidence={llm_confidence:.2f})")

            # Check playbook-specific config (can override workspace settings)
            elif auto_exec_config and task_plan.pack_id in auto_exec_config:
                playbook_config = auto_exec_config[task_plan.pack_id]
                # Use workspace execution_priority to adjust default threshold
                default_threshold = get_threshold(execution_priority)
                confidence_threshold = playbook_config.get('confidence_threshold', default_threshold)
                auto_execute_enabled = playbook_config.get('auto_execute', False)

                if auto_execute_enabled and llm_confidence >= confidence_threshold:
                    should_auto_execute = True
                    logger.info(f"ExecutionCoordinator: Playbook {task_plan.pack_id} meets auto-exec threshold (confidence={llm_confidence:.2f} >= {confidence_threshold:.2f})")
                else:
                    should_auto_execute = False
                    logger.info(f"ExecutionCoordinator: Playbook {task_plan.pack_id} does not meet auto-exec threshold (confidence={llm_confidence:.2f} < {confidence_threshold:.2f})")

            logger.info(f"ExecutionCoordinator: Processing task_plan {task_plan.pack_id}, side_effect_level={side_effect_level}, auto_execute={should_auto_execute}")
            print(f"ExecutionCoordinator: Processing task_plan {task_plan.pack_id}, side_effect_level={side_effect_level}, auto_execute={should_auto_execute}", file=sys.stderr)

            if should_auto_execute and side_effect_level == SideEffectLevel.READONLY:
                logger.info(f"ExecutionCoordinator: Executing READONLY task {task_plan.pack_id}")
                print(f"ExecutionCoordinator: Executing READONLY task {task_plan.pack_id}", file=sys.stderr)
                result = await self._execute_readonly_task(
                    task_plan, ctx, message_id, files, message, project_id, self.task_event_callback
                )
                if result:
                    results["executed_tasks"].append(result)
                    logger.info(f"ExecutionCoordinator: READONLY task {task_plan.pack_id} completed")
                    print(f"ExecutionCoordinator: READONLY task {task_plan.pack_id} completed", file=sys.stderr)
                else:
                    # If execution failed (e.g., unknown execution method), create suggestion card instead
                    pack_id_lower = task_plan.pack_id.lower() if task_plan.pack_id else ""

                    if pack_id_lower == "intent_extraction":
                        logger.error(
                            f"ExecutionCoordinator: intent_extraction execution failed in fallback path. "
                            f"This should not happen - intent_extraction should be handled by IntentInfraService."
                        )
                        print(
                            f"ExecutionCoordinator: ERROR - intent_extraction reached fallback path. "
                            f"This indicates a routing issue.",
                            file=sys.stderr
                        )
                        # Don't create suggestion card to avoid infinite loop
                        results["skipped_tasks"].append(task_plan.pack_id)
                    else:
                        # Check if there's already a pending task for this pack_id to avoid infinite loop
                        pending_tasks = self.tasks_store.list_pending_tasks(ctx.workspace_id, exclude_cancelled=True)
                        existing_pending = [t for t in pending_tasks if t.pack_id == task_plan.pack_id]

                        if existing_pending:
                            logger.warning(
                                f"ExecutionCoordinator: READONLY task {task_plan.pack_id} execution failed, "
                                f"but there's already a pending task ({existing_pending[0].id}). "
                                f"Skipping suggestion card creation to avoid infinite loop."
                            )
                            print(
                                f"ExecutionCoordinator: WARNING - {task_plan.pack_id} already has pending task, skipping",
                                file=sys.stderr
                            )
                            # Don't create suggestion card to avoid infinite loop
                            results["skipped_tasks"].append(task_plan.pack_id)
                        else:
                            logger.info(f"ExecutionCoordinator: READONLY task {task_plan.pack_id} execution failed, creating suggestion card")
                            print(f"ExecutionCoordinator: READONLY task {task_plan.pack_id} execution failed, creating suggestion card", file=sys.stderr)
                            suggestion = await self._create_suggestion_card(
                                task_plan, ctx.workspace_id, message_id
                            )
                            if suggestion:
                                results["suggestion_cards"].append(suggestion)
                                logger.info(f"ExecutionCoordinator: Suggestion card created for {task_plan.pack_id} (fallback from failed execution)")
                                print(f"ExecutionCoordinator: Suggestion card created for {task_plan.pack_id} (fallback from failed execution)", file=sys.stderr)

            elif side_effect_level == SideEffectLevel.SOFT_WRITE:
                # Check if should auto-execute based on workspace config
                should_auto_execute_soft = False
                if auto_exec_config and task_plan.pack_id in auto_exec_config:
                    playbook_config = auto_exec_config[task_plan.pack_id]
                    confidence_threshold = playbook_config.get('confidence_threshold', 0.8)
                    auto_execute_enabled = playbook_config.get('auto_execute', False)

                    llm_confidence = task_plan.params.get('llm_analysis', {}).get('confidence', 0.0) if task_plan.params else 0.0

                    if auto_execute_enabled and llm_confidence >= confidence_threshold:
                        should_auto_execute_soft = True
                        logger.info(f"ExecutionCoordinator: SOFT_WRITE playbook {task_plan.pack_id} meets auto-exec threshold (confidence={llm_confidence:.2f} >= {confidence_threshold:.2f}), executing directly")
                        # Execute directly (even though it's SOFT_WRITE, user has configured auto-exec)
                        # For playbooks, use execute_playbook which will handle side_effect_level
                        # But we need to force execution by temporarily treating it as READONLY
                        # Actually, we should use _execute_readonly_playbook directly for auto-exec
                        playbook_context = task_plan.params.get('context', task_plan.params.copy() if task_plan.params else {})
                        if task_plan.params:
                            playbook_context.update(task_plan.params)

                        # Execute playbook directly (bypassing suggestion card creation)
                        playbook_result = await self._execute_readonly_playbook(
                            playbook_code=task_plan.pack_id,
                            playbook_context=playbook_context,
                            ctx=ctx,
                            message_id=message_id,
                            project_id=project_id
                        )
                        if playbook_result:
                            results["executed_tasks"].append(playbook_result)
                        continue

                logger.info(f"ExecutionCoordinator: Creating suggestion card for SOFT_WRITE task {task_plan.pack_id}")
                print(f"ExecutionCoordinator: Creating suggestion card for SOFT_WRITE task {task_plan.pack_id}", file=sys.stderr)
                suggestion = await self._create_suggestion_card(
                    task_plan, ctx.workspace_id, message_id
                )
                if suggestion:
                    results["suggestion_cards"].append(suggestion)
                    logger.info(f"ExecutionCoordinator: Suggestion card created for {task_plan.pack_id}")
                    print(f"ExecutionCoordinator: Suggestion card created for {task_plan.pack_id}", file=sys.stderr)

            elif side_effect_level == SideEffectLevel.EXTERNAL_WRITE:
                # EXTERNAL_WRITE tasks should also create suggestion cards (like SOFT_WRITE)
                # They require explicit confirmation, so show as suggestion
                logger.info(f"ExecutionCoordinator: Creating suggestion card for EXTERNAL_WRITE task {task_plan.pack_id}")
                print(f"ExecutionCoordinator: Creating suggestion card for EXTERNAL_WRITE task {task_plan.pack_id}", file=sys.stderr)
                suggestion = await self._create_suggestion_card(
                    task_plan, ctx.workspace_id, message_id
                )
                if suggestion:
                    results["suggestion_cards"].append(suggestion)
                    logger.info(f"ExecutionCoordinator: Suggestion card created for {task_plan.pack_id}")
                    print(f"ExecutionCoordinator: Suggestion card created for {task_plan.pack_id}", file=sys.stderr)
                else:
                    logger.warning(f"Failed to create suggestion card for EXTERNAL_WRITE task {task_plan.pack_id}")
                    results["skipped_tasks"].append(task_plan.pack_id)

        return results

    async def _execute_readonly_task(
        self,
        task_plan,
        ctx: ExecutionContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        task_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute readonly task automatically"""
        pack_id = task_plan.pack_id
        pack_id_lower = pack_id.lower() if pack_id else ""

        if pack_id_lower == "intent_extraction":
            logger.error(
                f"ExecutionCoordinator: intent_extraction should not reach _execute_readonly_task. "
                f"This indicates a routing issue. Task should be handled by IntentInfraService in SuggestionActionHandler."
            )
            print(
                f"ExecutionCoordinator: ERROR - intent_extraction reached _execute_readonly_task. "
                f"This should be handled by IntentInfraService.",
                file=sys.stderr
            )
            raise ValueError(
                f"intent_extraction should be handled by IntentInfraService, not ExecutionCoordinator. "
                f"Check SuggestionActionHandler priority handling logic."
            )

        # Check execution method: PlaybookService handles playbooks, CapabilityRegistry handles capability packs
        execution_method = None

        # Check PlaybookService first - it handles all playbooks (system, capability, user)
        logger.info(f"ExecutionCoordinator: Checking PlaybookService for {pack_id}, playbook_service={self.playbook_service is not None}, default_locale={self.default_locale}, type={type(self.default_locale)}")
        if self.playbook_service:
            try:
                playbook = await self.playbook_service.get_playbook(
                    playbook_code=pack_id,
                    locale=self.default_locale,
                    workspace_id=ctx.workspace_id
                )
                if playbook:
                    execution_method = 'playbook'
                    logger.info(f"ExecutionCoordinator: Pack {pack_id} found in PlaybookService, execution method: {execution_method}")
                else:
                    logger.info(f"ExecutionCoordinator: Pack {pack_id} not found in PlaybookService (returned None)")
            except Exception as e:
                logger.warning(f"ExecutionCoordinator: Playbook {pack_id} error in PlaybookService: {type(e).__name__}: {e}", exc_info=True)
        else:
            logger.warning(f"ExecutionCoordinator: playbook_service is None, skipping PlaybookService check for {pack_id}")

        # If not a playbook, check CapabilityRegistry for pack_executor
        if not execution_method:
            from ...capabilities.registry import get_registry
            registry = get_registry()
            execution_method = registry.get_execution_method(pack_id)
            logger.info(f"ExecutionCoordinator: Pack {pack_id} execution method from CapabilityRegistry: {execution_method}")

        # Handle hardcoded pack executors first (for backward compatibility)
        # Note: daily_planning has been migrated to playbook architecture
        if pack_id == "semantic_seeds":
            # Allow execution even without files (can extract from message)
            # TODO: Consider migrating to playbook architecture if needed
            return await self._execute_semantic_seeds(
                ctx.workspace_id, ctx.actor_id, message_id, files, message, task_event_callback
            )
        # Handle dynamic execution methods
        if execution_method == 'playbook':
            # Execute via playbook
            return await self._execute_pack_via_playbook(
                pack_id, task_plan, ctx, message_id, files, message, project_id
            )
        elif execution_method == 'pack_executor':
            # Try to load and execute pack executor dynamically
            logger.warning(f"Pack {pack_id} has pack_executor but no hardcoded handler in _execute_readonly_task")
            # For now, fall back to creating suggestion card
            return None

        logger.warning(f"Unknown execution method for pack {pack_id}: {execution_method}")
        return None

    async def _execute_pack_via_playbook(
        self,
        pack_id: str,
        task_plan,
        ctx: ExecutionContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Execute pack via playbook for readonly tasks"""
        try:
            from ...capabilities.registry import get_registry

            registry = get_registry()
            playbook_code = None

            # Use PlaybookService if available, otherwise fallback to PlaybookLoader
            if self.playbook_service:
                # Use unified PlaybookService
                from ...services.playbook_service import PlaybookService
                playbook_service = self.playbook_service
            else:
                # Backward compatibility: use PlaybookLoader
                from ...services.playbook_loader import PlaybookLoader
                playbook_loader = PlaybookLoader()
                playbook_service = None

            # Determine if pack_id is a capability pack or system-level playbook
            capability = registry.get_capability(pack_id)
            capability_playbooks = registry.get_capability_playbooks(pack_id) if capability else []

            if capability and capability_playbooks:
                # Pack is a capability pack - load from capability pack playbooks
                logger.debug(f"Pack {pack_id} is a capability pack, loading from capability playbooks")
                playbook_codes_to_try = []
                for playbook_filename in capability_playbooks:
                    base_name = playbook_filename.replace('.yaml', '').replace('.yml', '')
                    if base_name not in playbook_codes_to_try:
                        playbook_codes_to_try.append(base_name)

                for code in playbook_codes_to_try:
                    try:
                        if playbook_service:
                            playbook = await playbook_service.get_playbook(
                                code,
                                locale=self.default_locale,
                                workspace_id=ctx.workspace_id
                            )
                        else:
                            playbook = playbook_loader.get_playbook_by_code(code, locale=self.default_locale)
                        if playbook:
                            playbook_code = code
                            logger.info(f"Found playbook {playbook_code} for capability pack {pack_id}")
                            break
                    except Exception:
                        continue
            else:
                # Pack is not a capability pack - try as system-level playbook
                logger.debug(f"Pack {pack_id} is not a capability pack, trying as system-level playbook")
                try:
                    if playbook_service:
                        playbook = await playbook_service.get_playbook(
                            pack_id,
                            locale=self.default_locale,
                            workspace_id=ctx.workspace_id
                        )
                    else:
                        playbook = playbook_loader.get_playbook_by_code(pack_id, locale=self.default_locale)
                    if playbook:
                        playbook_code = pack_id
                        logger.info(f"Found system-level playbook {playbook_code} for pack {pack_id}")
                except Exception as e:
                    logger.debug(f"Failed to load system-level playbook {pack_id}: {e}")

            if not playbook_code:
                logger.warning(f"Could not find executable playbook for pack {pack_id} (capability pack: {capability is not None}, system-level: not found)")
                return None

            # Execute playbook
            logger.info(f"ExecutionCoordinator: Starting playbook execution for pack {pack_id}, playbook_code={playbook_code}, workspace_id={ctx.workspace_id}, message_id={message_id}")
            try:
                execution_result = await self.playbook_runner.start_playbook_execution(
                    playbook_code=playbook_code,
                    profile_id=ctx.actor_id,
                    inputs={
                        **(task_plan.params if task_plan.params else {}),
                        "files": files,
                        "message": message,
                        "message_id": message_id
                    },
                    workspace_id=ctx.workspace_id
                )

                execution_id = execution_result.get("execution_id") if execution_result else None
                if execution_id:
                    logger.info(f"ExecutionCoordinator: Playbook {playbook_code} started successfully, execution_id={execution_id}")
                else:
                    logger.warning(f"ExecutionCoordinator: Playbook {playbook_code} started but no execution_id returned. Result: {execution_result}")

                if hasattr(self, 'task_event_callback') and self.task_event_callback:
                    try:
                        task = self.tasks_store.get_task_by_execution_id(execution_id) if execution_id else None
                        if task:
                            self.task_event_callback('created', {
                                'id': task.id,
                                'pack_id': pack_id,
                                'playbook_code': playbook_code,
                                'status': task.status.value if hasattr(task.status, 'value') else str(task.status),
                                'task_type': task.task_type,
                                'workspace_id': ctx.workspace_id,
                                'execution_id': execution_id
                            })
                        elif execution_id:
                            self.task_event_callback('created', {
                                'id': execution_id,
                                'pack_id': pack_id,
                                'playbook_code': playbook_code,
                                'status': 'running',
                                'task_type': 'playbook_execution',
                                'workspace_id': ctx.workspace_id,
                                'execution_id': execution_id
                            })
                    except Exception as e:
                        logger.warning(f"Failed to call task_event_callback for pack {pack_id}: {e}")

                return {
                    "pack_id": pack_id,
                    "playbook_code": playbook_code,
                    "execution_id": execution_id
                }
            except Exception as playbook_error:
                logger.error(
                    f"ExecutionCoordinator: Failed to start playbook execution for pack {pack_id}, "
                    f"playbook_code={playbook_code}: {playbook_error}",
                    exc_info=True
                )
                raise
        except Exception as e:
            logger.error(
                f"ExecutionCoordinator: Failed to execute pack {pack_id} via playbook {playbook_code}: {e}",
                exc_info=True
            )
            return None

    async def _execute_semantic_seeds(
        self,
        workspace_id: str,
        profile_id: str,
        message_id: str,
        files: List[str],
        message: str,
        task_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute semantic_seeds pack - can work with or without files"""
        try:
            pack_id = "semantic_seeds"

            # Allow execution even without files - can extract from message
            # If no files, use message content for intent extraction

            task = Task(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=message_id,
                execution_id=None,
                pack_id=pack_id,
                task_type="extract_intents",
                status=TaskStatus.RUNNING,
                params={
                    "files": files,
                    "message": message
                },
                result=None,
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                completed_at=None,
                error=None
            )
            self.tasks_store.create_task(task)
            logger.info(f"ExecutionCoordinator: Created RUNNING task {task.id} for semantic_seeds (pack_id={pack_id}, workspace={workspace_id})")
            print(f"ExecutionCoordinator: Created RUNNING task {task.id} for semantic_seeds (pack_id={pack_id}, workspace={workspace_id})", file=sys.stderr)

            # Notify about task creation if callback provided
            if task_event_callback:
                try:
                    task_event_callback('created', {
                        'id': task.id,
                        'pack_id': pack_id,
                        'status': task.status.value,
                        'task_type': task.task_type,
                        'workspace_id': workspace_id
                    })
                except Exception as e:
                    logger.warning(f"Failed to call task_event_callback: {e}")

            extracted_intents = []
            file_contents = []

            try:
                if self.timeline_items_store:
                    recent_timeline_items = self.timeline_items_store.list_timeline_items_by_workspace(
                        workspace_id=workspace_id,
                        limit=10
                    )
                    for item in recent_timeline_items:
                        if item.type == TimelineItemType.INTENT_SEEDS:
                            item_data = item.data if isinstance(item.data, dict) else {}
                            if 'intents' in item_data:
                                intents_list = item_data.get('intents', [])
                                if isinstance(intents_list, list):
                                    for intent_obj in intents_list:
                                        if isinstance(intent_obj, dict):
                                            intent_text = intent_obj.get('title') or intent_obj.get('text') or str(intent_obj)
                                        else:
                                            intent_text = str(intent_obj)
                                        if intent_text and intent_text not in extracted_intents:
                                            extracted_intents.append(intent_text)
                                logger.info(f"Found {len(intents_list)} intents from IntentExtractor timeline_item {item.id}")
            except Exception as e:
                logger.warning(f"Failed to get intents from timeline_items: {e}")

            recent_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=50
            )

            for event in recent_events:
                if event.event_type == EventType.MESSAGE:
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    metadata = event.metadata if isinstance(event.metadata, dict) else {}

                    file_analysis = metadata.get('file_analysis', {})
                    collaboration = file_analysis.get('collaboration_results', {})
                    semantic_seeds = collaboration.get('semantic_seeds', {})

                    if semantic_seeds.get('enabled') and semantic_seeds.get('intents'):
                        intents = semantic_seeds.get('intents', [])
                        for intent in intents:
                            intent_text = intent if isinstance(intent, str) else (intent.get('title') or intent.get('text') or str(intent))
                            if intent_text and intent_text not in extracted_intents:
                                extracted_intents.append(intent_text)

                        analysis = file_analysis.get('analysis', {})
                        file_info = analysis.get('file_info', {})
                        if file_info.get('text_content'):
                            file_contents.append(file_info['text_content'])

            if not extracted_intents and file_contents:
                try:
                    from ...capabilities.semantic_seeds.services.seed_extractor import SeedExtractor
                    from ...services.agent_runner import LLMProviderManager
                    import os

                    # Get LLM API keys from user config (stored in settings), fallback to unified function
                    from backend.app.shared.llm_provider_helper import create_llm_provider_manager
                    config = self.config_store.get_or_create_config(profile_id)
                    llm_manager = create_llm_provider_manager(
                        openai_key=config.agent_backend.openai_api_key,
                        anthropic_key=config.agent_backend.anthropic_api_key,
                        vertex_api_key=config.agent_backend.vertex_api_key,
                        vertex_project_id=config.agent_backend.vertex_project_id,
                        vertex_location=config.agent_backend.vertex_location
                    )
                    llm_provider = get_llm_provider_from_settings(llm_manager)

                    if llm_provider:
                        extractor = SeedExtractor(llm_provider=llm_provider)

                        combined_content = "\n\n".join(file_contents[:3])

                        seeds = await extractor.extract_seeds_from_content(
                            user_id=profile_id,
                            content=combined_content,
                            source_type="conversation",
                            source_id=message_id,
                            source_context=message
                        )

                        extracted_intents = [seed.get('text', '') for seed in seeds if seed.get('type') in ['intent', 'project']]
                except Exception as e:
                    logger.warning(f"Failed to extract seeds from files: {e}")

            if not extracted_intents and not file_contents and message:
                try:
                    from ...capabilities.semantic_seeds.services.seed_extractor import SeedExtractor
                    from ...services.agent_runner import LLMProviderManager
                    import os

                    # Get LLM API keys from user config (stored in settings), fallback to unified function
                    from backend.app.shared.llm_provider_helper import create_llm_provider_manager
                    config = self.config_store.get_or_create_config(profile_id)
                    llm_manager = create_llm_provider_manager(
                        openai_key=config.agent_backend.openai_api_key,
                        anthropic_key=config.agent_backend.anthropic_api_key,
                        vertex_api_key=config.agent_backend.vertex_api_key,
                        vertex_project_id=config.agent_backend.vertex_project_id,
                        vertex_location=config.agent_backend.vertex_location
                    )
                    llm_provider = get_llm_provider_from_settings(llm_manager)

                    if llm_provider:
                        extractor = SeedExtractor(llm_provider=llm_provider)
                        seeds = await extractor.extract_seeds_from_content(
                            user_id=profile_id,
                            content=message,
                            source_type="conversation",
                            source_id=message_id,
                            source_context=message
                        )
                        extracted_intents = [seed.get('text', '') for seed in seeds if seed.get('type') in ['intent', 'project']]
                        logger.info(f"Extracted {len(extracted_intents)} intents from message content")
                except Exception as e:
                    logger.warning(f"Failed to extract seeds from message: {e}", exc_info=True)

            if files:
                title = f"Extracted {len(extracted_intents)} intents from {len(files)} file(s)"
                summary = f"Found {len(extracted_intents)} potential intents or projects from files"
                result_message = f"Extracted {len(extracted_intents)} intents from uploaded files"
            else:
                title = f"Extracted {len(extracted_intents)} intents from message"
                summary = f"Found {len(extracted_intents)} potential intents or projects from message"
                result_message = f"Extracted {len(extracted_intents)} intents from message"

            execution_result = {
                "title": title,
                "summary": summary,
                "message": result_message,
                "intents": extracted_intents[:5],
                "files_processed": len(files),
                "source": "files" if files else "message"
            }

            self.tasks_store.update_task_status(
                task_id=task.id,
                status=TaskStatus.SUCCEEDED,
                result=execution_result,
                completed_at=datetime.utcnow()
            )
            logger.info(f"ExecutionCoordinator: Updated task {task.id} to SUCCEEDED")
            print(f"ExecutionCoordinator: Updated task {task.id} to SUCCEEDED", file=sys.stderr)

            # Notify about task update if callback provided
            if hasattr(self, 'task_event_callback') and self.task_event_callback:
                try:
                    self.task_event_callback('updated', {
                        'id': task.id,
                        'pack_id': pack_id,
                        'status': 'SUCCEEDED',
                        'task_type': task.task_type,
                        'workspace_id': workspace_id
                    })
                except Exception as e:
                    logger.warning(f"Failed to call task_event_callback: {e}")

            timeline_item = self.task_manager.create_timeline_item_from_task(
                task=task,
                execution_result=execution_result,
                playbook_code=pack_id
            )
            if timeline_item:
                logger.info(f"ExecutionCoordinator: Created TimelineItem {timeline_item.id} for completed task")
                print(f"ExecutionCoordinator: Created TimelineItem {timeline_item.id} for completed task", file=sys.stderr)

            logger.info(f"ExecutionCoordinator: Completed semantic_seeds task: {task.id}, created {len(extracted_intents)} intents")
            print(f"ExecutionCoordinator: Completed semantic_seeds task: {task.id}, created {len(extracted_intents)} intents", file=sys.stderr)
            return {"task": task, "pack_id": pack_id}
        except Exception as e:
            logger.error(f"Failed to execute semantic_seeds: {e}", exc_info=True)
            if 'task' in locals():
                try:
                    self.tasks_store.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=str(e),
                        completed_at=datetime.utcnow()
                    )
                except Exception:
                    pass
            return None

    def _should_create_new_suggestion_task(
        self,
        existing_tasks: List[Task],
        task_plan
    ) -> bool:
        """
        Determine if a new suggestion task should be created

        Args:
            existing_tasks: List of existing suggestion tasks with same pack_id
            task_plan: New task plan to compare against

        Returns:
            True if new task should be created, False if duplicate exists
        """
        if not existing_tasks:
            return True

        new_params_source = task_plan.params.get('source', '')
        new_params_files = task_plan.params.get('files', [])

        for existing_task in existing_tasks:
            existing_params = existing_task.params or {}
            existing_source = existing_params.get('source', '')
            existing_files = existing_params.get('files', [])

            # Compare params to determine if tasks are similar
            source_match = new_params_source == existing_source
            files_match = set(new_params_files) == set(existing_files)

            # If source and files are the same, consider it a duplicate
            if source_match and files_match:
                logger.info(f"Found duplicate suggestion task {existing_task.id} for pack {task_plan.pack_id}, skipping creation")
                return False

        return True

    async def _create_suggestion_card(
        self,
        task_plan,
        workspace_id: str,
        message_id: str
    ) -> Optional[Dict[str, Any]]:
        """Create suggestion card for soft_write task"""
        try:
            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)

            # Validate playbook exists before creating suggestion task
            # This prevents creating tasks for invalid playbook codes from LLM
            pack_id = task_plan.pack_id
            if pack_id:
                # Check if pack_id is a valid playbook or capability pack
                is_valid = False

                # Check PlaybookService first
                if self.playbook_service:
                    try:
                        playbook = await self.playbook_service.get_playbook(
                            playbook_code=pack_id,
                            locale=self.default_locale,
                            workspace_id=workspace_id
                        )
                        if playbook:
                            is_valid = True
                            logger.info(f"ExecutionCoordinator: Pack {pack_id} validated as playbook")
                    except Exception as e:
                        logger.debug(f"ExecutionCoordinator: Pack {pack_id} not found in PlaybookService: {e}")

                # If not a playbook, check CapabilityRegistry
                if not is_valid:
                    from ...capabilities.registry import get_registry
                    registry = get_registry()
                    execution_method = registry.get_execution_method(pack_id)
                    if execution_method in ['playbook', 'pack_executor']:
                        is_valid = True
                        logger.info(f"ExecutionCoordinator: Pack {pack_id} validated as capability pack (execution_method={execution_method})")

                # Special cases: intent_extraction and semantic_seeds are valid even if not in registry
                pack_id_lower = pack_id.lower()
                if pack_id_lower in ["intent_extraction", "semantic_seeds"]:
                    is_valid = True
                    logger.info(f"ExecutionCoordinator: Pack {pack_id} validated as special pack")

                # If pack_id is invalid, skip creating suggestion task
                if not is_valid:
                    logger.warning(
                        f"ExecutionCoordinator: Skipping suggestion task creation for invalid pack_id: {pack_id}. "
                        f"This pack is not in the playbook list and cannot be executed."
                    )
                    print(
                        f"ExecutionCoordinator: WARNING - Skipping invalid pack_id: {pack_id}",
                        file=sys.stderr
                    )
                    return {
                        "task_id": None,
                        "timeline_item_id": None,
                        "pack_id": pack_id,
                        "skipped": True,
                        "reason": "invalid_playbook_code"
                    }

            # Check user preference for this pack/task_type
            from ...services.stores.task_preference_store import TaskPreferenceStore
            from ...services.mindscape_store import MindscapeStore
            store = MindscapeStore()
            preference_store = TaskPreferenceStore(store.db_path)

            # Get workspace to get owner_user_id
            workspace = store.get_workspace(workspace_id)
            if workspace:
                should_auto_suggest = preference_store.should_auto_suggest(
                    workspace_id=workspace_id,
                    user_id=workspace.owner_user_id,
                    pack_id=task_plan.pack_id,
                    task_type=task_plan.task_type
                )

                if not should_auto_suggest:
                    logger.info(
                        f"Skipping suggestion task creation for pack {task_plan.pack_id} "
                        f"(auto_suggest disabled by user preference)"
                    )
                    return {
                        "task_id": None,
                        "timeline_item_id": None,
                        "pack_id": task_plan.pack_id,
                        "skipped": True,
                        "reason": "auto_suggest_disabled"
                    }

            # Check for existing suggestion tasks with same pack_id
            existing_tasks = self.tasks_store.find_existing_suggestion_tasks(
                workspace_id=workspace_id,
                pack_id=task_plan.pack_id,
                created_within_hours=1
            )

            # Check if we should create a new task or reuse existing one
            if not self._should_create_new_suggestion_task(existing_tasks, task_plan):
                # Return existing task info instead of creating new one
                existing_task = existing_tasks[0]
                logger.info(f"Reusing existing suggestion task {existing_task.id} for pack {task_plan.pack_id}")
                return {
                    "task_id": existing_task.id,
                    "timeline_item_id": None,
                    "pack_id": task_plan.pack_id,
                    "is_duplicate": True
                }

            # Extract LLM analysis from params if available
            llm_analysis = task_plan.params.get("llm_analysis", {}) if task_plan.params else {}

            # Check if this is a background playbook that auto-executes (doesn't require LLM analysis)
            # These playbooks run automatically in the background and don't need user confirmation
            background_playbooks = ["habit_learning"]
            is_background_playbook = task_plan.pack_id.lower() in [p.lower() for p in background_playbooks]

            # Ensure llm_analysis has all required fields with defaults
            if not llm_analysis:
                llm_analysis = {}
            if "confidence" not in llm_analysis:
                # Background playbooks don't need LLM confidence, but we still set it to 0.0 to indicate no LLM analysis
                llm_analysis["confidence"] = 0.0
            if "reason" not in llm_analysis:
                # For background playbooks, set a default reason explaining it's auto-executed
                if is_background_playbook:
                    llm_analysis["reason"] = "This task will be executed automatically in the background, no LLM analysis needed"
                else:
                    llm_analysis["reason"] = ""
            if "content_tags" not in llm_analysis:
                llm_analysis["content_tags"] = []
            if "analysis_summary" not in llm_analysis:
                if is_background_playbook:
                    llm_analysis["analysis_summary"] = "Background auto-execution task"
                else:
                    llm_analysis["analysis_summary"] = ""

            # Mark as background playbook in llm_analysis for frontend to handle differently
            if is_background_playbook:
                llm_analysis["is_background"] = True

            suggestion_task = Task(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=message_id,
                execution_id=None,
                pack_id=task_plan.pack_id,
                task_type="suggestion",
                status=TaskStatus.PENDING,
                params=task_plan.params,
                result={
                    "suggestion": True,
                    "pack_id": task_plan.pack_id,
                    "requires_cta": True,
                    "llm_analysis": llm_analysis  # Include LLM analysis in result for frontend
                },
                created_at=datetime.utcnow(),
                started_at=None,
                completed_at=None,
                error=None
            )
            self.tasks_store.create_task(suggestion_task)
            logger.info(f"ExecutionCoordinator: Created suggestion task {suggestion_task.id} (status=PENDING) for {task_plan.pack_id}")
            print(f"ExecutionCoordinator: Created suggestion task {suggestion_task.id} (status=PENDING) for {task_plan.pack_id}", file=sys.stderr)

            # Notify about task creation if callback provided
            if hasattr(self, 'task_event_callback') and self.task_event_callback:
                try:
                    self.task_event_callback('created', {
                        'id': suggestion_task.id,
                        'pack_id': task_plan.pack_id,
                        'status': suggestion_task.status.value,
                        'task_type': suggestion_task.task_type,
                        'workspace_id': workspace_id
                    })
                except Exception as e:
                    logger.warning(f"Failed to call task_event_callback: {e}")

            item_type = TimelineItemType.PLAN
            cta_action = "execute_pack"
            cta_label = i18n.t("conversation_orchestrator", "suggestion.cta_add")

            pack_id_lower = task_plan.pack_id.lower()
            if "semantic_seeds" in pack_id_lower or "intent" in pack_id_lower:
                item_type = TimelineItemType.INTENT_SEEDS
                cta_action = "add_to_intents"
            elif "daily_planning" in pack_id_lower or "habit_learning" in pack_id_lower or "task" in pack_id_lower or "plan" in pack_id_lower:
                item_type = TimelineItemType.PLAN
                cta_action = "add_to_tasks"

            suggestion_message = await self.message_generator.generate_suggestion_message(
                pack_id=task_plan.pack_id,
                task_result=suggestion_task.result,
                timeline_item={
                    "title": f"Suggested: {task_plan.pack_id}",
                    "summary": "",
                    "data": task_plan.params
                },
                locale=self.default_locale
            )

            # Don't create TimelineItem for suggestions - they should only appear in Timeline after execution
            # The suggestion task will show in PendingTasksPanel, and when user clicks CTA,
            # a new TimelineItem will be created by CTAHandler after execution
            logger.info(f"ExecutionCoordinator: Created suggestion task (no TimelineItem) for soft_write task: {task_plan.pack_id}, requires CTA")
            print(f"ExecutionCoordinator: Created suggestion task (no TimelineItem) for soft_write task: {task_plan.pack_id}", file=sys.stderr)

            return {
                "task_id": suggestion_task.id,
                "timeline_item_id": None,
                "pack_id": task_plan.pack_id
            }
        except Exception as e:
            logger.error(f"Failed to create suggestion card: {e}", exc_info=True)
            return None

    async def execute_playbook(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        workspace_id: str,
        profile_id: str,
        message_id: str,
        project_id: Optional[str]
    ) -> Dict[str, Any]:
        """
        Execute playbook based on side_effect_level

        Args:
            playbook_code: Playbook code
            playbook_context: Playbook context
            workspace_id: Workspace ID
            profile_id: User profile ID
            message_id: Message/event ID
            project_id: Optional project ID

        Returns:
            Dict with execution result
        """
        ctx = ExecutionContext(
            actor_id=profile_id,
            workspace_id=workspace_id,
            tags={"mode": "local"}
        )
        return await self.create_execution_with_ctx(
            playbook_code=playbook_code,
            playbook_context=playbook_context,
            ctx=ctx,
            message_id=message_id,
            project_id=project_id
        )

    async def create_execution_with_ctx(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        ctx: ExecutionContext,
        message_id: str,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create execution based on side_effect_level and from_suggestion_action flag

        Args:
            playbook_code: Playbook code
            playbook_context: Playbook context (may contain from_suggestion_action flag)
            ctx: Execution context
            message_id: Message/event ID
            project_id: Optional project ID

        Returns:
            Dict with execution result (status: "started" or "suggestion")
        """
        # Determine side_effect_level
        side_effect_level = self.plan_builder.determine_side_effect_level(playbook_code)

        # Check if this is from suggestion action (user confirmed execution)
        from_suggestion_action = playbook_context.get("from_suggestion_action", False)

        logger.info(f"ExecutionCoordinator.create_execution_with_ctx: playbook={playbook_code}, side_effect_level={side_effect_level}, from_suggestion_action={from_suggestion_action}")

        # If from_suggestion_action=True, execute directly (user confirmed)
        # Otherwise, check side_effect_level
        if from_suggestion_action:
            # User confirmed execution, execute directly regardless of side_effect_level
            logger.info(f"ExecutionCoordinator: Executing playbook {playbook_code} directly (user confirmed from suggestion)")
            result = await self._execute_readonly_playbook(
                playbook_code=playbook_code,
                playbook_context=playbook_context,
                ctx=ctx,
                message_id=message_id,
                project_id=project_id
            )
            return {
                "status": "started",
                "execution_id": result.get("execution_id"),
                "task_id": result.get("task_id")
            }
        elif side_effect_level == SideEffectLevel.READONLY:
            # READONLY: execute directly
            logger.info(f"ExecutionCoordinator: Executing READONLY playbook {playbook_code} directly")
            result = await self._execute_readonly_playbook(
                playbook_code=playbook_code,
                playbook_context=playbook_context,
                ctx=ctx,
                message_id=message_id,
                project_id=project_id
            )
            return {
                "status": "started",
                "execution_id": result.get("execution_id"),
                "task_id": result.get("task_id")
            }
        else:
            # SOFT_WRITE or EXTERNAL_WRITE: create suggestion card
            logger.info(f"ExecutionCoordinator: Creating suggestion card for {side_effect_level} playbook {playbook_code}")
            result = await self._create_playbook_suggestion(
                playbook_code=playbook_code,
                playbook_context=playbook_context,
                ctx=ctx,
                message_id=message_id
            )
            return {
                "status": "suggestion",
                "task_id": result.get("task_id")
            }

    async def _execute_readonly_playbook(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        ctx: ExecutionContext,
        message_id: str,
        project_id: Optional[str]
    ) -> Dict[str, Any]:
        """Execute readonly playbook automatically"""
        try:
            playbook_inputs = playbook_context.copy()
            playbook_inputs["workspace_id"] = ctx.workspace_id

            # Use PlaybookService if available, otherwise fallback to PlaybookRunExecutor
            if self.playbook_service:
                from ...services.playbook_service import ExecutionMode as PlaybookExecutionMode
                execution_result_obj = await self.playbook_service.execute_playbook(
                    playbook_code=playbook_code,
                    workspace_id=ctx.workspace_id,
                    profile_id=ctx.actor_id,
                    inputs=playbook_inputs,
                    execution_mode=PlaybookExecutionMode.ASYNC,
                    locale=self.default_locale
                )
                # Convert ExecutionResult to dict format
                execution_result = {
                    "execution_id": execution_result_obj.execution_id,
                    "execution_mode": "workflow" if execution_result_obj.status == "running" else "conversation",
                    "result": execution_result_obj.result or {},
                }
            else:
                # Fallback to PlaybookRunExecutor (backward compatibility)
                execution_result = await self.playbook_run_executor.execute_playbook_run(
                    playbook_code=playbook_code,
                    profile_id=ctx.actor_id,
                    inputs=playbook_inputs,
                    workspace_id=ctx.workspace_id,
                    locale=self.default_locale
                )

            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)

            execution_mode = execution_result.get("execution_mode", "conversation")
            execution_id = execution_result.get("execution_id")

            if execution_mode == "workflow":
                assistant_response = i18n.t("conversation_orchestrator", "workflow.started", playbook_code=playbook_code, default=f"Started workflow execution for {playbook_code}")
            else:
                assistant_response = execution_result.get("result", {}).get(
                    "message",
                    i18n.t("conversation_orchestrator", "workflow.started", playbook_code=playbook_code, default=f"Started execution for {playbook_code}")
                )

            assistant_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.ASSISTANT,
                channel="local_workspace",
                profile_id=ctx.actor_id,
                project_id=project_id,
                workspace_id=ctx.workspace_id,
                event_type=EventType.MESSAGE,
                payload={
                    "message": assistant_response,
                    "response_to": message_id,
                    "playbook_code": playbook_code
                },
                entity_ids=[],
                metadata={}
            )
            self.store.create_event(assistant_event)

            # Determine trigger source
            trigger_source = "manual"
            if playbook_context.get("suggestion_id"):
                trigger_source = "suggestion"
            elif playbook_context.get("auto_execute"):
                trigger_source = "auto"

            # Get confirmed intent if available
            origin_intent_id = None
            origin_intent_label = None
            intent_confidence = None
            if playbook_context.get("confirmed_intent_id"):
                from ...services.stores.intent_tags_store import IntentTagsStore
                intent_tags_store = IntentTagsStore(db_path=self.store.db_path)
                intent_tag = intent_tags_store.get_intent_tag(playbook_context["confirmed_intent_id"])
                if intent_tag and intent_tag.status.value == "confirmed":
                    origin_intent_id = intent_tag.id
                    origin_intent_label = intent_tag.label
                    intent_confidence = intent_tag.confidence

            # Calculate total_steps from playbook if not provided
            total_steps = playbook_context.get("total_steps", 0)
            if total_steps == 0:
                # Try to get steps count from playbook.json (for workflow mode)
                if execution_mode == "workflow" and execution_result.get("result"):
                    workflow_result = execution_result.get("result", {})
                    if isinstance(workflow_result, dict) and "steps" in workflow_result:
                        total_steps = len(workflow_result["steps"])
                    elif execution_id:
                        # Try to get from task execution_context
                        task = self.tasks_store.get_task_by_execution_id(execution_id)
                        if task and task.execution_context:
                            total_steps = task.execution_context.get("total_steps", 0)

                # Fallback: Try to get steps count from playbook.json
                if total_steps == 0:
                    try:
                        if self.playbook_service:
                            # Use PlaybookService to load playbook
                            playbook = await self.playbook_service.get_playbook(
                                playbook_code=playbook_code,
                                locale=self.default_locale,
                                workspace_id=ctx.workspace_id
                            )
                            # Try to load playbook.json via PlaybookService's internal loader
                            if playbook and hasattr(playbook, 'playbook_json') and playbook.playbook_json and playbook.playbook_json.steps:
                                total_steps = len(playbook.playbook_json.steps)
                        else:
                            # Fallback to PlaybookLoader (backward compatibility)
                            from ...services.playbook_loader import PlaybookLoader
                            playbook_loader = PlaybookLoader()
                            playbook_run = playbook_loader.load_playbook_run(playbook_code=playbook_code, locale=self.default_locale)
                            if playbook_run and playbook_run.playbook_json and playbook_run.playbook_json.steps:
                                total_steps = len(playbook_run.playbook_json.steps)
                    except Exception:
                        pass

                # Final fallback: Try to get steps count from playbook YAML
                if total_steps == 0:
                    try:
                        import yaml
                        from pathlib import Path
                        # Use PlaybookService if available, otherwise fallback to PlaybookLoader
                        if self.playbook_service:
                            playbook = await self.playbook_service.get_playbook(
                                playbook_code,
                                locale=self.default_locale,
                                workspace_id=ctx.workspace_id
                            )
                        else:
                            # Fallback to PlaybookLoader (backward compatibility)
                            from ...services.playbook_loader import PlaybookLoader
                            playbook_loader = PlaybookLoader()
                            playbook = playbook_loader.get_playbook_by_code(playbook_code)
                        if playbook:
                            # Try to load the YAML file directly to get steps count
                            # Find the playbook file
                            app_dir = Path(__file__).parent.parent.parent
                            # Try capability packs first
                            cap_dirs = [
                                app_dir / "capabilities" / playbook_code.split('_')[0] / "playbooks",
                                app_dir / "capabilities" / playbook_code / "playbooks"
                            ]
                            yaml_file = None
                            for cap_dir in cap_dirs:
                                if cap_dir.exists():
                                    for yf in cap_dir.glob('*.yaml'):
                                        # Check if this file contains the playbook_code
                                        try:
                                            with open(yf, 'r', encoding='utf-8') as f:
                                                yaml_data = yaml.safe_load(f)
                                                if yaml_data and (yaml_data.get('code') == playbook_code or yaml_data.get('playbook_code') == playbook_code):
                                                    yaml_file = yf
                                                    break
                                        except Exception:
                                            continue
                                    if yaml_file:
                                        break

                            if yaml_file:
                                with open(yaml_file, 'r', encoding='utf-8') as f:
                                    yaml_data = yaml.safe_load(f)
                                    if yaml_data and 'steps' in yaml_data:
                                        steps = yaml_data['steps']
                                        if isinstance(steps, list):
                                            total_steps = len(steps)
                                        else:
                                            total_steps = 1
                                    else:
                                        total_steps = 1
                            else:
                                # Fallback: default to 1 for markdown playbooks or if we can't find YAML
                                total_steps = 1
                    except Exception as e:
                        logger.warning(f"Failed to get step count from playbook: {e}")
                        total_steps = 1  # Default to 1 if we can't determine

            # Get default_cluster from playbook_context, or fallback to workspace configuration
            default_cluster = playbook_context.get("default_cluster")
            if not default_cluster:
                # Try to get default_cluster from workspace configuration
                try:
                    workspace = self.store.get_workspace(ctx.workspace_id)
                    if workspace and workspace.default_cluster:
                        default_cluster = workspace.default_cluster
                        logger.debug(f"Using default_cluster from workspace: {workspace.default_cluster}")
                except Exception as e:
                    logger.debug(f"Failed to get default_cluster from workspace: {e}")

            # Fallback to "local_mcp" if still not set
            if not default_cluster:
                default_cluster = "local_mcp"

            # Build execution_context
            execution_context = {
                "playbook_code": playbook_code,
                "playbook_version": playbook_context.get("playbook_version"),
                "trigger_source": trigger_source,
                "current_step_index": 0,
                "total_steps": total_steps,
                "paused_at": None,
                "origin_intent_id": origin_intent_id,
                "origin_intent_label": origin_intent_label,
                "intent_confidence": intent_confidence,
                "origin_suggestion_id": playbook_context.get("suggestion_id"),
                "initiator_user_id": ctx.actor_id,
                "failure_type": None,
                "failure_reason": None,
                "default_cluster": default_cluster
            }

            # Merge ctx.tags if available (for future cloud support)
            if ctx.tags:
                execution_context.update(ctx.tags)

            # Check if task already exists (created by PlaybookService)
            existing_task = None
            if execution_id:
                existing_task = self.tasks_store.get_task(execution_id)

            if not existing_task:
                task = Task(
                    id=str(uuid.uuid4()) if not execution_id else execution_id,
                    workspace_id=ctx.workspace_id,
                    message_id=message_id,
                    execution_id=execution_id or str(uuid.uuid4()),
                    pack_id=playbook_code,
                    task_type="playbook_execution",
                    status=TaskStatus.RUNNING,
                    params={
                        "playbook_code": playbook_code,
                        "context": playbook_context
                    },
                    result=None,
                    execution_context=execution_context,
                    created_at=datetime.utcnow(),
                    started_at=datetime.utcnow(),
                    completed_at=None,
                    error=None
                )
                self.tasks_store.create_task(task)
            else:
                # Task already exists, update it if needed
                task = existing_task
                logger.info(f"ExecutionCoordinator: Task {task.id} already exists, skipping creation")

            # Notify about task creation if callback provided
            if hasattr(self, 'task_event_callback') and self.task_event_callback:
                try:
                    self.task_event_callback('created', {
                        'id': task.id,
                        'pack_id': playbook_code,
                        'status': task.status.value,
                        'task_type': task.task_type,
                        'workspace_id': ctx.workspace_id
                    })
                except Exception as e:
                    logger.warning(f"Failed to call task_event_callback: {e}")

            await self.task_manager.check_and_update_task_status(
                task=task,
                execution_id=execution_id,
                playbook_code=playbook_code
            )

            return {
                "status": "started",
                "playbook_code": playbook_code,
                "execution_id": execution_id,
                "message": assistant_response
            }
        except Exception as e:
            logger.error(f"Failed to start playbook {playbook_code}: {e}", exc_info=True)
            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)
            return {
                "status": "failed",
                "playbook_code": playbook_code,
                "error": str(e),
                "message": i18n.t("conversation_orchestrator", "workflow.failed", playbook_code=playbook_code, error=str(e))
            }

    async def _create_playbook_suggestion(
        self,
        playbook_code: str,
        playbook_context: Dict[str, Any],
        ctx: ExecutionContext,
        message_id: str
    ) -> Dict[str, Any]:
        """Create suggestion card for soft_write playbook"""
        try:
            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)

            # Extract LLM analysis from playbook_context if available
            # playbook_context may contain llm_analysis from workbench suggestions
            # Also check if llm_analysis is at top level of playbook_context
            llm_analysis = {}
            if playbook_context:
                # Try to get from top level first (from workbench suggestions)
                llm_analysis = playbook_context.get("llm_analysis", {})
                # If not found, try to get from nested context
                if not llm_analysis and isinstance(playbook_context.get("context"), dict):
                    llm_analysis = playbook_context.get("context", {}).get("llm_analysis", {})

            # Check if this is a background playbook that auto-executes (doesn't require LLM analysis)
            # These playbooks run automatically in the background and don't need user confirmation
            background_playbooks = ["habit_learning"]
            is_background_playbook = playbook_code.lower() in [p.lower() for p in background_playbooks]

            # Ensure llm_analysis has all required fields with defaults
            if not llm_analysis or not isinstance(llm_analysis, dict):
                llm_analysis = {}
            if "confidence" not in llm_analysis:
                # Background playbooks don't need LLM confidence, but we still set it to 0.0 to indicate no LLM analysis
                llm_analysis["confidence"] = 0.0
            if "reason" not in llm_analysis:
                # For background playbooks, set a default reason explaining it's auto-executed
                if is_background_playbook:
                    llm_analysis["reason"] = "This task will be executed automatically in the background, no LLM analysis needed"
                else:
                    llm_analysis["reason"] = ""
            if "content_tags" not in llm_analysis:
                llm_analysis["content_tags"] = []
            if "analysis_summary" not in llm_analysis:
                if is_background_playbook:
                    llm_analysis["analysis_summary"] = "Background auto-execution task"
                else:
                    llm_analysis["analysis_summary"] = ""

            # Mark as background playbook in llm_analysis for frontend to handle differently
            if is_background_playbook:
                llm_analysis["is_background"] = True

            logger.info(f"ExecutionCoordinator: Extracted llm_analysis for playbook {playbook_code}: confidence={llm_analysis.get('confidence', 0.0):.2f}, tags={len(llm_analysis.get('content_tags', []))}, reason={bool(llm_analysis.get('reason'))}")

            suggestion_task = Task(
                id=str(uuid.uuid4()),
                workspace_id=ctx.workspace_id,
                message_id=message_id,
                execution_id=None,
                pack_id=playbook_code,
                task_type="suggestion",
                status=TaskStatus.PENDING,
                params={
                    "playbook_code": playbook_code,
                    "context": playbook_context,
                    "llm_analysis": llm_analysis
                },
                result={
                    "suggestion": True,
                    "playbook_code": playbook_code,
                    "requires_cta": True,
                    "llm_analysis": llm_analysis
                },
                created_at=datetime.utcnow(),
                started_at=None,
                completed_at=None,
                error=None
            )
            self.tasks_store.create_task(suggestion_task)

            item_type = TimelineItemType.PLAN
            cta_action = "execute_playbook"
            cta_label = i18n.t("conversation_orchestrator", "suggestion.cta_add")

            playbook_lower = playbook_code.lower()
            if "semantic_seeds" in playbook_lower or "intent" in playbook_lower:
                item_type = TimelineItemType.INTENT_SEEDS
                cta_action = "add_to_intents"
            elif "habit_learning" in playbook_lower or "task" in playbook_lower or "plan" in playbook_lower:
                item_type = TimelineItemType.PLAN
                cta_action = "add_to_tasks"

            # Don't create TimelineItem for suggestions - they should only appear in Timeline after execution
            # The suggestion task will show in PendingTasksPanel, and when user clicks CTA,
            # a new TimelineItem will be created by CTAHandler after execution
            # suggestion_timeline_item = TimelineItem(...)  # Removed - don't create TimelineItem for suggestions

            return {
                "status": "suggestion",
                "playbook_code": playbook_code,
                "task_id": suggestion_task.id,
                "timeline_item_id": None,  # No timeline item for suggestions until executed
                "message": i18n.t("conversation_orchestrator", "suggestion.add_to_mindscape")
            }
        except Exception as e:
            logger.error(f"Failed to create playbook suggestion: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}


