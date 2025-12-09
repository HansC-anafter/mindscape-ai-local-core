"""
Playbook Runner Service
Handles Playbook execution with real LLM-powered conversations
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_service import PlaybookService
from backend.app.services.stores.tool_calls_store import ToolCallsStore
from backend.app.services.stores.stage_results_store import StageResultsStore
from backend.app.services.conversation.workflow_tracker import WorkflowTracker
from backend.app.services.playbook import (
    PlaybookConversationManager,
    PlaybookToolExecutor,
    ExecutionStateStore,
    StepEventRecorder,
    PlaybookLLMProviderManager,
    ToolListLoader,
    PlaybookTaskManager
)
from backend.app.services.story_thread.context_injector import StoryThreadContextInjector

logger = logging.getLogger(__name__)




class PlaybookRunner:
    """Main Playbook execution service"""

    def __init__(self, config_store=None):
        self.store = MindscapeStore()
        # Use PlaybookService instead of PlaybookLoader
        self.playbook_service = PlaybookService(store=config_store)
        # Import here to avoid circular dependency
        if config_store is None:
            from backend.app.services.config_store import ConfigStore
            config_store = ConfigStore()
        self.config_store = config_store
        self.llm_manager = None  # Will be initialized per-profile
        self.active_conversations: Dict[str, PlaybookConversationManager] = {}
        self.tool_calls_store = ToolCallsStore(db_path=self.store.db_path)
        self.stage_results_store = StageResultsStore(db_path=self.store.db_path)
        self.workflow_tracker = WorkflowTracker(self.store)
        # Initialize modular components
        self.tool_executor = PlaybookToolExecutor(self.store, self.workflow_tracker)
        self.state_store = ExecutionStateStore(self.store)
        self.step_recorder = StepEventRecorder(
            self.store,
            self.workflow_tracker,
            self.tool_calls_store,
            self.state_store
        )
        self.llm_provider_manager = PlaybookLLMProviderManager(self.config_store)
        self.task_manager = PlaybookTaskManager(self.store)
        self.context_injector = StoryThreadContextInjector()


    async def _run_tool(
        self,
        tool_fqn: str,
        profile_id: str = None,
        workspace_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        step_id: Optional[str] = None,
        factory_cluster: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Unified tool execution entry point (delegates to PlaybookToolExecutor)

        This method provides a single entry point for all tool calls from Playbooks.
        It routes to capability package tools via registry, or falls back to legacy services.

        Args:
            tool_fqn: Fully qualified tool name (e.g., "major_proposal.import_template_from_files")
            profile_id: Profile ID (optional, for event recording)
            **kwargs: Parameters to pass to the tool

        Returns:
            Tool execution result
        """
        return await self.tool_executor.execute_tool(
            tool_fqn=tool_fqn,
                        profile_id=profile_id,
                        workspace_id=workspace_id,
            execution_id=execution_id,
            step_id=step_id,
            factory_cluster=factory_cluster,
            **kwargs
        )

    async def start_playbook_execution(
        self,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        target_language: Optional[str] = None,
        variant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Start a new Playbook execution

        Args:
            playbook_code: Base Playbook code
            profile_id: User profile ID
            inputs: Optional execution inputs
            workspace_id: Optional workspace ID
            target_language: Target language for output
            variant_id: Optional personalized variant ID to use
        """
        try:
            # Inject Story Thread context if thread_id is provided
            thread_id = inputs.get("thread_id") if inputs else None
            if thread_id and inputs:
                inputs = await self.context_injector.inject_context(
                    execution_id="",  # Will be set later
                    thread_id=thread_id,
                    inputs=inputs,
                )

            # Use PlaybookService to get playbook
            locale = inputs.get("locale") if inputs else None
            if not locale and workspace_id:
                try:
                    workspace = self.store.get_workspace(workspace_id)
                    locale = workspace.default_locale if workspace else None
                except Exception:
                    pass
            if not locale:
                locale = "zh-TW"

            playbook = await self.playbook_service.get_playbook(
                playbook_code=playbook_code,
                locale=locale,
                workspace_id=workspace_id
            )
            if not playbook:
                raise ValueError(f"Playbook not found: {playbook_code}")

            # Get playbook.run to check for playbook.json
            from backend.app.services.playbook_loaders.json_loader import PlaybookJsonLoader
            playbook_json = PlaybookJsonLoader.load_playbook_json(playbook_code)

            # Determine total_steps from playbook.json if available
            total_steps = 1  # Default to 1 for conversation mode
            if playbook_json and playbook_json.steps:
                total_steps = len(playbook_json.steps)
                logger.info(f"PlaybookRunner: Playbook {playbook_code} has JSON with {total_steps} steps")
            else:
                logger.info(f"PlaybookRunner: Playbook {playbook_code} using conversation mode (no JSON)")

            # Check for personalized variant
            # TODO: Re-implement variant support using PlaybookService or PlaybookRegistry
            # PlaybookStore has been removed, variant functionality is temporarily disabled
            variant = None
            if variant_id:
                logger.warning(f"Variant support is temporarily disabled. variant_id={variant_id} will be ignored.")
            # Note: skip_steps and custom_checklist will be handled during execution

            profile = self.store.get_profile(profile_id)

            project_obj = None
            project_sandbox_path = None
            if project_id:
                from backend.app.services.project.project_manager import ProjectManager
                from backend.app.services.sandbox.playbook_integration import SandboxPlaybookAdapter
                project_manager = ProjectManager(self.store)
                project_obj = await project_manager.get_project(project_id, workspace_id=workspace_id)
                if project_obj:
                    logger.info(f"Playbook execution in Project mode: {project_id}")
                    sandbox_adapter = SandboxPlaybookAdapter(self.store)
                    try:
                        sandbox_id = await sandbox_adapter.get_or_create_sandbox_for_project(
                            project_id=project_id,
                            workspace_id=workspace_id
                        )
                        project_sandbox_path = await sandbox_adapter.get_sandbox_path_for_compatibility(
                            project_id=project_id,
                            workspace_id=workspace_id
                        )
                        logger.info(f"Using unified sandbox {sandbox_id} for project {project_id}: {project_sandbox_path}")
                        context["sandbox_id"] = sandbox_id
                    except Exception as e:
                        logger.warning(f"Failed to get unified sandbox, falling back to legacy: {e}")
                        from backend.app.services.project.project_sandbox_manager import ProjectSandboxManager
                        sandbox_manager = ProjectSandboxManager(self.store)
                        try:
                            project_sandbox_path = await sandbox_manager.get_sandbox_path(project_id, workspace_id)
                            logger.info(f"Using legacy project sandbox: {project_sandbox_path}")
                        except Exception as e2:
                            logger.warning(f"Failed to get project sandbox: {e2}")
                else:
                    logger.warning(f"Project {project_id} not found, continuing without Project mode")
            elif inputs and "project_id" in inputs:
                # Support legacy project_id in inputs
                project_id_from_inputs = inputs.get("project_id")
                if project_id_from_inputs:
                    from backend.app.services.project.project_manager import ProjectManager
                    project_manager = ProjectManager(self.store)
                    project_obj = await project_manager.get_project(
                        project_id_from_inputs,
                        workspace_id=workspace_id
                    )
                    if project_obj:
                        project_id = project_id_from_inputs
                        logger.info(f"Playbook execution in Project mode (from inputs): {project_id}")

            execution_id = str(uuid.uuid4())

            # Re-inject context with execution_id if thread_id exists
            thread_id = inputs.get("thread_id") if inputs else None
            if thread_id and inputs:
                inputs = await self.context_injector.inject_context(
                    execution_id=execution_id,
                    thread_id=thread_id,
                    inputs=inputs,
                )

            # Create Task record for execution session (required for ExecutionSession view model)
            if workspace_id:
                self.task_manager.create_execution_task(
                        execution_id=execution_id,
                    workspace_id=workspace_id,
                        profile_id=profile_id,
                    playbook_code=playbook_code,
                    playbook_name=playbook.metadata.name,
                    inputs=inputs,
                    total_steps=total_steps
                )

            final_target_language = (
                target_language or
                (inputs.get("target_language") if inputs else None) or
                None
            )
            final_locale = (
                inputs.get("locale") if inputs else None
            )

            # Check for auto_execute mode in inputs
            auto_execute = inputs.get("auto_execute", False) if inputs else False

            conv_manager = PlaybookConversationManager(
                playbook=playbook,
                profile=profile,
                project=project_obj,  # Use project_obj from Project Manager
                locale=final_locale,
                target_language=final_target_language,
                workspace_id=workspace_id,
                auto_execute=auto_execute
            )

            if auto_execute:
                logger.info(f"PlaybookRunner: Auto-execute mode enabled for execution {execution_id}")

            # Set project sandbox path in inputs if available
            if project_sandbox_path and inputs:
                inputs["project_sandbox_path"] = str(project_sandbox_path)
                logger.info(f"Project sandbox path set in inputs: {project_sandbox_path}")

            # Preload and cache tools list for this workspace (with Redis cache support)
            if workspace_id:
                profile_id_for_tools = profile_id if profile else None
                cached_tools_str = ToolListLoader.load_tools_for_workspace(
                    workspace_id=workspace_id,
                    profile_id=profile_id_for_tools
                )
                if cached_tools_str:
                    conv_manager.cached_tools_str = cached_tools_str
                    logger.info(f"PlaybookRunner: Loaded {len(cached_tools_str)} characters of tools list for workspace {workspace_id}")
                else:
                    logger.warning(f"PlaybookRunner: Failed to load tools list for workspace {workspace_id}, playbook may not have access to tools")

            # Store variant info in conversation manager for later use
            if variant:
                conv_manager.variant = variant
                conv_manager.skip_steps = variant.get("skip_steps", [])
                conv_manager.custom_checklist = variant.get("custom_checklist", [])
                # Apply execution params
                if variant.get("execution_params"):
                    if inputs:
                        inputs.update(variant["execution_params"])
                    else:
                        inputs = variant["execution_params"]

            self.active_conversations[execution_id] = conv_manager

            # Get LLM provider with profile-specific keys
            llm_manager = self.llm_provider_manager.get_llm_manager(profile_id)
            provider = self.llm_provider_manager.get_llm_provider(llm_manager)

            # Add a user message to start the conversation
            # Priority: user's original message > i18n string > default
            from backend.app.shared.i18n_loader import load_i18n_string
            default_start_message = load_i18n_string(
                "playbook.start_execution",
                locale=conv_manager.locale,
                default="Starting Playbook execution."
            )
            # Use user's original message if provided in inputs, otherwise use i18n default
            user_message = None
            if inputs:
                user_message = inputs.get("user_message") or inputs.get("message") or inputs.get("original_message")
            initial_message = user_message if user_message else default_start_message
            conv_manager.add_user_message(initial_message)

            messages = conv_manager.get_messages_for_llm()
            # Get model name from system settings
            model_name = self.llm_provider_manager.get_model_name()
            logger.info(f"PlaybookRunner: Calling LLM for playbook {playbook_code}, model={model_name}, messages_count={len(messages)}")
            assistant_response = await provider.chat_completion(messages, model=model_name if model_name else None)
            logger.info(f"PlaybookRunner: LLM response received for playbook {playbook_code}, response_length={len(assistant_response) if assistant_response else 0}")

            conv_manager.add_assistant_message(assistant_response)

            # Parse and execute tool calls (with loop support for multiple iterations)
            # Use tool executor for tool execution loop
            logger.info(f"PlaybookRunner: Starting tool execution loop for {execution_id}")
            model_name = self.llm_provider_manager.get_model_name()
            context = inputs or {}
            sandbox_id_from_context = context.get("sandbox_id")
            try:
                assistant_response, used_tools = await self.tool_executor.execute_tool_loop(
                    conv_manager=conv_manager,
                    assistant_response=assistant_response,
                    execution_id=execution_id,
                    profile_id=profile_id,
                    provider=provider,
                    model_name=model_name,
                    workspace_id=workspace_id,
                    sandbox_id=sandbox_id_from_context
                )
                logger.info(f"PlaybookRunner: Tool execution loop completed for {execution_id}, used_tools={len(used_tools) if used_tools else 0}")
            except Exception as e:
                logger.error(f"PlaybookRunner: Tool execution loop failed for {execution_id}: {e}", exc_info=True)
                # Continue execution even if tool loop fails
                used_tools = []

            # Extract structured output and check if complete
            structured_output = conv_manager.extract_structured_output(assistant_response)
            is_complete = structured_output is not None

            # Record playbook step event for initial LLM response
            project_id = inputs.get("project_id") if inputs else None
            playbook_code = playbook.metadata.playbook_code if playbook else None
            step_event, total_steps = self.step_recorder.record_initial_step(
                    execution_id=execution_id,
                    profile_id=profile_id,
                        workspace_id=workspace_id,
                playbook_code=playbook_code,
                conv_manager=conv_manager,
                assistant_response=assistant_response,
                playbook_json=playbook_json,
                playbook=playbook,
                project_id=project_id
            )

            # Finalize step with structured output if complete
            if is_complete and structured_output and step_event:
                self.step_recorder.finalize_step_with_output(
                    step_event=step_event,
                    execution_id=execution_id,
                    structured_output=structured_output
                )

            # Store structured output if complete
            if is_complete:
                conv_manager.extracted_data = structured_output

            # Update task status and cleanup if execution is complete
            if is_complete:
                self.task_manager.update_task_status_to_succeeded(
                    execution_id=execution_id,
                    structured_output=structured_output
                )
                # Cleanup execution from active_conversations
                self.cleanup_execution(execution_id)
                logger.info(f"Cleaned up execution {execution_id} from active_conversations")

            # Save initial execution state to database
            try:
                await self.state_store.save_execution_state(execution_id, conv_manager)
            except Exception as e:
                logger.warning(f"Failed to save initial execution state: {e}", exc_info=True)

            result = {
                "execution_id": execution_id,
                "playbook_code": playbook_code,
                "playbook_name": playbook.metadata.name,
                "message": assistant_response,
                "is_complete": is_complete,
                "conversation_history": conv_manager.conversation_history
            }

            # Extract and update Story Thread context if thread_id exists
            thread_id = inputs.get("thread_id") if inputs else None
            if thread_id:
                try:
                    await self.context_injector.extract_context_updates(
                        execution_id=execution_id,
                        thread_id=thread_id,
                        execution_result=result,
                    )
                except Exception as e:
                    logger.warning(f"Failed to extract Story Thread context updates: {e}", exc_info=True)

            return result

        except Exception as e:
            logger.error(f"Failed to start playbook execution: {e}", exc_info=True)
            # Update task status to FAILED if task was created
            if workspace_id:
                self.task_manager.update_task_status_to_failed(execution_id, str(e))
            raise

    async def continue_playbook_execution(
        self,
        execution_id: str,
        user_message: str,
        profile_id: str = "default-user"
    ) -> Dict[str, Any]:
        """Continue an ongoing Playbook execution"""
        try:
            # Get conversation manager from memory first
            conv_manager = self.active_conversations.get(execution_id)

            # If not in memory, try to restore from database
            if not conv_manager:
                logger.info(f"Execution {execution_id} not in memory, attempting to restore from database")
                conv_manager = await self.state_store.restore_execution_state(execution_id, self.playbook_service)

                if conv_manager:
                    # Restore to memory for future interactions
                    self.active_conversations[execution_id] = conv_manager
                    logger.info(f"Successfully restored execution {execution_id} from database")
                else:
                    raise ValueError(f"Execution not found: {execution_id}")

            # Add user message
            conv_manager.add_user_message(user_message)

            # Record user message event
            try:
                project_id = getattr(conv_manager.project, 'id', None) if conv_manager.project else None
                event = MindEvent(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                    actor=EventActor.USER,
                    channel="playbook",
                    profile_id=profile_id,
                    project_id=project_id,
                    workspace_id=conv_manager.workspace_id,
                    event_type=EventType.MESSAGE,
                    payload={
                        "execution_id": execution_id,
                        "playbook_code": conv_manager.playbook.metadata.playbook_code if conv_manager.playbook else None,
                        "message": user_message[:500],
                        "role": "user"
                    },
                    entity_ids=[project_id] if project_id else [],
                    metadata={}
                )
                self.store.create_event(event)
            except Exception as e:
                logger.warning(f"Failed to record user message event: {e}")

            # Get LLM provider with profile-specific keys
            llm_manager = self.llm_provider_manager.get_llm_manager(profile_id)
            provider = self.llm_provider_manager.get_llm_provider(llm_manager)

            messages = conv_manager.get_messages_for_llm()
            # Get model name from system settings
            model_name = self.llm_provider_manager.get_model_name()
            assistant_response = await provider.chat_completion(messages, model=model_name if model_name else None)

            conv_manager.add_assistant_message(assistant_response)

            # Parse and execute tool calls (with loop support for multiple iterations)
            # Use tool executor for tool execution loop
            model_name = self.llm_provider_manager.get_model_name()
            workspace_id = conv_manager.workspace_id
            # Get sandbox_id from conv_manager's execution context if available
            sandbox_id_from_context = getattr(conv_manager, 'sandbox_id', None)
            assistant_response, used_tools = await self.tool_executor.execute_tool_loop(
                conv_manager=conv_manager,
                assistant_response=assistant_response,
                execution_id=execution_id,
                profile_id=profile_id,
                provider=provider,
                model_name=model_name,
                workspace_id=workspace_id,
                sandbox_id=sandbox_id_from_context
            )

            # Extract structured output and check if complete
            structured_output = conv_manager.extract_structured_output(assistant_response)
            is_complete = structured_output is not None

            # Record assistant message and playbook step event
            project_id = getattr(conv_manager.project, 'id', None) if conv_manager.project else None
            playbook_code = conv_manager.playbook.metadata.playbook_code if conv_manager.playbook else None
            workspace_id = conv_manager.workspace_id

            step_event, total_steps = self.step_recorder.record_continuation_step(
                execution_id=execution_id,
                    profile_id=profile_id,
                    workspace_id=workspace_id,
                playbook_code=playbook_code,
                conv_manager=conv_manager,
                assistant_response=assistant_response,
                    used_tools=used_tools,
                project_id=project_id
                )

            # Finalize step with structured output if complete
            if is_complete and structured_output and step_event:
                self.step_recorder.finalize_step_with_output(
                    step_event=step_event,
                        execution_id=execution_id,
                    structured_output=structured_output
                )

            # Store structured output if complete
            if is_complete:
                conv_manager.extracted_data = structured_output

            # Update task status and cleanup if execution is complete
            if is_complete:
                self.task_manager.update_task_status_to_succeeded(
                    execution_id=execution_id,
                    structured_output=structured_output
                )
                # Cleanup execution from active_conversations
                self.cleanup_execution(execution_id)
                logger.info(f"Cleaned up execution {execution_id} from active_conversations")

            # Observe habits from playbook execution (background, don't block response)
            if is_complete:
                try:
                    profile = conv_manager.profile
                    playbook = conv_manager.playbook
                    playbook_code = playbook.metadata.playbook_code if playbook else None

                    # Observe habits from playbook execution via capability tool
                    tool_name = "habit_learning.observe_playbook_execution"
                    try:
                        await self._run_tool(
                            tool_name,
                            profile_id=profile_id,
                            playbook_code=playbook_code,
                            execution_data={
                                "execution_id": execution_id,
                                "conversation_length": len(conv_manager.conversation_history),
                            },
                            project_id=getattr(conv_manager.project, 'id', None) if conv_manager.project else None
                        )
                    except ValueError as e:
                        # Tool not found in registry - log warning but don't fail execution
                        logger.warning(f"Tool {tool_name} not found in capability registry: {e}")
                except Exception as e:
                    logger.warning(f"Failed to observe habits from playbook execution: {e}")

            # Save execution state to database after each interaction
            await self.state_store.save_execution_state(execution_id, conv_manager)

            result = {
                "execution_id": execution_id,
                "message": assistant_response,
                "is_complete": is_complete,
                "structured_output": structured_output,
                "conversation_history": conv_manager.conversation_history
            }

            # Extract and update Story Thread context if thread_id exists
            execution_state = await self.state_store.get_execution_state(execution_id)
            if execution_state and execution_state.get("inputs"):
                thread_id = execution_state["inputs"].get("thread_id")
                if thread_id:
                    try:
                        await self.context_injector.extract_context_updates(
                            execution_id=execution_id,
                            thread_id=thread_id,
                            execution_result=result,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to extract Story Thread context updates: {e}", exc_info=True)

            return result

        except Exception as e:
            logger.error(f"Failed to continue playbook execution: {e}")
            raise


    async def get_playbook_execution_result(
        self,
        execution_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the final structured output from a completed execution"""
        conv_manager = self.active_conversations.get(execution_id)
        if not conv_manager:
            # Execution is not in active_conversations
            # This means it was cleaned up, which happens when execution completes
            # Return a completion status to indicate the execution finished
            return {
                "status": "completed",
                "execution_id": execution_id,
                "note": "Execution completed (conversation mode, no structured output)"
            }

        # If execution is still active but has extracted_data, return it
        if conv_manager.extracted_data:
            return conv_manager.extracted_data

        # Execution is active but no structured output yet
        return None

    def cleanup_execution(self, execution_id: str):
        """Clean up completed execution from memory"""
        if execution_id in self.active_conversations:
            del self.active_conversations[execution_id]

    def list_active_executions(self) -> List[str]:
        """List all active execution IDs"""
        return list(self.active_conversations.keys())
