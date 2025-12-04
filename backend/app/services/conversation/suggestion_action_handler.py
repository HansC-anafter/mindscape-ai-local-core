"""
Suggestion Action Handler

Handles actions from dynamic suggestions (execute_playbook, use_tool, etc.)
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

from ...models.workspace import ExecutionPlan, TaskPlan
from ...models.mindscape import MindEvent, EventType, EventActor
from ...services.mindscape_store import MindscapeStore
from ...services.playbook_service import PlaybookService, ExecutionMode as PlaybookExecutionMode
from ...services.intent_infra import IntentInfraService
from ...capabilities.registry import get_registry
from ...core.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


class SuggestionActionHandler:
    """Handles actions from dynamic suggestions"""

    def __init__(
        self,
        store: MindscapeStore,
        playbook_runner,
        task_manager,
        execution_coordinator=None,
        default_locale: str = "en",
        playbook_service: Optional[PlaybookService] = None,
        intent_infra: Optional[IntentInfraService] = None
    ):
        """
        Initialize SuggestionActionHandler

        Args:
            store: MindscapeStore instance
            playbook_runner: PlaybookRunner instance
            task_manager: TaskManager instance
            execution_coordinator: ExecutionCoordinator instance (optional, for execute_pack)
            default_locale: Default locale for i18n
            playbook_service: PlaybookService instance (optional, for unified query/execution)
            intent_infra: IntentInfraService instance (optional, for intent_extraction tasks)
        """
        self.store = store
        self.playbook_runner = playbook_runner
        self.task_manager = task_manager
        self.execution_coordinator = execution_coordinator
        self.playbook_service = playbook_service or PlaybookService(store=store)
        self.intent_infra = intent_infra or IntentInfraService(store=store, default_locale=default_locale)
        self.default_locale = default_locale

    async def handle_action(
        self,
        workspace_id: str,
        profile_id: str,
        action: str,
        action_params: Dict[str, Any],
        project_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle action from dynamic suggestion

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            action: Action type (e.g., 'execute_playbook', 'use_tool', 'create_intent')
            action_params: Action parameters
            project_id: Optional project ID
            message_id: Optional message/event ID for ExecutionPlan

        Returns:
            Response dict with conversation message and results
        """
        # Validate action_params
        if not action_params:
            logger.error(f"handle_action called with None action_params for action: {action}")
            action_params = {}

        # Extract suggestion_id from action_params if available
        suggestion_id = action_params.get('suggestion_id') or action_params.get('task_id')

        ctx = ExecutionContext(
            actor_id=profile_id,
            workspace_id=workspace_id,
            tags={"mode": "local"}
        )
        return await self.handle_suggestion_action_with_ctx(
            ctx=ctx,
            suggestion_id=suggestion_id,
            action=action,
            action_params=action_params,
            project_id=project_id,
            message_id=message_id
        )

    async def handle_suggestion_action_with_ctx(
        self,
        ctx: ExecutionContext,
        suggestion_id: Optional[str],
        action: str,
        action_params: Dict[str, Any],
        project_id: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle action from dynamic suggestion using ExecutionContext

        Args:
            ctx: Execution context
            suggestion_id: Suggestion task ID
            action: Action type (e.g., 'execute_playbook', 'use_tool', 'create_intent')
            action_params: Action parameters
            project_id: Optional project ID
            message_id: Optional message/event ID for ExecutionPlan

        Returns:
            Response dict with conversation message and results
        """
        try:
            if action == 'execute_playbook':
                return await self._handle_execute_playbook(
                    ctx, action_params, project_id, message_id
                )

            elif action == 'use_tool':
                return await self._handle_use_tool(
                    ctx, action_params, project_id, message_id
                )

            elif action == 'create_intent':
                return await self._handle_create_intent(ctx, action_params, project_id, message_id)

            elif action == 'start_chat':
                return self._handle_start_chat(ctx.workspace_id)

            elif action == 'upload_file':
                return self._handle_upload_file(ctx.workspace_id)

            elif action == 'execute_pack':
                return await self._handle_execute_pack(
                    ctx=ctx,
                    action_params=action_params,
                    project_id=project_id,
                    message_id=message_id
                )

            else:
                from ...services.i18n_service import get_i18n_service
                i18n = get_i18n_service(default_locale=self.default_locale)
                error_msg = i18n.t("conversation_orchestrator", "error.unknown_action", action=action)
                raise ValueError(error_msg)

        except Exception as e:
            logger.error(f"Failed to handle suggestion action: {e}", exc_info=True)
            return self._handle_error(ctx.workspace_id, ctx.actor_id, project_id, str(e))

    async def _handle_execute_playbook(
        self,
        ctx: ExecutionContext,
        action_params: Dict[str, Any],
        project_id: Optional[str],
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Handle execute_playbook action"""
        playbook_code = action_params.get('playbook_code')
        if not playbook_code:
            logger.error(f"_handle_execute_playbook: playbook_code missing in action_params: {action_params}")
            raise ValueError("playbook_code is required for execute_playbook action")

        logger.info(f"_handle_execute_playbook: Starting execution for playbook {playbook_code}, workspace={ctx.workspace_id}, profile={ctx.actor_id}")

        playbook_context = action_params.copy()
        playbook_context["from_suggestion_action"] = True
        playbook_context["task_id"] = action_params.get("task_id")

        locale = playbook_context.get("locale") or self.default_locale

        logger.info(f"_handle_execute_playbook: Loading playbook for {playbook_code}, locale={locale}")
        # Use PlaybookService to get playbook
        playbook = await self.playbook_service.get_playbook(
            playbook_code=playbook_code,
            locale=locale,
            workspace_id=ctx.workspace_id
        )

        if not playbook:
            logger.error(f"_handle_execute_playbook: Playbook {playbook_code} not found")
            raise ValueError(f"Playbook {playbook_code} not found")

        # Verify playbook has JSON structure required for execution
        playbook_run = self.playbook_service.playbook_loader.load_playbook_run(
            playbook_code=playbook_code,
            locale=locale
        )
        if not playbook_run or not playbook_run.has_json():
            logger.error(f"_handle_execute_playbook: Playbook {playbook_code} does not have playbook.json")
            raise ValueError(
                f"Playbook {playbook_code} does not have playbook.json. "
                f"HandoffPlan is required for execution. Please create playbook.json for structured workflow execution."
            )

        logger.info(f"_handle_execute_playbook: Calling execute_playbook for {playbook_code}")
        execution_result_obj = await self.playbook_service.execute_playbook(
            playbook_code=playbook_code,
            workspace_id=ctx.workspace_id,
            profile_id=ctx.actor_id,
            inputs=playbook_context,
            execution_mode=PlaybookExecutionMode.ASYNC,
            locale=locale
        )
        # Convert ExecutionResult to dict format for backward compatibility
        execution_result = {
            "execution_id": execution_result_obj.execution_id,
            "execution_mode": "workflow" if execution_result_obj.status == "running" else "conversation",
            "result": execution_result_obj.result or {},
        }
        logger.info(f"_handle_execute_playbook: Execution completed for {playbook_code}, execution_id={execution_result_obj.execution_id}")

        self._create_user_event(
            ctx.workspace_id, ctx.actor_id, project_id,
            f"Execute playbook: {playbook_code}",
            'execute_playbook', action_params
        )

        execution_id = None
        if execution_result.get("execution_id"):
            execution_id = execution_result.get("execution_id")
        elif execution_result.get("result", {}).get("execution_id"):
            execution_id = execution_result.get("result", {}).get("execution_id")

        logger.info(f"_handle_execute_playbook: Returning execution_id={execution_id} for {playbook_code}")

        return {
            "workspace_id": ctx.workspace_id,
            "display_events": [],
            "triggered_playbook": {
                "playbook_code": playbook_code,
                "execution_id": execution_id,
                "status": "triggered"
            },
            "pending_tasks": []
        }

    async def _handle_use_tool(
        self,
        ctx: ExecutionContext,
        action_params: Dict[str, Any],
        project_id: Optional[str],
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Handle use_tool action"""
        tool_name = action_params.get('tool')
        if not tool_name:
            raise ValueError("tool is required for use_tool action")

        registry = get_registry()
        tool_info = registry.get_tool(tool_name)
        if not tool_info:
            raise ValueError(f"Tool {tool_name} not found")

        capability_code = tool_info.get('capability')
        capability_info = registry.capabilities.get(capability_code)
        side_effect_level = capability_info.get('manifest', {}).get('side_effect_level', 'readonly') if capability_info else 'readonly'

        plan = ExecutionPlan(
            message_id=message_id or str(uuid.uuid4()),
            workspace_id=ctx.workspace_id,
            tasks=[
                TaskPlan(
                    pack_id=capability_code,
                    task_type=tool_name.split('.')[-1],
                    params=action_params,
                    side_effect_level=side_effect_level,
                    auto_execute=(side_effect_level == 'readonly'),
                    requires_cta=(side_effect_level != 'readonly')
                )
            ]
        )

        # Create tasks from execution plan
        from ...services.conversation_orchestrator import ConversationOrchestrator
        task_results = []
        for task_plan in plan.tasks:
            from ...models.workspace import Task, TaskStatus
            task = Task(
                id=str(uuid.uuid4()),
                workspace_id=ctx.workspace_id,
                message_id=plan.message_id,
                execution_id=None,
                pack_id=task_plan.pack_id,
                task_type=task_plan.task_type,
                status=TaskStatus.PENDING if task_plan.requires_cta else TaskStatus.RUNNING,
                params=task_plan.params,
                result=None,
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow() if not task_plan.requires_cta else None,
                completed_at=None,
                error=None
            )
            self.task_manager.tasks_store.create_task(task)
            task_results.append({
                "task_id": task.id,
                "pack_id": task_plan.pack_id,
                "task_type": task_plan.task_type,
                "status": task.status.value,
                "requires_cta": task_plan.requires_cta
            })
        task_result = task_results[0] if task_results else None

        self._create_user_event(
            ctx.workspace_id, ctx.actor_id, project_id,
            f"Use tool: {tool_name}",
            'use_tool', action_params
        )

        return {
            "workspace_id": ctx.workspace_id,
            "display_events": [],
            "triggered_playbook": None,
            "pending_tasks": [task_result] if task_result else []
        }

    def _handle_create_intent(
        self,
        ctx: ExecutionContext,
        action_params: Dict[str, Any],
        project_id: Optional[str],
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Handle create_intent action"""
        from ...models.mindscape import IntentCard, IntentStatus, PriorityLevel
        from datetime import datetime
        import uuid

        title = action_params.get("title") or action_params.get("intent_title")
        description = action_params.get("description") or action_params.get("intent_description")

        if not title:
            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)
            title = i18n.t("conversation_orchestrator", "create_intent_card_title", default="New Intent")

        if not description:
            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)
            description = i18n.t("conversation_orchestrator", "create_intent_card_description", default="Start tracking your long-term goals and tasks")

        new_intent = IntentCard(
            id=str(uuid.uuid4()),
            profile_id=ctx.actor_id,
            title=title,
            description=description,
            priority=PriorityLevel.MEDIUM,
            status=IntentStatus.ACTIVE,
            tags=action_params.get("tags", []),
            category=action_params.get("category"),
            progress_percentage=0.0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            started_at=None,
            completed_at=None,
            due_date=None,
            parent_intent_id=None,
            child_intent_ids=[],
            metadata={}
        )

        try:
            created_intent = self.store.create_intent(new_intent)
            logger.info(f"_handle_create_intent: Created intent card {created_intent.id} for user {ctx.actor_id}")

            from ...models.mindscape import MindEvent, EventType, EventActor
            is_high_priority = created_intent.priority in [PriorityLevel.HIGH, PriorityLevel.CRITICAL]
            intent_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.USER,
                channel="local_workspace",
                profile_id=ctx.actor_id,
                project_id=project_id,
                workspace_id=ctx.workspace_id,
                event_type=EventType.INTENT_CREATED,
                payload={
                    "intent_id": created_intent.id,
                    "title": created_intent.title,
                    "description": created_intent.description,
                    "status": created_intent.status.value,
                    "priority": created_intent.priority.value
                },
                entity_ids=[created_intent.id],
                metadata={
                    "should_embed": is_high_priority,
                    "is_artifact": is_high_priority
                }
            )
            self.store.create_event(intent_event, generate_embedding=is_high_priority)

            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)
            success_message = i18n.t(
                "conversation_orchestrator",
                "intent.created",
                intent_title=created_intent.title,
                default=f"Intent card '{created_intent.title}' created successfully"
            )

            return {
                "workspace_id": ctx.workspace_id,
                "display_events": [{
                    "type": "message",
                    "content": success_message,
                    "timestamp": datetime.utcnow().isoformat()
                }],
                "triggered_playbook": None,
                "pending_tasks": [],
                "created_intent": {
                    "id": created_intent.id,
                    "title": created_intent.title
                }
            }
        except Exception as e:
            logger.error(f"_handle_create_intent: Failed to create intent: {e}", exc_info=True)
            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)
            error_message = i18n.t(
                "conversation_orchestrator",
                "intent.create_failed",
                error=str(e),
                default=f"Failed to create intent card: {str(e)}"
            )
            return {
                "workspace_id": ctx.workspace_id,
                "display_events": [{
                    "type": "error",
                    "content": error_message,
                    "timestamp": datetime.utcnow().isoformat()
                }],
                "triggered_playbook": None,
                "pending_tasks": []
            }

    def _handle_start_chat(self, workspace_id: str) -> Dict[str, Any]:
        """Handle start_chat action"""
        return {
            "workspace_id": workspace_id,
            "display_events": [],
            "triggered_playbook": None,
            "pending_tasks": []
        }

    def _handle_upload_file(self, workspace_id: str) -> Dict[str, Any]:
        """Handle upload_file action"""
        return {
            "workspace_id": workspace_id,
            "display_events": [],
            "triggered_playbook": None,
            "pending_tasks": []
        }

    async def _handle_execute_pack(
        self,
        ctx: ExecutionContext,
        action_params: Dict[str, Any],
        project_id: Optional[str],
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Handle execute_pack action - execute a pack from pending task"""
        try:
            if not action_params:
                logger.error("action_params is None for execute_pack action")
                raise ValueError("action_params is required for execute_pack action")

            logger.info(f"_handle_execute_pack called with action_params: {action_params}")

            pack_id = action_params.get('pack_id')
            task_id = action_params.get('task_id')

            if not pack_id:
                raise ValueError("pack_id is required for execute_pack action")

            if not self.execution_coordinator:
                raise ValueError("execution_coordinator is required for execute_pack action")

            task = self.task_manager.tasks_store.get_task(task_id) if task_id else None

            if task:
                original_message_id = task.message_id or message_id or str(uuid.uuid4())
                files = task.params.get('files', []) if task.params else []
                message = task.params.get('message', '') if task.params else ''

                from ...models.workspace import TaskStatus
                try:
                    self.task_manager.tasks_store.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.SUCCEEDED,
                        result={"action": "executed", "pack_id": pack_id},
                        completed_at=datetime.utcnow()
                    )
                except Exception as e:
                    logger.warning(f"Failed to update suggestion task status: {e}")
            else:
                original_message_id = message_id or str(uuid.uuid4())
                files = action_params.get('files', [])
                message = action_params.get('message', '')

            from ...services.i18n_service import get_i18n_service
            i18n = get_i18n_service(default_locale=self.default_locale)
            execute_message = i18n.t("conversation_orchestrator", "error.execute_pack", pack_id=pack_id)
            self._create_user_event(
                ctx.workspace_id, ctx.actor_id, project_id,
                execute_message,
                'execute_pack', action_params
            )

            result = None
            pack_id_lower = pack_id.lower() if pack_id else ""

            if pack_id_lower == "intent_extraction" and task:
                from ...models.workspace import TaskStatus
                result = await self.intent_infra.handle_extraction_task(
                    ctx=ctx,
                    task=task,
                    original_message_id=original_message_id
                )
                self.task_manager.tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.SUCCEEDED,
                    error=None,
                    completed_at=datetime.utcnow()
                )
                try:
                    self.task_manager.tasks_store.db.execute(
                        "UPDATE tasks SET execution_id = NULL WHERE id = ?",
                        (task.id,)
                    )
                    self.task_manager.tasks_store.db.commit()
                    logger.info(f"Cleared execution_id for intent_extraction task {task.id}")
                except Exception as e:
                    logger.warning(f"Failed to clear execution_id for intent_extraction task: {e}")

                logger.info(f"Intent extraction task {task.id} completed via IntentInfraService")
            else:
                # Determine execution method: check PlaybookService first (handles all playbooks),
                # then CapabilityRegistry (handles capability packs with pack_executor)
                execution_method = None
                registry = get_registry()

                # Check PlaybookService first - it handles all playbooks (system, capability, user)
                logger.info(f"SuggestionActionHandler: Checking PlaybookService for {pack_id}, default_locale={self.default_locale}, type={type(self.default_locale)}")
                playbook_found = None
                try:
                    playbook = await self.playbook_service.get_playbook(
                        playbook_code=pack_id,
                        locale=self.default_locale,
                        workspace_id=ctx.workspace_id
                    )
                    if playbook:
                        execution_method = 'playbook'
                        playbook_found = playbook.metadata.playbook_code
                        logger.info(f"Pack {pack_id} found in PlaybookService, execution method: {execution_method}, playbook_code: {playbook_found}")
                    else:
                        logger.debug(f"Pack {pack_id} not found in PlaybookService (returned None)")
                except Exception as e:
                    logger.warning(f"Pack {pack_id} error checking PlaybookService: {type(e).__name__}: {e}")

                # If not a playbook, check CapabilityRegistry for pack_executor
                if not execution_method:
                    execution_method = registry.get_execution_method(pack_id)
                    logger.info(f"Pack {pack_id} execution method from CapabilityRegistry: {execution_method}")

                if execution_method == 'pack_executor':
                    if pack_id_lower == "daily_planning":
                        result = await self.execution_coordinator._execute_daily_planning(
                            workspace_id=ctx.workspace_id,
                            profile_id=ctx.actor_id,
                            message_id=original_message_id,
                            files=files,
                            message=message,
                            task_event_callback=None
                        )
                    elif pack_id_lower == "semantic_seeds" or "intent" in pack_id_lower:
                        result = await self.execution_coordinator._execute_semantic_seeds(
                            workspace_id=ctx.workspace_id,
                            profile_id=ctx.actor_id,
                            message_id=original_message_id,
                            files=files,
                            message=message,
                            task_event_callback=None
                        )
                    elif pack_id_lower == "content_drafting":
                        output_type = action_params.get('output_type', 'summary')
                        result = await self.execution_coordinator._execute_content_drafting(
                            workspace_id=ctx.workspace_id,
                            profile_id=ctx.actor_id,
                            message_id=original_message_id,
                            files=files,
                            message=message,
                            output_type=output_type,
                            task_event_callback=None
                        )
                    else:
                        logger.warning(f"Pack {pack_id} has pack_executor but no specific handler, using ExecutionPlan")
                        result = await self._execute_via_plan(
                            pack_id, ctx, original_message_id,
                            files, message, project_id, task, action_params
                        )

                if execution_method == 'playbook':
                    # If PlaybookService already found the playbook, use it directly
                    if playbook_found:
                        logger.info(f"Executing pack {pack_id} via playbook {playbook_found} (found by PlaybookService)")
                        execution_result = await self.playbook_runner.start_playbook_execution(
                            playbook_code=playbook_found,
                            profile_id=ctx.actor_id,
                            inputs={
                                **(task.params if task and task.params else {}),
                                **(action_params if action_params else {}),
                                "files": files,
                                "message": message
                            },
                            workspace_id=ctx.workspace_id
                        )
                        result = {"pack_id": pack_id, "playbook_code": playbook_found, "execution_id": execution_result.get("execution_id")}
                    else:
                        # Fallback: try to find playbook via capability registry (for capability playbooks)
                        playbooks = registry.get_capability_playbooks(pack_id)
                        if not playbooks:
                            raise ValueError(f"Pack {pack_id} marked as playbook but no playbooks found in PlaybookService or CapabilityRegistry")

                        from backend.app.playbook_loader import PlaybookLoader
                        playbook_loader = PlaybookLoader()

                        playbook_found = None
                        playbook_codes_to_try = []

                        playbook_codes_to_try.append(pack_id)

                        for playbook_filename in playbooks:
                            base_name = playbook_filename.replace('.yaml', '').replace('.yml', '')
                            playbook_codes_to_try.append(base_name)

                        logger.info(f"Looking for playbook for pack {pack_id}, trying codes: {playbook_codes_to_try}")

                        for playbook_code in playbook_codes_to_try:
                            try:
                                playbook = await self.playbook_service.get_playbook(
                                    playbook_code=playbook_code,
                                    locale=self.default_locale,
                                    workspace_id=ctx.workspace_id
                                )
                                if playbook:
                                    playbook_found = playbook.metadata.playbook_code
                                    logger.info(f"Found playbook {playbook_found} for pack {pack_id} (searched with: {playbook_code})")
                                    break
                            except Exception as e:
                                logger.debug(f"Playbook {playbook_code} not found: {e}")
                                continue

                        if not playbook_found:
                            logger.info(f"Trying to load all playbooks to find match for pack {pack_id}")
                            try:
                                all_playbooks_metadata = await self.playbook_service.list_playbooks(
                                    workspace_id=ctx.workspace_id,
                                    locale=self.default_locale
                                )
                                logger.info(f"Loaded {len(all_playbooks_metadata)} total playbooks, searching for pack {pack_id}")
                                for pb_meta in all_playbooks_metadata:
                                    pb_code = pb_meta.playbook_code
                                    if pb_code in playbook_codes_to_try:
                                        playbook_found = pb_code
                                        logger.info(f"Found playbook {playbook_found} for pack {pack_id} via full search (exact match)")
                                        break
                                    if pack_id.lower() in pb_code.lower():
                                        playbook_found = pb_code
                                        logger.info(f"Found playbook {playbook_found} for pack {pack_id} via full search (partial match)")
                                        break
                                if not playbook_found:
                                    logger.warning(f"Available playbook codes: {[p.playbook_code for p in all_playbooks_metadata[:10]]}")
                            except Exception as e:
                                logger.error(f"Failed to load all playbooks: {e}", exc_info=True)

                        if playbook_found:
                            logger.info(f"Executing pack {pack_id} via playbook {playbook_found}")
                            execution_result = await self.playbook_runner.start_playbook_execution(
                                playbook_code=playbook_found,
                                profile_id=ctx.actor_id,
                                inputs={
                                    **(task.params if task and task.params else {}),
                                    **(action_params if action_params else {}),
                                    "files": files,
                                    "message": message
                                },
                                workspace_id=ctx.workspace_id
                            )
                            result = {"pack_id": pack_id, "playbook_code": playbook_found, "execution_id": execution_result.get("execution_id")}
                        else:
                            from ...services.i18n_service import get_i18n_service
                            i18n = get_i18n_service(default_locale=self.default_locale)
                            logger.error(
                                f"Could not find playbook for pack {pack_id}. "
                                f"Tried codes: {playbook_codes_to_try}."
                            )
                            error_msg = i18n.t(
                                "conversation_orchestrator",
                                "error.could_not_find_playbook",
                                pack_id=pack_id,
                                tried=str(playbook_codes_to_try)
                            )
                            raise ValueError(error_msg)

                else:
                    # If execution_method is explicitly 'unknown', fail immediately - do NOT attempt any execution
                    if execution_method == 'unknown':
                        error_msg = (
                            f"Pack {pack_id} has unknown execution method and cannot be executed. "
                            f"This pack is not a playbook, does not have a pack_executor, and cannot be executed."
                        )
                        logger.error(error_msg)
                        raise ValueError(error_msg)

                    if pack_id_lower == "intent_extraction":
                        error_msg = (
                            f"SuggestionActionHandler: intent_extraction reached fallback logic. "
                            f"This should have been handled by IntentInfraService priority logic above. "
                            f"Check that priority handling is working correctly."
                        )
                        logger.error(error_msg)
                        raise ValueError(error_msg)

                    logger.info(f"Pack {pack_id} has unknown execution method, trying to find playbook directly")
                    playbook_found = None
                    try:
                        playbook = await self.playbook_service.get_playbook(
                            playbook_code=pack_id,
                            locale=self.default_locale,
                            workspace_id=ctx.workspace_id
                        )
                        if playbook:
                            playbook_found = playbook.metadata.playbook_code
                            logger.info(f"Found playbook {playbook_found} for pack {pack_id} (direct lookup)")
                    except Exception as e:
                        logger.debug(f"Playbook {pack_id} not found via direct lookup: {e}")

                    if playbook_found:
                        logger.info(f"Executing pack {pack_id} via playbook {playbook_found}")
                        execution_result = await self.playbook_runner.start_playbook_execution(
                            playbook_code=playbook_found,
                            profile_id=ctx.actor_id,
                            inputs={
                                **(task.params if task and task.params else {}),
                                **(action_params if action_params else {}),
                                "files": files,
                                "message": message
                            },
                            workspace_id=ctx.workspace_id
                        )
                        result = {"pack_id": pack_id, "playbook_code": playbook_found, "execution_id": execution_result.get("execution_id")}
                    else:
                        logger.warning(f"Pack {pack_id} has unknown execution method and no playbook found, trying ExecutionPlan as fallback")
                        result = await self._execute_via_plan(
                            pack_id, ctx, original_message_id,
                            files, message, project_id, task, action_params
                        )

                        # Check if execution actually succeeded - if ExecutionPlan created suggestion cards, it failed
                        if result and result.get("suggestion_cards"):
                            # Execution failed and created suggestion cards - this will cause infinite loop
                            logger.error(f"Pack {pack_id} execution failed - created suggestion cards, preventing infinite loop by raising error")
                            raise ValueError(f"Pack {pack_id} cannot be executed: no playbook found and execution failed")

            # Only log success if we have a valid result (execution_id or executed_tasks, but NOT suggestion_cards)
            if result and (result.get("execution_id") or (result.get("executed_tasks") and not result.get("suggestion_cards"))):
                logger.info(f"Successfully executed pack {pack_id} from pending task")
            else:
                logger.error(f"Pack {pack_id} execution failed - no valid result or only suggestion cards returned")
                raise ValueError(f"Pack {pack_id} execution failed: no valid result")

            return {
                "workspace_id": ctx.workspace_id,
                "display_events": [],
                "triggered_playbook": None,
                "pending_tasks": []
            }

        except Exception as e:
            error_message = f"Failed to execute pack {pack_id}: {str(e)}"
            error_type = type(e).__name__
            logger.error(error_message, exc_info=True)

            if task:
                from ...models.workspace import TaskStatus
                try:
                    self.task_manager.tasks_store.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=error_message,
                        result={
                            "progress": "failed",
                            "progress_percentage": 0,
                            "error": error_message,
                            "error_type": error_type,
                            "pack_id": pack_id
                        },
                        completed_at=datetime.utcnow()
                    )
                    logger.info(f"Updated task {task.id} status to FAILED with error: {error_message}")
                except Exception as update_error:
                    logger.error(f"Failed to update task {task.id} status to FAILED: {update_error}", exc_info=True)

            # Re-raise the exception to propagate it, but task status is already updated
            raise

    def _handle_error(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        error_message: str
    ) -> Dict[str, Any]:
        """Handle error case"""
        # Use i18n for error message
        from ...services.i18n_service import get_i18n_service
        i18n = get_i18n_service(default_locale=self.default_locale)
        error_msg = i18n.t("conversation_orchestrator", "error.execute_action_failed", error=error_message)

        error_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.SYSTEM,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": error_msg
            },
            entity_ids=[],
            metadata={}
        )
        self.store.create_event(error_event)

        return {
            "workspace_id": workspace_id,
            "display_events": [],
            "triggered_playbook": None,
            "pending_tasks": []
        }

    async def _execute_via_plan(
        self,
        pack_id: str,
        ctx: ExecutionContext,
        message_id: str,
        files: List[str],
        message: str,
        project_id: Optional[str],
        task: Optional[Any],
        action_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute pack via ExecutionPlan as fallback"""
        plan = ExecutionPlan(
            message_id=message_id,
            workspace_id=ctx.workspace_id,
            tasks=[
                TaskPlan(
                    pack_id=pack_id,
                    task_type=pack_id,
                    params={
                        **(task.params if task and task.params else {}),
                        **(action_params if action_params else {}),
                        "files": files,
                        "message": message
                    },
                    side_effect_level=None,
                    auto_execute=False,
                    requires_cta=False
                )
            ]
        )
        execution_results = await self.execution_coordinator.execute_plan(
            execution_plan=plan,
            workspace_id=ctx.workspace_id,
            profile_id=ctx.actor_id,
            message_id=message_id,
            files=files,
            message=message,
            project_id=project_id
        )
        return {"pack_id": pack_id, "execution_results": execution_results}

    def _create_user_event(
        self,
        workspace_id: str,
        profile_id: str,
        project_id: Optional[str],
        message: str,
        action: str,
        action_params: Dict[str, Any]
    ):
        """Create user message event for action"""
        user_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=EventActor.USER,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": message,
                "action": action,
                "action_params": action_params
            },
            entity_ids=[],
            metadata={}
        )
        self.store.create_event(user_event)
