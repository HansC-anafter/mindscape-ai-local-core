"""
Playbook Runner Service
Handles Playbook execution with real LLM-powered conversations
"""

import os
import logging
import uuid
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from ..models.mindscape import MindscapeProfile, MindEvent, EventType, EventActor
from ..models.playbook import Playbook
from .mindscape_store import MindscapeStore
from .playbook_loader import PlaybookLoader
from .agent_runner import LLMProviderManager
from .stores.tool_calls_store import ToolCallsStore, ToolCall
from .stores.stage_results_store import StageResultsStore, StageResult
from .conversation.workflow_tracker import WorkflowTracker
from ..shared.tool_executor import execute_tool
from ..shared.i18n_loader import get_locale_from_context
from ..capabilities.registry import get_registry

logger = logging.getLogger(__name__)


class PlaybookConversationManager:
    """Manages multi-turn conversations for Playbook execution"""

    def __init__(
        self,
        playbook: Playbook,
        profile: Optional[MindscapeProfile] = None,
        project: Optional[Any] = None,
        locale: Optional[str] = None,
        target_language: Optional[str] = None,
        workspace_id: Optional[str] = None
    ):
        self.playbook = playbook
        self.profile = profile
        self.project = project
        self.workspace_id = workspace_id
        if target_language:
            self.target_language = target_language
            self.locale = target_language
        else:
            workspace = None
            if workspace_id:
                try:
                    from ..services.mindscape_store import MindscapeStore
                    store = MindscapeStore()
                    workspace = store.get_workspace(workspace_id)
                except Exception:
                    pass
            self.locale = locale or get_locale_from_context(profile=profile, workspace=workspace, project=project)
            self.target_language = self.locale
        self.conversation_history: List[Dict[str, str]] = []
        self.extracted_data: Dict[str, Any] = {}
        self.current_step = 0
        self.variant: Optional[Dict[str, Any]] = None
        self.skip_steps: List[int] = []
        self.custom_checklist: List[str] = []

    def build_system_prompt(self) -> str:
        """Build system prompt for Playbook execution"""
        prompt_parts = []

        # Playbook role and instructions
        prompt_parts.append(f"[PLAYBOOK: {self.playbook.metadata.name}]")
        prompt_parts.append(self.playbook.sop_content)
        prompt_parts.append("[/PLAYBOOK]")

        # Add variant customizations if present
        if self.variant:
            if self.skip_steps:
                prompt_parts.append(f"\n[SKIP_STEPS]")
                prompt_parts.append(f"Skip the following steps: {', '.join(map(str, self.skip_steps))}")
                prompt_parts.append("[/SKIP_STEPS]")

            if self.custom_checklist:
                prompt_parts.append(f"\n[CUSTOM_CHECKLIST]")
                prompt_parts.append("Additional checklist items:")
                for item in self.custom_checklist:
                    prompt_parts.append(f"- {item}")
                prompt_parts.append("[/CUSTOM_CHECKLIST]")

        # User context
        if self.profile and self.profile.self_description:
            prompt_parts.append("\n[USER_CONTEXT]")
            desc = self.profile.self_description
            prompt_parts.append(f"Identity: {desc.get('identity', 'N/A')}")
            prompt_parts.append(f"Current Goal: {desc.get('solving', 'N/A')}")
            prompt_parts.append(f"Challenges: {desc.get('thinking', 'N/A')}")
            prompt_parts.append("[/USER_CONTEXT]")

        prompt_parts.append("\n[LANGUAGE_INSTRUCTION]")
        prompt_parts.append(f"Always respond in {self.target_language}.")
        prompt_parts.append(f"Use terminology appropriate for {self.target_language} locale.")
        prompt_parts.append(f"Maintain a conversational, friendly tone in {self.target_language}.")
        prompt_parts.append("[/LANGUAGE_INSTRUCTION]")

        # Execution instructions
        prompt_parts.append("\n[EXECUTION_INSTRUCTIONS]")
        prompt_parts.append("Follow the SOP steps exactly as described.")
        prompt_parts.append("At the end, output structured JSON with the key 'STRUCTURED_OUTPUT'.")
        prompt_parts.append("[/EXECUTION_INSTRUCTIONS]")

        return "\n".join(prompt_parts)

    def add_user_message(self, message: str):
        """Add user message to conversation history"""
        self.conversation_history.append({
            "role": "user",
            "content": message
        })

    def add_assistant_message(self, message: str):
        """Add assistant message to conversation history"""
        self.conversation_history.append({
            "role": "assistant",
            "content": message
        })

    def get_messages_for_llm(self) -> List[Dict[str, str]]:
        """Get formatted messages for LLM API"""
        messages = [
            {"role": "system", "content": self.build_system_prompt()}
        ]
        messages.extend(self.conversation_history)
        return messages

    def extract_structured_output(self, assistant_message: str) -> Optional[Dict[str, Any]]:
        """Extract structured JSON output from assistant message"""
        try:
            # Look for JSON in the message
            # Pattern 1: STRUCTURED_OUTPUT: {...}
            pattern1 = r'STRUCTURED_OUTPUT:\s*(\{.*\})'
            match = re.search(pattern1, assistant_message, re.DOTALL)

            if match:
                json_str = match.group(1)
                return json.loads(json_str)

            # Pattern 2: Any JSON object in the message
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            matches = re.findall(json_pattern, assistant_message, re.DOTALL)

            if matches:
                # Try to parse the last (most complete) JSON
                for json_str in reversed(matches):
                    try:
                        data = json.loads(json_str)
                        # Check if it looks like playbook output
                        if any(key in data for key in ['project_data', 'work_rhythm_data', 'onboarding_task']):
                            return data
                    except:
                        continue

            return None

        except Exception as e:
            logger.error(f"Failed to extract structured output: {e}")
            return None


