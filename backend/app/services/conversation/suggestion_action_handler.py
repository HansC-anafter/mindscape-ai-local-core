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
        default_locale: str = "en"
    ):
        """
        Initialize SuggestionActionHandler

        Args:
            store: MindscapeStore instance
            playbook_runner: PlaybookRunner instance
            task_manager: TaskManager instance
            execution_coordinator: ExecutionCoordinator instance (optional, for execute_pack)
            default_locale: Default locale for i18n
        """
        self.store = store
        self.playbook_runner = playbook_runner
        self.task_manager = task_manager
        self.execution_coordinator = execution_coordinator
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
                return self._handle_create_intent(ctx.workspace_id)

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
            raise ValueError("playbook_code is required for execute_playbook action")

        # Use execution_coordinator.create_execution_with_ctx to handle side_effect_level correctly
        # This ensures that SOFT_WRITE/EXTERNAL_WRITE playbooks create suggestion tasks with llm_analysis
        if self.execution_coordinator:
            # Extract llm_analysis from action_params if available
            playbook_context = action_params.copy()

            # Mark that this is triggered from suggestion action (user confirmed execution)
            # This allows create_execution_with_ctx to distinguish between first-time suggestion and user confirmation
            playbook_context["from_suggestion_action"] = True
            playbook_context["task_id"] = action_params.get("task_id")  # Original suggestion task ID if available

            # execution_coordinator.create_execution_with_ctx will:
            # - Check side_effect_level
            # - Check from_suggestion_action flag
            # - If from_suggestion_action=True: execute directly (user confirmed)
            # - If from_suggestion_action=False: create suggestion card (first-time suggestion)
            # - For READONLY: always execute directly
            result = await self.execution_coordinator.create_execution_with_ctx(
                playbook_code=playbook_code,
                playbook_context=playbook_context,
                ctx=ctx,
                message_id=message_id or str(uuid.uuid4()),
                project_id=project_id
            )

            self._create_user_event(
                ctx.workspace_id, ctx.actor_id, project_id,
                f"Execute playbook: {playbook_code}",
                'execute_playbook', action_params
            )

            # Convert execution_coordinator result to suggestion_action_handler format
            if result.get("status") == "suggestion":
                return {
                    "workspace_id": ctx.workspace_id,
                    "display_events": [],
                    "triggered_playbook": None,
                    "pending_tasks": [{
                        "task_id": result.get("task_id"),
                        "playbook_code": playbook_code,
                        "status": "pending"
                    }] if result.get("task_id") else []
                }
            elif result.get("status") == "started":
                return {
                    "workspace_id": ctx.workspace_id,
                    "display_events": [],
                    "triggered_playbook": {
                        "playbook_code": playbook_code,
                        "execution_id": result.get("execution_id"),
                        "status": "triggered"
                    },
                    "pending_tasks": []
                }
            else:
                # Fallback to original behavior
                return {
                    "workspace_id": ctx.workspace_id,
                    "display_events": [],
                    "triggered_playbook": {
                        "playbook_code": playbook_code,
                        "status": result.get("status", "unknown")
                    },
                    "pending_tasks": []
                }
        else:
            # Fallback: direct execution if execution_coordinator not available
            execution_result = await self.playbook_runner.start_playbook_execution(
                playbook_code=playbook_code,
                profile_id=ctx.actor_id,
                inputs=action_params,
                workspace_id=ctx.workspace_id
            )

            self._create_user_event(
                ctx.workspace_id, ctx.actor_id, project_id,
                f"Execute playbook: {playbook_code}",
                'execute_playbook', action_params
            )

            return {
                "workspace_id": ctx.workspace_id,
                "display_events": [],
                "triggered_playbook": {
                    "playbook_code": playbook_code,
                    "execution_id": execution_result.get("execution_id"),
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

        # Use execution_coordinator to execute the plan instead of task_manager
        # task_manager doesn't have execute_task_plan method
        from ...services.conversation_orchestrator import ConversationOrchestrator
        # Get execution_coordinator from orchestrator if available
        # For now, create tasks directly from the plan
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

    def _handle_create_intent(self, workspace_id: str) -> Dict[str, Any]:
        """Handle create_intent action"""
        return {
            "workspace_id": workspace_id,
            "display_events": [],
            "triggered_playbook": None,
            "pending_tasks": [],
            "redirect": "/mindscape?action=create_intent"
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

        # Get the original task to retrieve context (message_id, files, message)
        task = self.task_manager.tasks_store.get_task(task_id) if task_id else None

        # If task exists, use its context
        if task:
            original_message_id = task.message_id or message_id or str(uuid.uuid4())
            files = task.params.get('files', []) if task.params else []
            message = task.params.get('message', '') if task.params else ''

            # Mark suggestion task as succeeded (user accepted the suggestion)
            # The pack executor or playbook will create a new RUNNING task for actual execution
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
            # Create new message_id if task not found
            original_message_id = message_id or str(uuid.uuid4())
            files = action_params.get('files', [])
            message = action_params.get('message', '')

        # Create user event for action (use i18n)
        from ...services.i18n_service import get_i18n_service
        i18n = get_i18n_service(default_locale=self.default_locale)
        execute_message = i18n.t("conversation_orchestrator", "error.execute_pack", pack_id=pack_id)
        self._create_user_event(
            ctx.workspace_id, ctx.actor_id, project_id,
            execute_message,
            'execute_pack', action_params
        )

        # Execute the pack using Registry to determine execution method
        try:
            registry = get_registry()
            execution_method = registry.get_execution_method(pack_id)

            logger.info(f"Pack {pack_id} execution method: {execution_method}")

            result = None

            if execution_method == 'pack_executor':
                # Pack has a direct executor (like daily_planning, content_drafting)
                # Use ExecutionCoordinator's internal methods
                pack_id_lower = pack_id.lower()
                if pack_id_lower == "daily_planning":
                    result = await self.execution_coordinator._execute_daily_planning(
                        workspace_id=ctx.workspace_id,
                        profile_id=ctx.actor_id,
                        message_id=original_message_id,
                        files=files,
                        message=message,
                        task_event_callback=None
                    )
                elif pack_id_lower == "semantic_seeds" or "intent" in pack_id_lower or pack_id_lower == "intent_extraction":
                    # Handle intent_extraction tasks - directly add intents and create completed TimelineItem
                    if pack_id_lower == "intent_extraction" and task:
                        # Extract intents from task params
                        intents = task.params.get("intents", []) if task.params else []
                        themes = task.params.get("themes", []) if task.params else []

                        if intents:
                            from ...models.mindscape import IntentCard, IntentStatus, PriorityLevel
                            from ...models.workspace import TaskStatus, TimelineItem, TimelineItemType
                            from ...services.stores.timeline_items_store import TimelineItemsStore
                            from ...services.i18n_service import get_i18n_service

                            i18n = get_i18n_service(default_locale=self.default_locale)
                            timeline_items_store = TimelineItemsStore(self.store.db_path)
                            intents_added = 0

                            # Add intents directly
                            for intent_item in intents[:3]:
                                if isinstance(intent_item, dict):
                                    intent_text = intent_item.get("title") or intent_item.get("text") or str(intent_item)
                                else:
                                    intent_text = str(intent_item) if intent_item else None

                                if intent_text and isinstance(intent_text, str) and len(intent_text.strip()) > 0:
                                    try:
                                        existing_intents = self.store.list_intents(
                                            profile_id=ctx.actor_id,
                                            status=None,
                                            priority=None
                                        )
                                        intent_exists = any(
                                            intent.title == intent_text.strip() or
                                            intent_text.strip() in intent.title
                                            for intent in existing_intents
                                        )
                                        if not intent_exists:
                                            new_intent = IntentCard(
                                                id=str(uuid.uuid4()),
                                                profile_id=ctx.actor_id,
                                                title=intent_text.strip(),
                                                description=f"Added from intent extraction task",
                                                status=IntentStatus.ACTIVE,
                                                priority=PriorityLevel.MEDIUM,
                                                tags=[],
                                                category="intent_extraction",
                                                progress_percentage=0.0,
                                                created_at=datetime.utcnow(),
                                                updated_at=datetime.utcnow(),
                                                started_at=None,
                                                completed_at=None,
                                                due_date=None,
                                                parent_intent_id=None,
                                                child_intent_ids=[],
                                                metadata={
                                                    "source": "intent_extraction_task",
                                                    "workspace_id": ctx.workspace_id,
                                                    "task_id": task.id
                                                }
                                            )
                                            self.store.create_intent(new_intent)
                                            intents_added += 1
                                            logger.info(f"Added intent from task: {intent_text[:50]}")
                                    except Exception as e:
                                        logger.warning(f"Failed to add intent from task: {e}")

                            # Update task status to SUCCEEDED
                            self.task_manager.tasks_store.update_task_status(
                                task_id=task.id,
                                status=TaskStatus.SUCCEEDED,
                                error=None
                            )

                            # Create completed TimelineItem (no CTA, already executed)
                            timeline_item = TimelineItem(
                                id=str(uuid.uuid4()),
                                workspace_id=ctx.workspace_id,
                                message_id=original_message_id,
                                task_id=task.id,
                                type=TimelineItemType.INTENT_SEEDS,
                                title=i18n.t(
                                    "conversation_orchestrator",
                                    "timeline.intents_added_title" if intents_added > 0 else "timeline.no_intents_added_title",
                                    count=intents_added,
                                    default=f"Added {intents_added} intent(s) to Mindscape" if intents_added > 0 else "No new intents"
                                ),
                                summary=i18n.t(
                                    "conversation_orchestrator",
                                    "timeline.intents_added_summary" if intents_added > 0 else "timeline.all_intents_exist_summary",
                                    count=intents_added,
                                    default=f"Added {intents_added} intent(s) from message" if intents_added > 0 else "All intents already exist"
                                ),
                                data={
                                    "intents": intents,
                                    "themes": themes,
                                    "source": "intent_extraction_task",
                                    "intents_added": intents_added
                                },
                                cta=None,  # No CTA - already completed
                                created_at=datetime.utcnow()
                            )
                            timeline_items_store.create_timeline_item(timeline_item)
                            logger.info(f"Created completed TimelineItem for intent_extraction task {task.id}")

                            result = {"pack_id": pack_id, "intents_added": intents_added}
                        else:
                            # No intents to add
                            self.task_manager.tasks_store.update_task_status(
                                task_id=task.id,
                                status=TaskStatus.SUCCEEDED,
                                error=None
                            )
                            result = {"pack_id": pack_id, "intents_added": 0}
                    else:
                        # Use semantic_seeds executor for other intent-related packs
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
                    # Generic pack executor - try to use ExecutionPlan
                    logger.warning(f"Pack {pack_id} has pack_executor but no specific handler, using ExecutionPlan")
                    result = await self._execute_via_plan(
                        pack_id, ctx, original_message_id,
                        files, message, project_id, task, action_params
                    )

            elif execution_method == 'playbook':
                # Pack has playbooks - find and execute the first/default one
                playbooks = registry.get_capability_playbooks(pack_id)
                if not playbooks:
                    raise ValueError(f"Pack {pack_id} marked as playbook but no playbooks found")

                # Try to find playbook by common naming patterns
                from ..playbook_loader import PlaybookLoader
                playbook_loader = PlaybookLoader()

                playbook_found = None
                # Extract playbook codes from manifest playbooks list
                # playbooks in manifest are filenames like "storyboard_from_outline.yaml"
                # playbook_code in yaml file is "storyboard_from_outline"
                playbook_codes_to_try = []

                # Try exact pack_id first (in case pack_id itself is a playbook)
                playbook_codes_to_try.append(pack_id)

                # Extract playbook_code from filenames (remove .yaml/.yml extension)
                for playbook_filename in playbooks:
                    # Remove extension to get base name
                    base_name = playbook_filename.replace('.yaml', '').replace('.yml', '')
                    playbook_codes_to_try.append(base_name)

                logger.info(f"Looking for playbook for pack {pack_id}, trying codes: {playbook_codes_to_try}")

                for playbook_code in playbook_codes_to_try:
                    try:
                        playbook = playbook_loader.get_playbook_by_code(playbook_code)
                        if playbook:
                            # Use the actual playbook_code from the loaded playbook (may differ from filename)
                            playbook_found = playbook.metadata.playbook_code
                            logger.info(f"Found playbook {playbook_found} for pack {pack_id} (searched with: {playbook_code})")
                            break
                    except Exception as e:
                        logger.debug(f"Playbook {playbook_code} not found: {e}")
                        continue

                # If still not found, try loading all playbooks and matching by code
                if not playbook_found:
                    logger.info(f"Trying to load all playbooks to find match for pack {pack_id}")
                    try:
                        all_playbooks = playbook_loader.load_all_playbooks()
                        logger.info(f"Loaded {len(all_playbooks)} total playbooks, searching for pack {pack_id}")
                        for playbook in all_playbooks:
                            pb_code = playbook.metadata.playbook_code
                            # Try matching by playbook_code
                            if pb_code in playbook_codes_to_try:
                                playbook_found = pb_code
                                logger.info(f"Found playbook {playbook_found} for pack {pack_id} via full search (exact match)")
                                break
                            # Try matching by pack_id in playbook_code
                            if pack_id.lower() in pb_code.lower():
                                playbook_found = pb_code
                                logger.info(f"Found playbook {playbook_found} for pack {pack_id} via full search (partial match)")
                                break
                        if not playbook_found:
                            logger.warning(f"Available playbook codes: {[p.metadata.playbook_code for p in all_playbooks[:10]]}")
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
                    # Log detailed information for debugging
                    logger.error(
                        f"Could not find playbook for pack {pack_id}. "
                        f"Tried codes: {playbook_codes_to_try}. "
                        f"Available playbooks in manifest: {playbooks}"
                    )
                    error_msg = i18n.t(
                        "conversation_orchestrator",
                        "error.could_not_find_playbook",
                        pack_id=pack_id,
                        tried=str(playbook_codes_to_try)
                    )
                    raise ValueError(error_msg)

            else:
                # Unknown execution method - try ExecutionPlan as fallback
                logger.warning(f"Pack {pack_id} has unknown execution method, trying ExecutionPlan as fallback")
                result = await self._execute_via_plan(
                    pack_id, ctx, original_message_id,
                    files, message, project_id, task, action_params
                )

            logger.info(f"Successfully executed pack {pack_id} from pending task")

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

            # Update task status to FAILED if task exists
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
                    auto_execute=True,
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
