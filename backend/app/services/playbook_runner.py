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

from backend.app.models.mindscape import MindscapeProfile, MindEvent, EventType, EventActor
from backend.app.models.playbook import Playbook
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_service import PlaybookService
from backend.app.services.agent_runner import LLMProviderManager, LLMProvider
from backend.app.services.stores.tool_calls_store import ToolCallsStore, ToolCall
from backend.app.services.stores.stage_results_store import StageResultsStore, StageResult
from backend.app.services.conversation.workflow_tracker import WorkflowTracker
from backend.app.shared.tool_executor import execute_tool
from backend.app.shared.i18n_loader import get_locale_from_context
from backend.app.capabilities.registry import get_registry

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
                    from backend.app.services.mindscape_store import MindscapeStore
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
        self.cached_tools_str: Optional[str] = None  # Cache formatted tools string

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

        # Available tools (using cached tool list if available)
        if self.cached_tools_str:
            prompt_parts.append("\n[AVAILABLE_TOOLS]")
            prompt_parts.append(self.cached_tools_str)
            prompt_parts.append("\n\n**如何使用工具：**")
            prompt_parts.append("\n當你需要使用工具時，請使用以下格式輸出 JSON：")
            prompt_parts.append("\n**方式 1（推薦）**:")
            prompt_parts.append("```json")
            prompt_parts.append("{")
            prompt_parts.append('  "tool_call": {')
            prompt_parts.append('    "tool_name": "工具名稱",')
            prompt_parts.append('    "parameters": {')
            prompt_parts.append('      "參數1": "值1",')
            prompt_parts.append('      "參數2": "值2"')
            prompt_parts.append("    }")
            prompt_parts.append("  }")
            prompt_parts.append("}")
            prompt_parts.append("```")
            prompt_parts.append("\n**方式 2（簡化）**:")
            prompt_parts.append("```json")
            prompt_parts.append("{")
            prompt_parts.append('  "tool_name": "工具名稱",')
            prompt_parts.append('  "parameters": {')
            prompt_parts.append('    "參數1": "值1"')
            prompt_parts.append("  }")
            prompt_parts.append("}")
            prompt_parts.append("```")
            prompt_parts.append("\n工具調用後，系統會自動執行並將結果返回給你，你可以根據結果繼續處理。")
            prompt_parts.append("[/AVAILABLE_TOOLS]")

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

    def parse_tool_calls_from_response(self, assistant_message: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response.

        Uses shared JSON parser utility to extract tool calls from various formats:
        1. JSON object with tool_call field: {"tool_call": {"tool_name": "...", "parameters": {...}}}
        2. JSON in markdown code blocks: ```json\n{"tool_call": {...}}\n```
        3. Array of tool calls: [{"tool_call": {...}}, ...]

        Returns:
            List of tool call dictionaries, each containing:
            - tool_name: str
            - parameters: Dict[str, Any]
        """
        tool_calls = []

        try:
            from backend.app.shared.json_parser import parse_json_from_llm_response, parse_json_array_from_llm_response

            # First, try to parse the entire response as JSON
            parsed_json = parse_json_from_llm_response(assistant_message)

            if parsed_json:
                # Check if it's a tool call format: {"tool_call": {...}}
                if "tool_call" in parsed_json:
                    tool_call_data = parsed_json["tool_call"]
                    if isinstance(tool_call_data, dict) and "tool_name" in tool_call_data:
                        tool_calls.append({
                            "tool_name": tool_call_data["tool_name"],
                            "parameters": tool_call_data.get("parameters", tool_call_data.get("args", {}))
                        })
                        logger.info(f"Parsed 1 tool call from JSON: {tool_call_data.get('tool_name')}")
                        return tool_calls

                # Check if it's a direct tool call format: {"tool_name": "...", "parameters": {...}}
                if "tool_name" in parsed_json and isinstance(parsed_json.get("tool_name"), str):
                    # Skip if it looks like structured output
                    if not any(key in parsed_json for key in ['project_data', 'work_rhythm_data', 'onboarding_task', 'STRUCTURED_OUTPUT']):
                        tool_calls.append({
                            "tool_name": parsed_json["tool_name"],
                            "parameters": parsed_json.get("parameters", parsed_json.get("args", {}))
                        })
                        logger.info(f"Parsed 1 tool call (direct format): {parsed_json.get('tool_name')}")
                        return tool_calls

            # Try to parse as JSON array (multiple tool calls)
            parsed_array = parse_json_array_from_llm_response(assistant_message)

            if parsed_array and isinstance(parsed_array, list):
                for item in parsed_array:
                    if isinstance(item, dict):
                        # Check for tool_call format in array item
                        if "tool_call" in item:
                            tool_call_data = item["tool_call"]
                            if isinstance(tool_call_data, dict) and "tool_name" in tool_call_data:
                                tool_calls.append({
                                    "tool_name": tool_call_data["tool_name"],
                                    "parameters": tool_call_data.get("parameters", tool_call_data.get("args", {}))
                                })
                        # Check for direct tool call format in array item
                        elif "tool_name" in item and isinstance(item.get("tool_name"), str):
                            tool_calls.append({
                                "tool_name": item["tool_name"],
                                "parameters": item.get("parameters", item.get("args", {}))
                            })

                if tool_calls:
                    logger.info(f"Parsed {len(tool_calls)} tool call(s) from JSON array")
                    return tool_calls

            # Fallback: search for JSON blocks in markdown code blocks
            # This handles cases where JSON is embedded in prose text
            import re
            json_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
            matches = re.findall(json_block_pattern, assistant_message, re.DOTALL)

            for match in matches:
                parsed = parse_json_from_llm_response(match)
                if parsed:
                    # Check for tool_call format
                    if "tool_call" in parsed:
                        tool_call_data = parsed["tool_call"]
                        if isinstance(tool_call_data, dict) and "tool_name" in tool_call_data:
                            tool_calls.append({
                                "tool_name": tool_call_data["tool_name"],
                                "parameters": tool_call_data.get("parameters", tool_call_data.get("args", {}))
                            })
                    # Check for direct tool call format
                    elif "tool_name" in parsed and isinstance(parsed.get("tool_name"), str):
                        if not any(key in parsed for key in ['project_data', 'work_rhythm_data', 'onboarding_task', 'STRUCTURED_OUTPUT']):
                            tool_calls.append({
                                "tool_name": parsed["tool_name"],
                                "parameters": parsed.get("parameters", parsed.get("args", {}))
                            })

            if tool_calls:
                logger.info(f"Parsed {len(tool_calls)} tool call(s) from markdown code blocks")
                return tool_calls

        except Exception as e:
            logger.warning(f"Failed to parse tool calls from response: {e}", exc_info=True)

        return tool_calls

    def add_tool_call_results(self, tool_results: List[Dict[str, Any]]):
        """
        Add tool call results to conversation history.

        Args:
            tool_results: List of tool execution results, each containing:
                - tool_name: str
                - result: Any (tool execution result)
                - success: bool
                - error: Optional[str] (if execution failed)
        """
        if not tool_results:
            return

        results_text = "**工具調用結果：**\n\n"
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get("tool_name", "unknown")
            success = result.get("success", False)

            if success:
                result_value = result.get("result", "執行成功")
                results_text += f"{i}. **{tool_name}**: 執行成功\n"
                # Format result for LLM understanding
                if isinstance(result_value, (dict, list)):
                    result_str = json.dumps(result_value, ensure_ascii=False, indent=2)
                    results_text += f"   結果：\n```json\n{result_str}\n```\n\n"
                else:
                    result_str = str(result_value)[:500]  # Limit length
                    results_text += f"   結果：{result_str}\n\n"
            else:
                error_msg = result.get("error", "執行失敗")
                results_text += f"{i}. **{tool_name}**: 執行失敗\n"
                results_text += f"   錯誤：{error_msg}\n\n"

        results_text += "請根據以上工具調用結果繼續處理。\n"

        self.conversation_history.append({
            "role": "system",
            "content": results_text
        })

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ConversationManager state to dict for database storage"""
        return {
            "conversation_history": self.conversation_history,
            "current_step": self.current_step,
            "extracted_data": self.extracted_data,
            "workspace_id": self.workspace_id,
            "playbook_code": self.playbook.metadata.playbook_code if self.playbook else None,
            "locale": self.locale,
            "target_language": self.target_language,
            "variant": self.variant,
            "skip_steps": self.skip_steps,
            "custom_checklist": self.custom_checklist,
            "profile_id": self.profile.id if self.profile else "default-user",
            "project_id": getattr(self.project, 'id', None) if self.project else None,
        }

    @classmethod
    async def from_dict(
        cls,
        state: Dict[str, Any],
        store: Any,
        playbook_service: Any
    ) -> "PlaybookConversationManager":
        """Restore ConversationManager from serialized state"""
        playbook_code = state.get("playbook_code")
        locale = state.get("locale", "zh-TW")
        workspace_id = state.get("workspace_id")

        # Load playbook
        playbook = await playbook_service.get_playbook(
            playbook_code=playbook_code,
            locale=locale,
            workspace_id=workspace_id
        )

        if not playbook:
            raise ValueError(f"Playbook not found: {playbook_code}")

        # Load profile
        profile_id = state.get("profile_id", "default-user")
        profile = store.get_profile(profile_id)

        # Create manager
        manager = cls(
            playbook=playbook,
            profile=profile,
            locale=state.get("locale"),
            target_language=state.get("target_language"),
            workspace_id=workspace_id
        )

        # Restore state
        manager.conversation_history = state.get("conversation_history", [])
        manager.current_step = state.get("current_step", 0)
        manager.extracted_data = state.get("extracted_data", {})
        manager.variant = state.get("variant")
        manager.skip_steps = state.get("skip_steps", [])
        manager.custom_checklist = state.get("custom_checklist", [])

        return manager


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

    def _get_llm_manager(self, profile_id: str) -> LLMProviderManager:
        """Get LLM manager with profile-specific API keys"""
        from backend.app.shared.llm_provider_helper import create_llm_provider_manager

        # Get user config (for profile-specific overrides)
        config = self.config_store.get_or_create_config(profile_id)

        # Use user-configured keys if available, otherwise use unified function
        openai_key = config.agent_backend.openai_api_key
        anthropic_key = config.agent_backend.anthropic_api_key
        vertex_api_key = config.agent_backend.vertex_api_key
        vertex_project_id = config.agent_backend.vertex_project_id
        vertex_location = config.agent_backend.vertex_location

        # Use unified function with user config as overrides
        return create_llm_provider_manager(
            openai_key=openai_key,
            anthropic_key=anthropic_key,
            vertex_api_key=vertex_api_key,
            vertex_project_id=vertex_project_id,
            vertex_location=vertex_location
        )

    def _get_llm_provider(self, llm_manager: LLMProviderManager) -> LLMProvider:
        """
        Get LLM provider based on user's chat_model setting

        Args:
            llm_manager: LLMProviderManager instance

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If chat_model is not configured or specified provider is not available
        """
        from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings
        return get_llm_provider_from_settings(llm_manager)

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
                factory_cluster = "local_mcp"

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
            normalized_kwargs = kwargs.copy()
            if tool_fqn == "filesystem_write_file" and "path" in normalized_kwargs and "file_path" not in normalized_kwargs:
                normalized_kwargs["file_path"] = normalized_kwargs.pop("path")
                logger.debug(f"Normalized parameter 'path' -> 'file_path' for {tool_fqn}")

            result = await execute_tool(tool_fqn, **normalized_kwargs)

            tool_end_time = datetime.utcnow()
            duration_ms = int((tool_end_time - tool_start_time).total_seconds() * 1000)

            if execution_id and tool_call:
                try:
                    self.workflow_tracker.record_tool_call_complete(
                        tool_call_id=tool_call.id,
                        response={"result": str(result)[:1000]} if result else {"result": result}
                    )
                except Exception as e:
                    logger.warning(f"Failed to update ToolCall record: {e}")

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

            project = None
            if inputs and "project_id" in inputs:
                pass

            execution_id = str(uuid.uuid4())

            # Create Task record for execution session (required for ExecutionSession view model)
            if workspace_id:
                try:
                    from backend.app.services.stores.tasks_store import TasksStore
                    from backend.app.models.workspace import Task, TaskStatus

                    tasks_store = TasksStore(db_path=self.store.db_path)

                    # Build execution_context for ExecutionSession
                    execution_context = {
                        "playbook_code": playbook_code,
                        "playbook_name": playbook.metadata.name,
                        "trigger_source": inputs.get("trigger_source", "manual") if inputs else "manual",
                        "current_step_index": 0,
                        "total_steps": total_steps,  # Use actual step count from playbook.json
                        "origin_intent_id": inputs.get("origin_intent_id") if inputs else None,
                        "origin_intent_label": inputs.get("origin_intent_label") if inputs else None,
                        "intent_confidence": inputs.get("intent_confidence") if inputs else None,
                        "origin_suggestion_id": inputs.get("origin_suggestion_id") if inputs else None,
                    }

                    # Create Task record with execution_id
                    task = Task(
                        id=execution_id,
                        workspace_id=workspace_id,
                        message_id=inputs.get("message_id", str(uuid.uuid4())) if inputs else str(uuid.uuid4()),
                        execution_id=execution_id,
                        profile_id=profile_id,
                        pack_id=playbook_code,
                        task_type="playbook_execution",
                        status=TaskStatus.RUNNING,
                        execution_context=execution_context,
                        params=inputs or {},
                        created_at=datetime.utcnow(),
                        started_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )

                    tasks_store.create_task(task)
                    logger.info(f"PlaybookRunner: Created execution task {execution_id} for playbook {playbook_code}, workspace_id={workspace_id}")
                except Exception as task_error:
                    logger.warning(f"PlaybookRunner: Failed to create execution task for {playbook_code}: {task_error}", exc_info=True)
                    # Continue execution even if task creation fails

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

            # Preload and cache tools list for this workspace (with Redis cache support)
            if workspace_id:
                try:
                    from backend.app.services.tool_registry import ToolRegistryService
                    import os

                    # Get tool registry service
                    data_dir = os.getenv("DATA_DIR", "./data")
                    tool_registry = ToolRegistryService(data_dir=data_dir)

                    # Register external extensions (same as get_tool_registry does)
                    try:
                        from backend.app.extensions.console_kit import register_console_kit_tools
                        register_console_kit_tools(tool_registry)
                    except ImportError:
                        pass

                    try:
                        from backend.app.extensions.community import register_community_extensions
                        register_community_extensions(tool_registry)
                    except ImportError:
                        pass

                    # Get cached tools list (uses Redis cache if available)
                    profile_id_for_tools = profile_id if profile else None
                    if hasattr(tool_registry, 'get_tools_str_cached'):
                        cached_tools_str = tool_registry.get_tools_str_cached(
                            workspace_id=workspace_id,
                            profile_id=profile_id_for_tools,
                            enabled_only=True
                        )
                        conv_manager.cached_tools_str = cached_tools_str
                        logger.info(f"PlaybookRunner: Preloaded and cached tool list for workspace {workspace_id}")
                    else:
                        # Fallback: query tools directly
                        tools = tool_registry.get_tools(
                            workspace_id=workspace_id,
                            profile_id=profile_id_for_tools,
                            enabled_only=True
                        )
                        if tools:
                            # Format tools manually as fallback
                            tools_list = []
                            for tool in tools:
                                tool_id = getattr(tool, 'tool_id', None) or getattr(tool, 'id', 'unknown')
                                name = getattr(tool, 'display_name', None) or getattr(tool, 'name', None) or tool_id
                                desc = getattr(tool, 'description', None) or ''
                                category = getattr(tool, 'category', None) or 'general'
                                tools_list.append(f"- {tool_id}: {name} ({category}) - {desc[:100]}")
                            conv_manager.cached_tools_str = "\n".join(tools_list) if tools_list else None
                except Exception as e:
                    logger.warning(f"PlaybookRunner: Failed to preload tools list: {e}", exc_info=True)
                    # Continue execution even if tool loading fails

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
            provider = self._get_llm_provider(llm_manager)

            # Add a user message to start the conversation
            # Use a minimal message for LLM, but don't show "Starting Playbook execution" in UI
            from backend.app.shared.i18n_loader import load_i18n_string
            start_message = load_i18n_string(
                "playbook.start_execution",
                locale=conv_manager.locale,
                default="Starting Playbook execution."
            )
            # Add a minimal message to conversation for LLM context (required for execution)
            conv_manager.add_user_message("開始執行")  # Minimal message in Chinese

            messages = conv_manager.get_messages_for_llm()
            # Get model name from system settings
            from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model
            model_name = get_model_name_from_chat_model()
            logger.info(f"PlaybookRunner: Calling LLM for playbook {playbook_code}, model={model_name}, messages_count={len(messages)}")
            assistant_response = await provider.chat_completion(messages, model=model_name if model_name else None)
            logger.info(f"PlaybookRunner: LLM response received for playbook {playbook_code}, response_length={len(assistant_response) if assistant_response else 0}")

            conv_manager.add_assistant_message(assistant_response)

            # Record playbook step event for initial LLM response
            # This creates a step event for the first assistant response, similar to continue_playbook_execution
            try:
                project_id = inputs.get("project_id") if inputs else None
                playbook_code = playbook.metadata.playbook_code if playbook else None

                # Determine step information
                step_index = conv_manager.current_step  # This is 0 initially
                step_name = f"Step {step_index + 1}"  # Use 1-based naming for display
                step_type = "agent_action"
                agent_type = playbook.metadata.entry_agent_type if playbook.metadata else None

                # Generate log_summary from assistant response
                log_summary = f"Step {step_index + 1}: {assistant_response[:100]}..." if assistant_response else f"Step {step_index + 1}: Executing"

                # Record playbook step with full payload using WorkflowTracker
                # For initial step, mark as "completed" since LLM has responded
                # The step is considered complete when assistant provides initial response
                step_event = self.workflow_tracker.create_playbook_step_event(
                    execution_id=execution_id,
                    step_index=step_index + 1,  # Use 1-based index for display
                    step_name=step_name,
                    status="completed",  # Initial step is completed when LLM responds
                    step_type=step_type,
                    agent_type=agent_type,
                    used_tools=[],
                    description=assistant_response[:500] if assistant_response else None,
                    log_summary=log_summary,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    playbook_code=playbook_code
                )

                # Use total_steps already calculated from playbook.json (line 429-432)
                # If not available from JSON, calculate from SOP phases as fallback
                if total_steps == 1 and playbook_json is None:
                    # Only recalculate if we don't have JSON and defaulted to 1
                    calculated_steps = len(re.findall(r"### Phase \d:", playbook.sop_content))
                    if calculated_steps > 0:
                        total_steps = calculated_steps
                        logger.info(f"PlaybookRunner: Calculated total_steps={total_steps} from SOP phases for playbook {playbook_code}")
                    # Otherwise keep total_steps = 1

                # Update step event with completed_at timestamp and total_steps
                if step_event and isinstance(step_event.payload, dict):
                    step_event.payload["completed_at"] = datetime.utcnow().isoformat()
                    step_event.payload["total_steps"] = total_steps
                    self.store.update_event(
                        event_id=step_event.id,
                        payload=step_event.payload
                    )

                # Update Task's execution_context with the correct total_steps
                # This ensures the ExecutionSession view model has the correct total_steps
                if workspace_id and total_steps > 1:
                    try:
                        from backend.app.services.stores.tasks_store import TasksStore
                        tasks_store = TasksStore(db_path=self.store.db_path)
                        task = tasks_store.get_task(execution_id)
                        if task and task.execution_context:
                            if task.execution_context.get("total_steps", 1) != total_steps:
                                task.execution_context["total_steps"] = total_steps
                                tasks_store.update_task(execution_id, execution_context=task.execution_context)
                                logger.info(f"PlaybookRunner: Updated Task {execution_id} execution_context.total_steps to {total_steps}")
                    except Exception as e:
                        logger.warning(f"PlaybookRunner: Failed to update Task execution_context.total_steps: {e}", exc_info=True)

                # Increment current_step for next interaction
                conv_manager.current_step += 1

            except Exception as e:
                logger.warning(f"Failed to record playbook step event: {e}")

            # Save initial execution state to database
            try:
                await self._save_execution_state(execution_id, conv_manager)
            except Exception as e:
                logger.warning(f"Failed to save initial execution state: {e}", exc_info=True)

            return {
                "execution_id": execution_id,
                "playbook_code": playbook_code,
                "playbook_name": playbook.metadata.name,
                "message": assistant_response,
                "is_complete": False,
                "conversation_history": conv_manager.conversation_history
            }

        except Exception as e:
            logger.error(f"Failed to start playbook execution: {e}", exc_info=True)
            # Update task status to FAILED if task was created
            if workspace_id:
                try:
                    from backend.app.services.stores.tasks_store import TasksStore
                    from backend.app.models.workspace import TaskStatus
                    tasks_store = TasksStore(db_path=self.store.db_path)
                    task = tasks_store.get_task_by_execution_id(execution_id)
                    if task:
                        tasks_store.update_task_status(
                            task_id=task.id,
                            status=TaskStatus.FAILED,
                            error=str(e)[:1000]
                        )
                        logger.info(f"Updated execution task {execution_id} status to FAILED")
                except Exception as task_update_error:
                    logger.warning(f"Failed to update task status: {task_update_error}")
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
                conv_manager = await self._restore_execution_state(execution_id)

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
            llm_manager = self._get_llm_manager(profile_id)
            provider = self._get_llm_provider(llm_manager)

            messages = conv_manager.get_messages_for_llm()
            # Get model name from system settings
            from backend.app.shared.llm_provider_helper import get_model_name_from_chat_model
            model_name = get_model_name_from_chat_model()
            assistant_response = await provider.chat_completion(messages, model=model_name if model_name else None)

            conv_manager.add_assistant_message(assistant_response)

            # Parse and execute tool calls (with loop support for multiple iterations)
            max_tool_iterations = 5  # Prevent infinite loops
            tool_iteration = 0
            used_tools = []

            while tool_iteration < max_tool_iterations:
                # Parse tool calls from current assistant response
                tool_calls = conv_manager.parse_tool_calls_from_response(assistant_response)

                if not tool_calls:
                    break  # No tool calls found, exit loop

                logger.info(f"PlaybookRunner: Found {len(tool_calls)} tool call(s) in iteration {tool_iteration + 1}")

                # Execute all tool calls
                tool_results = []
                for tool_call in tool_calls:
                    tool_name = tool_call.get("tool_name")
                    parameters = tool_call.get("parameters", {})

                    if not tool_name:
                        logger.warning(f"Invalid tool call: missing tool_name")
                        continue

                    try:
                        # Execute tool using existing _run_tool method
                        logger.info(f"PlaybookRunner: Executing tool {tool_name} with parameters: {list(parameters.keys())}")
                        result = await self._run_tool(
                            tool_fqn=tool_name,
                            profile_id=profile_id,
                            workspace_id=conv_manager.workspace_id,
                            execution_id=execution_id,
                            step_id=None,  # Will be set when step event is created
                            **parameters
                        )

                        tool_results.append({
                            "tool_name": tool_name,
                            "result": result,
                            "success": True
                        })
                        used_tools.append(tool_name)

                        logger.info(f"PlaybookRunner: Tool {tool_name} executed successfully")

                    except Exception as e:
                        error_msg = str(e)[:500]
                        logger.error(f"PlaybookRunner: Tool {tool_name} execution failed: {e}", exc_info=True)
                        tool_results.append({
                            "tool_name": tool_name,
                            "result": None,
                            "success": False,
                            "error": error_msg
                        })

                # Add tool call results to conversation
                if tool_results:
                    conv_manager.add_tool_call_results(tool_results)

                # Continue conversation with tool results
                # Only continue if we have successful tool calls (to avoid infinite loops on errors)
                if any(r.get("success", False) for r in tool_results):
                    messages = conv_manager.get_messages_for_llm()
                    assistant_response = await provider.chat_completion(messages, model=model_name if model_name else None)
                    conv_manager.add_assistant_message(assistant_response)
                    tool_iteration += 1
                else:
                    # All tool calls failed, exit loop
                    logger.warning(f"PlaybookRunner: All tool calls failed, exiting tool execution loop")
                    break

            # Extract structured output and check if complete
            structured_output = conv_manager.extract_structured_output(assistant_response)
            is_complete = structured_output is not None

            # Increment current step index before creating step event
            # This ensures step_index is 1-based and sequential
            conv_manager.current_step += 1
            step_index = conv_manager.current_step

            # Calculate total steps by counting existing steps for this execution
            # This gives us the current total, which will increase as more steps are added
            # We add 1 because we're about to create a new step
            try:
                existing_events = self.store.get_events_by_workspace(
                    workspace_id=conv_manager.workspace_id,
                    limit=200
                )
                existing_steps = [
                    e for e in existing_events
                    if e.event_type == EventType.PLAYBOOK_STEP
                    and isinstance(e.payload, dict)
                    and e.payload.get('execution_id') == execution_id
                ]
                # Total steps is the maximum of:
                # 1. Current step_index (which is the step we're about to create)
                # 2. Number of existing steps + 1 (for the new step we're creating)
                # This ensures total_steps is always >= step_index
                total_steps = max(step_index, len(existing_steps) + 1)
            except Exception as e:
                logger.warning(f"Failed to calculate total_steps: {e}")
                total_steps = step_index  # Fallback to current step_index

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
                step_name = f"Step {step_index}"
                step_type = "agent_action"  # Default, could be determined from playbook SOP
                agent_type = None  # Could be determined from playbook or response

                # Get tools used in this step from ToolCall records
                # Note: We'll update this after creating the step event if we have a step_id
                # used_tools will be populated from tool execution loop above
                # (already defined in tool execution loop)

                # Generate log_summary
                log_summary = f"Step {step_index}: {assistant_response[:100]}..." if assistant_response else f"Step {step_index}: Executing"

                # For conversation mode, mark previous step as completed when creating a new step
                # Find and update the previous step (step_index - 1) to completed status
                if step_index > 1:
                    try:
                        previous_step_events = self.store.get_events_by_workspace(
                            workspace_id=workspace_id,
                            limit=100
                        )
                        previous_step_event = None
                        for event in previous_step_events:
                            if (event.event_type == EventType.PLAYBOOK_STEP and
                                isinstance(event.payload, dict) and
                                event.payload.get('execution_id') == execution_id and
                                event.payload.get('step_index') == step_index - 1):
                                previous_step_event = event
                                break

                        if previous_step_event and isinstance(previous_step_event.payload, dict):
                            # Update previous step status to completed
                            updated_payload = previous_step_event.payload.copy()
                            updated_payload['status'] = 'completed'
                            updated_payload['completed_at'] = datetime.utcnow().isoformat()
                            # Update the event in the store
                            self.store.update_event(
                                event_id=previous_step_event.id,
                                payload=updated_payload
                            )
                    except Exception as e:
                        logger.warning(f"Failed to update previous step status: {e}")

                # Record playbook step with full payload using WorkflowTracker
                # For conversation mode, mark as completed immediately since LLM has responded
                step_event = self.workflow_tracker.create_playbook_step_event(
                    execution_id=execution_id,
                    step_index=step_index,
                    step_name=step_name,
                    status="completed",  # Always mark as completed for conversation mode
                    step_type=step_type,
                    agent_type=agent_type,
                    used_tools=used_tools,
                    description=assistant_response[:500] if assistant_response else None,
                    log_summary=log_summary,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    playbook_code=playbook_code
                )

                # Update step event payload to include total_steps for frontend display
                if step_event and isinstance(step_event.payload, dict):
                    step_event.payload['total_steps'] = total_steps
                    self.store.update_event(
                        event_id=step_event.id,
                        payload=step_event.payload
                    )

                    # Update all previous steps' total_steps to match current total
                    # This ensures frontend displays correct "Step X/Y" for all steps
                    try:
                        all_step_events = [
                            e for e in existing_events
                            if e.event_type == EventType.PLAYBOOK_STEP
                            and isinstance(e.payload, dict)
                            and e.payload.get('execution_id') == execution_id
                            and e.id != step_event.id  # Exclude the current step
                        ]
                        for prev_event in all_step_events:
                            if isinstance(prev_event.payload, dict):
                                updated_payload = prev_event.payload.copy()
                                updated_payload['total_steps'] = total_steps
                                self.store.update_event(
                                    event_id=prev_event.id,
                                    payload=updated_payload
                                )
                    except Exception as e:
                        logger.warning(f"Failed to update previous steps' total_steps: {e}")

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

            # Update task status and cleanup if execution is complete
            if is_complete:
                try:
                    from backend.app.services.stores.tasks_store import TasksStore
                    from backend.app.models.workspace import TaskStatus
                    tasks_store = TasksStore(db_path=self.store.db_path)
                    task = tasks_store.get_task_by_execution_id(execution_id)
                    if task and task.status.value == 'running':
                        # Update task status to SUCCEEDED
                        tasks_store.update_task_status(
                            task_id=task.id,
                            status=TaskStatus.SUCCEEDED,
                            result={
                                "execution_id": execution_id,
                                "structured_output": structured_output,
                                "status": "completed"
                            },
                            completed_at=datetime.utcnow()
                        )
                        logger.info(f"Updated task {task.id} status to SUCCEEDED for completed execution {execution_id}")

                    # Cleanup execution from active_conversations
                    self.cleanup_execution(execution_id)
                    logger.info(f"Cleaned up execution {execution_id} from active_conversations")
                except Exception as e:
                    logger.warning(f"Failed to update task status or cleanup execution: {e}")

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
            await self._save_execution_state(execution_id, conv_manager)

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

    async def _save_execution_state(self, execution_id: str, conv_manager: PlaybookConversationManager):
        """Save execution state to database for persistence"""
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            tasks_store = TasksStore(db_path=self.store.db_path)
            task = tasks_store.get_task_by_execution_id(execution_id)

            if task:
                execution_context = task.execution_context or {}
                conversation_state_dict = conv_manager.to_dict()
                execution_context["conversation_state"] = conversation_state_dict
                tasks_store.update_task(task.id, execution_context=execution_context)
                logger.info(f"Saved execution state for {execution_id} to database (conversation_length={len(conversation_state_dict.get('conversation_history', []))})")
            else:
                logger.warning(f"Cannot save execution state: Task not found for execution_id {execution_id}")
        except Exception as e:
            logger.error(f"Failed to save execution state for {execution_id}: {e}", exc_info=True)

    async def _restore_execution_state(self, execution_id: str) -> Optional[PlaybookConversationManager]:
        """Restore execution state from database"""
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.models.workspace import TaskStatus
            tasks_store = TasksStore(db_path=self.store.db_path)
            task = tasks_store.get_task_by_execution_id(execution_id)

            if not task:
                logger.debug(f"Task not found for execution_id: {execution_id}")
                return None

            # Only restore if task is still running
            if task.status != TaskStatus.RUNNING:
                logger.debug(f"Task {task.id} is not running (status: {task.status}), cannot restore execution state")
                return None

            execution_context = task.execution_context or {}
            conversation_state = execution_context.get("conversation_state")

            if not conversation_state:
                logger.info(f"No conversation_state found in execution_context for {execution_id}. Available keys: {list(execution_context.keys())}")
                return None

            # Restore ConversationManager from saved state
            logger.info(f"Attempting to restore ConversationManager for execution {execution_id} from database")
            conv_manager = await PlaybookConversationManager.from_dict(
                conversation_state,
                self.store,
                self.playbook_service
            )

            logger.info(f"Successfully restored ConversationManager for execution {execution_id} (conversation_length={len(conv_manager.conversation_history)})")

            # Reload tools list from cache if workspace_id is available
            if conv_manager.workspace_id:
                try:
                    from backend.app.services.tool_registry import ToolRegistryService
                    import os

                    data_dir = os.getenv("DATA_DIR", "./data")
                    tool_registry = ToolRegistryService(data_dir=data_dir)

                    profile_id_for_tools = conv_manager.profile.id if conv_manager.profile else None
                    if hasattr(tool_registry, 'get_tools_str_cached'):
                        cached_tools_str = tool_registry.get_tools_str_cached(
                            workspace_id=conv_manager.workspace_id,
                            profile_id=profile_id_for_tools,
                            enabled_only=True
                        )
                        conv_manager.cached_tools_str = cached_tools_str
                        logger.info(f"PlaybookRunner: Reloaded cached tool list for workspace {conv_manager.workspace_id}")
                except Exception as e:
                    logger.warning(f"PlaybookRunner: Failed to reload tools list during restore: {e}", exc_info=True)

            return conv_manager

        except Exception as e:
            logger.error(f"Failed to restore execution state for {execution_id}: {e}", exc_info=True)
            return None

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