class PlaybookRunner:
    """Main Playbook execution service"""

    def __init__(self, config_store=None):
        self.store = MindscapeStore()
        self.playbook_loader = PlaybookLoader()
        # Import here to avoid circular dependency
        if config_store is None:
            from .config_store import ConfigStore
            config_store = ConfigStore()
        self.config_store = config_store
        self.llm_manager = None  # Will be initialized per-profile
        self.active_conversations: Dict[str, PlaybookConversationManager] = {}
        self.tool_calls_store = ToolCallsStore(db_path=self.store.db_path)
        self.stage_results_store = StageResultsStore(db_path=self.store.db_path)
        self.workflow_tracker = WorkflowTracker(self.store)

    def _get_llm_manager(self, profile_id: str) -> LLMProviderManager:
        """Get LLM manager with profile-specific API keys"""
        # Get user config
        config = self.config_store.get_or_create_config(profile_id)

        # Use user-configured keys, fallback to env vars
        openai_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
        anthropic_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        vertex_api_key = config.agent_backend.vertex_api_key or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("VERTEX_API_KEY")
        vertex_project_id = config.agent_backend.vertex_project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT_ID")
        vertex_location = config.agent_backend.vertex_location or os.getenv("VERTEX_LOCATION", "us-central1")

        return LLMProviderManager(
            openai_key=openai_key,
            anthropic_key=anthropic_key,
            vertex_api_key=vertex_api_key,
            vertex_project_id=vertex_project_id,
            vertex_location=vertex_location
        )

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
        Unified tool execution entry point

        This method provides a single entry point for all tool calls from Playbooks.
        It routes to capability package tools via registry, or falls back to legacy services.

        Args:
            tool_fqn: Fully qualified tool name (e.g., "major_proposal.import_template_from_files")
            profile_id: Profile ID (optional, for event recording)
            **kwargs: Parameters to pass to the tool

        Returns:
            Tool execution result
        """
        tool_start_time = datetime.utcnow()
        tool_call_id = str(uuid.uuid4())

        # Determine factory_cluster from tool_fqn if not provided
        if not factory_cluster:
            if "mcp" in tool_fqn.lower() or tool_fqn.startswith("local_"):
                factory_cluster = "local_mcp"
            elif "sem-" in tool_fqn.lower():
                factory_cluster = "sem-hub"
            elif "wp" in tool_fqn.lower() or "wordpress" in tool_fqn.lower():
                factory_cluster = "wp-hub"
            elif "n8n" in tool_fqn.lower():
                factory_cluster = "n8n"
            else:
                factory_cluster = "local_mcp"  # default

        # Create ToolCall record (pending status) using WorkflowTracker
        tool_call = None
        if execution_id:
            try:
                tool_call = self.workflow_tracker.record_tool_call_start(
                    execution_id=execution_id,
                    step_id=step_id or "",
                    tool_name=tool_fqn,
                    parameters=kwargs,
                    factory_cluster=factory_cluster
                )
            except Exception as e:
                logger.warning(f"Failed to create ToolCall record: {e}")

        try:
            # Try capability package tool first
            registry = get_registry()
            if registry.get_tool(tool_fqn):
                logger.debug(f"Calling capability tool via registry: {tool_fqn}")
                result = await execute_tool(tool_fqn, **kwargs)

                tool_end_time = datetime.utcnow()
                duration_ms = int((tool_end_time - tool_start_time).total_seconds() * 1000)

                # Update ToolCall record (completed status) using WorkflowTracker
                if execution_id and tool_call:
                    try:
                        self.workflow_tracker.record_tool_call_complete(
                            tool_call_id=tool_call.id,
                            response={"result": str(result)[:1000]} if result else {"result": result}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update ToolCall record: {e}")

                # Record tool call event (for backward compatibility)
                if profile_id:
                    try:
                        project_id = kwargs.get("project_id")
                        event = MindEvent(
                            id=str(uuid.uuid4()),
                            timestamp=tool_end_time,
                            actor=EventActor.ASSISTANT,
                            channel="playbook",
                            profile_id=profile_id,
                            project_id=project_id,
                            workspace_id=workspace_id,
                            event_type=EventType.TOOL_CALL,
                            payload={
                                "tool_fqn": tool_fqn,
                                "tool_call_id": tool_call_id,
                                "execution_id": execution_id,
                                "step_id": step_id,
                                "status": "completed",
                                "duration_seconds": (tool_end_time - tool_start_time).total_seconds()
                            },
                            entity_ids=[project_id] if project_id else [],
                            metadata={
                                "tool_params": {k: str(v)[:100] for k, v in kwargs.items() if k != "project_id"},
                                "factory_cluster": factory_cluster
                            }
                        )
                        self.store.create_event(event)
                    except Exception as e:
                        logger.warning(f"Failed to record tool call event: {e}")

                return result

            # Tool not found in registry - this is expected for legacy services
            # that haven't been migrated yet. We'll handle fallback in specific cases.
            logger.debug(f"Tool {tool_fqn} not found in capability registry")
            raise ValueError(f"Tool {tool_fqn} not found in capability registry")

        except Exception as e:
            tool_end_time = datetime.utcnow()

            # Update ToolCall record (failed status) using WorkflowTracker
            if execution_id and tool_call:
                try:
                    self.workflow_tracker.record_tool_call_fail(
                        tool_call_id=tool_call.id,
                        error=str(e)[:1000]
                    )
                except Exception as e2:
                    logger.warning(f"Failed to update ToolCall record: {e2}")

            # Record failed tool call event (for backward compatibility)
            if profile_id:
                try:
                    project_id = kwargs.get("project_id")
                    event = MindEvent(
                        id=str(uuid.uuid4()),
                        timestamp=tool_end_time,
                        actor=EventActor.SYSTEM,
                        channel="playbook",
                        profile_id=profile_id,
                        project_id=project_id,
                        workspace_id=workspace_id,
                        event_type=EventType.TOOL_CALL,
                        payload={
                            "tool_fqn": tool_fqn,
                            "tool_call_id": tool_call_id,
                            "execution_id": execution_id,
                            "step_id": step_id,
                            "status": "failed",
                            "error_message": str(e)[:500],
                            "duration_seconds": (tool_end_time - tool_start_time).total_seconds()
                        },
                        entity_ids=[project_id] if project_id else [],
                        metadata={
                            "factory_cluster": factory_cluster
                        }
                    )
                    self.store.create_event(event)
                except Exception as e2:
                    logger.warning(f"Failed to record failed tool call event: {e2}")

            logger.error(f"Failed to execute tool {tool_fqn}: {e}")
            raise

    async def start_playbook_execution(
        self,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
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
            playbook = self.playbook_loader.get_playbook_by_code(playbook_code)
            if not playbook:
                raise ValueError(f"Playbook not found: {playbook_code}")

            # Check for personalized variant
            variant = None
            if variant_id:
                from .playbook_store import PlaybookStore
                store = PlaybookStore()
                variant = store.get_personalized_variant(variant_id)
                if variant and variant["profile_id"] == profile_id and variant["base_playbook_code"] == playbook_code:
                    # Apply variant customizations
                    if variant.get("personalized_sop_content"):
                        # Use personalized SOP
                        playbook.sop_content = variant["personalized_sop_content"]
                    # Note: skip_steps and custom_checklist will be handled during execution
            else:
                # Check for default variant
                from .playbook_store import PlaybookStore
                store = PlaybookStore()
                default_variant = store.get_default_variant(profile_id, playbook_code)
                if default_variant:
                    variant = default_variant
                    if variant.get("personalized_sop_content"):
                        playbook.sop_content = variant["personalized_sop_content"]

            profile = self.store.get_profile(profile_id)

            project = None
            if inputs and "project_id" in inputs:
                pass

            execution_id = str(uuid.uuid4())
            final_target_language = (
                target_language or
                (inputs.get("target_language") if inputs else None) or
                None
            )
            final_locale = (
                inputs.get("locale") if inputs else None
            )

            conv_manager = PlaybookConversationManager(
                playbook=playbook,
                profile=profile,
                project=project,
                locale=final_locale,
                target_language=final_target_language,
                workspace_id=workspace_id
            )

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
            llm_manager = self._get_llm_manager(profile_id)
            provider = llm_manager.get_provider()
            if not provider:
                raise ValueError("No LLM provider available. Please configure OpenAI or Anthropic API key in Settings.")

            # Add a user message to start the conversation
            from ..shared.i18n_loader import load_i18n_string
            start_message = load_i18n_string(
                "playbook.start_execution",
                locale=conv_manager.locale,
                default="Starting Playbook execution."
            )
            conv_manager.add_user_message(start_message)

            messages = conv_manager.get_messages_for_llm()
            assistant_response = await provider.chat_completion(messages)

            conv_manager.add_assistant_message(assistant_response)

            # Record playbook start event with full payload
            try:
                project_id = inputs.get("project_id") if inputs else None
                step_event_id = str(uuid.uuid4())
                event = MindEvent(
                    id=step_event_id,
                    timestamp=datetime.utcnow(),
                    actor=EventActor.USER,
                    channel="playbook",
                    profile_id=profile_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    event_type=EventType.PLAYBOOK_STEP,
                    payload={
                        "execution_id": execution_id,
                        "step_index": 0,
                        "step_name": "start",
                        "status": "running",
                        "step_type": "agent_action",
                        "agent_type": None,
                        "used_tools": [],
                        "description": start_message,
                        "log_summary": f"Starting Playbook execution: {playbook.metadata.name}",
                        "requires_confirmation": False,
                        "confirmation_status": None,
                        "started_at": datetime.utcnow().isoformat(),
                        "completed_at": None,
                        "playbook_code": playbook_code,
                        "playbook_name": playbook.metadata.name,
                        "step": "start",
                        "message": start_message[:200]
                    },
                    entity_ids=[project_id] if project_id else [],
                    metadata={
                        "locale": conv_manager.locale
                    }
                )
                self.store.create_event(event)
            except Exception as e:
                logger.warning(f"Failed to record playbook start event: {e}")

            return {
                "execution_id": execution_id,
                "playbook_code": playbook_code,
                "playbook_name": playbook.metadata.name,
                "message": assistant_response,
                "is_complete": False,
                "conversation_history": conv_manager.conversation_history
            }

        except Exception as e:
            logger.error(f"Failed to start playbook execution: {e}")
            raise

    async def continue_playbook_execution(
        self,
        execution_id: str,
        user_message: str,
        profile_id: str = "default-user"
    ) -> Dict[str, Any]:
        """Continue an ongoing Playbook execution"""
        try:
            # Get conversation manager
            conv_manager = self.active_conversations.get(execution_id)
            if not conv_manager:
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
            llm_manager = self._get_llm_manager(profile_id)
            provider = llm_manager.get_provider()
            if not provider:
                raise ValueError("No LLM provider available. Please configure OpenAI or Anthropic API key in Settings.")

            messages = conv_manager.get_messages_for_llm()
            assistant_response = await provider.chat_completion(messages)

            conv_manager.add_assistant_message(assistant_response)

            # Extract structured output and check if complete
            structured_output = conv_manager.extract_structured_output(assistant_response)
            is_complete = structured_output is not None

            # Update current step index
            conv_manager.current_step += 1

            # Record assistant message and playbook step event
            try:
                project_id = getattr(conv_manager.project, 'id', None) if conv_manager.project else None
                playbook_code = conv_manager.playbook.metadata.playbook_code if conv_manager.playbook else None
                workspace_id = conv_manager.workspace_id

                # Record assistant message
                message_event = MindEvent(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                    actor=EventActor.ASSISTANT,
                    channel="playbook",
                    profile_id=profile_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    event_type=EventType.MESSAGE,
                    payload={
                        "execution_id": execution_id,
                        "playbook_code": playbook_code,
                        "message": assistant_response[:500],
                        "role": "assistant"
                    },
                    entity_ids=[project_id] if project_id else [],
                    metadata={}
                )
                self.store.create_event(message_event)

                # Determine step information
                step_index = conv_manager.current_step
                step_name = f"Step {step_index}"
                step_type = "agent_action"  # Default, could be determined from playbook SOP
                agent_type = None  # Could be determined from playbook or response

                # Get tools used in this step from ToolCall records
                # Note: We'll update this after creating the step event if we have a step_id
                used_tools = []

                # Generate log_summary
                log_summary = f"Step {step_index}: {assistant_response[:100]}..." if assistant_response else f"Step {step_index}: Executing"

                # Record playbook step with full payload using WorkflowTracker
                step_event = self.workflow_tracker.create_playbook_step_event(
                    execution_id=execution_id,
                    step_index=step_index,
                    step_name=step_name,
                    status="completed" if is_complete else "running",
                    step_type=step_type,
                    agent_type=agent_type,
                    used_tools=used_tools,
                    description=assistant_response[:500] if assistant_response else None,
                    log_summary=log_summary,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    playbook_code=playbook_code
                )

                # Update step event with actual tools used in this step
                try:
                    tool_calls = self.tool_calls_store.list_tool_calls(
                        execution_id=execution_id,
                        step_id=step_event.id,
                        limit=100
                    )
                    if tool_calls:
                        # Get unique tool names from tool calls
                        used_tools = list(set([tc.tool_name for tc in tool_calls if tc.tool_name]))
                        # Update step event with actual tools
                        self.workflow_tracker.update_playbook_step_event(
                            step_event_id=step_event.id,
                            log_summary=log_summary
                        )
                        # Update payload with used_tools
                        step_event.payload["used_tools"] = used_tools
                        self.store.update_event(step_event)
                except Exception as e:
                    logger.warning(f"Failed to update step event with tool calls: {e}")

                # Generate embedding for completed steps with structured output
                if is_complete and structured_output:
                    try:
                        # Re-create event with embedding metadata (if needed)
                        # The event is already created by create_playbook_step_event,
                        # but we may need to update it with embedding metadata
                        step_event.metadata.update({
                            "has_structured_output": True,
                            "should_embed": True,
                            "is_artifact": True
                        })
                        self.store.update_event(step_event)
                        # Generate embedding if needed
                        if hasattr(self.store, 'generate_embedding'):
                            self.store.generate_embedding(step_event)
                    except Exception as e:
                        logger.warning(f"Failed to update step event with embedding metadata: {e}")

                step_event_id = step_event.id

                # Create StageResult if we have structured output using WorkflowTracker
                if is_complete and structured_output:
                    try:
                        self.workflow_tracker.create_stage_result(
                            execution_id=execution_id,
                            step_id=step_event_id,
                            stage_name="final_output",
                            result_type="draft",  # Could be determined from playbook or output structure
                            content=structured_output,
                            preview=str(structured_output)[:200] if structured_output else None,
                            requires_review=False
                        )
                    except Exception as e:
                        logger.warning(f"Failed to create StageResult: {e}")

            except Exception as e:
                logger.warning(f"Failed to record playbook step event: {e}")

            # Store structured output if complete
            if is_complete:
                conv_manager.extracted_data = structured_output

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

            return {
                "execution_id": execution_id,
                "message": assistant_response,
                "is_complete": is_complete,
                "structured_output": structured_output,
                "conversation_history": conv_manager.conversation_history
            }

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
            return None

        return conv_manager.extracted_data

    def cleanup_execution(self, execution_id: str):
        """Clean up completed execution from memory"""
        if execution_id in self.active_conversations:
            del self.active_conversations[execution_id]

    def list_active_executions(self) -> List[str]:
        """List all active execution IDs"""
        return list(self.active_conversations.keys())
