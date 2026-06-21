"""
Playbook Conversation Manager
Manages multi-turn conversations for Playbook execution
"""

import json
import logging
from typing import Dict, List, Optional, Any

from backend.app.models.playbook import Playbook
from backend.app.models.mindscape import MindscapeProfile
from .conversation_manager_core import (
    build_base_prompt_parts,
    build_tool_access_sections,
    build_tool_result_message,
    normalize_tool_call_json,
    normalize_tool_name,
    parse_python_style_tool_call,
    parse_tool_calls_from_response,
)

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
        workspace_id: Optional[str] = None,
        auto_execute: bool = False,
    ):
        self.playbook = playbook
        self.profile = profile
        self.project = project
        self.workspace_id = workspace_id
        self.project_id = getattr(project, "id", None) if project else None
        self.auto_execute = (
            auto_execute  # If True, skip confirmations and execute tools directly
        )
        self.store = None  # Will be set if needed for tool slot collection
        if target_language:
            self.target_language = target_language
            self.locale = target_language
        else:
            from backend.app.shared.i18n_loader import get_locale_from_context

            # Note: workspace fetching moved to async context, using None here
            # Locale will be determined from profile/project or default
            self.locale = locale or get_locale_from_context(
                profile=profile, workspace=None, project=project
            )
            self.target_language = self.locale
        self.conversation_history: List[Dict[str, str]] = []
        self.extracted_data: Dict[str, Any] = {}
        self.current_step = 0
        self.variant: Optional[Dict[str, Any]] = None
        self.skip_steps: List[int] = []
        self.custom_checklist: List[str] = []
        self.cached_tools_str: Optional[str] = None  # Cache formatted tools string

    async def build_system_prompt(self) -> str:
        """Build system prompt for Playbook execution"""
        prompt_parts = build_base_prompt_parts(
            playbook_name=self.playbook.metadata.name,
            sop_content=self.playbook.sop_content,
            user_context=(
                self.profile.self_description
                if self.profile and self.profile.self_description
                else None
            ),
            target_language=self.target_language,
            variant=self.variant,
            skip_steps=self.skip_steps,
            custom_checklist=self.custom_checklist,
            auto_execute=self.auto_execute,
        )

        # Collect tool slot information (if available)
        slot_info_str = ""
        try:
            workspace_id = self.workspace_id
            project_id = self.project_id
            playbook_code = (
                self.playbook.metadata.playbook_code if self.playbook else None
            )

            if workspace_id and playbook_code:
                from backend.app.services.playbook.tool_slot_info_collector import (
                    get_tool_slot_info_collector,
                )

                # Initialize store if not set
                if not self.store:
                    from backend.app.services.mindscape_store import MindscapeStore

                    self.store = MindscapeStore()

                collector = get_tool_slot_info_collector(store=self.store)

                # Get user message from conversation history for intent filtering
                user_message = None
                if self.conversation_history:
                    # Get last user message
                    for msg in reversed(self.conversation_history):
                        if msg.get("role") == "user":
                            user_message = msg.get("content", "")
                            break

                # Collect slots with intent filtering (collect_slot_info already resolves tool IDs)
                slot_info_map = await collector.collect_slot_info(
                    playbook_code=playbook_code,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    user_message=user_message,
                    conversation_history=self.conversation_history,
                    enable_intent_filtering=True,  # Enable LLM-based filtering
                )

                if slot_info_map:
                    slot_info_str = collector.format_for_prompt(
                        slot_info_map=slot_info_map,
                        include_policy=True,
                        include_mapped_tool=True,
                        include_relevance_score=True,  # Show relevance scores
                    )
                    logger.debug(
                        f"Collected {len(slot_info_map)} tool slots for prompt injection"
                    )
        except Exception as e:
            logger.warning(
                f"Failed to collect tool slot information: {e}", exc_info=True
            )

        if self.cached_tools_str:
            logger.debug(
                f"PlaybookConversationManager: Using cached tools string (length={len(self.cached_tools_str)})"
            )
        elif not slot_info_str:
            logger.warning(
                f"PlaybookConversationManager: No cached tools string available for playbook {self.playbook.metadata.playbook_code if self.playbook else 'unknown'}"
            )

        prompt_parts.extend(
            build_tool_access_sections(
                slot_info_str=slot_info_str,
                cached_tools_str=self.cached_tools_str,
            )
        )

        system_prompt = "\n".join(prompt_parts)

        # Log system prompt for debugging (first 2000 chars to avoid log spam)
        logger.info(
            f"PlaybookConversationManager: Built system prompt (length={len(system_prompt)}, "
            f"has_slot_info={bool(slot_info_str)}, has_cached_tools={bool(self.cached_tools_str)})"
        )
        if len(system_prompt) > 0:
            logger.info(
                f"PlaybookConversationManager: System prompt preview (first 2000 chars):\n{system_prompt[:2000]}"
            )
            # Also log AVAILABLE_TOOLS section if present
            if "[AVAILABLE_TOOLS]" in system_prompt:
                tools_start = system_prompt.find("[AVAILABLE_TOOLS]")
                tools_end = system_prompt.find("[/AVAILABLE_TOOLS]", tools_start)
                if tools_end > tools_start:
                    tools_section = system_prompt[
                        tools_start : tools_end + len("[/AVAILABLE_TOOLS]")
                    ]
                    logger.info(
                        f"PlaybookConversationManager: AVAILABLE_TOOLS section (length={len(tools_section)}):\n{tools_section[:1500]}"
                    )

        return system_prompt

    def add_user_message(self, message: str):
        """Add user message to conversation history"""
        self.conversation_history.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        """Add assistant message to conversation history"""
        self.conversation_history.append({"role": "assistant", "content": message})

    async def get_messages_for_llm(self) -> List[Dict[str, str]]:
        """Get formatted messages for LLM API"""
        # Ensure store is initialized if not set
        if not self.store:
            from backend.app.services.mindscape_store import MindscapeStore

            self.store = MindscapeStore()

        system_prompt = await self.build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history)
        return messages

    def extract_structured_output(
        self, assistant_message: str
    ) -> Optional[Dict[str, Any]]:
        """Extract structured JSON output from assistant message"""
        try:
            # Look for JSON in the message
            # Pattern 1: STRUCTURED_OUTPUT: {...}
            pattern1 = r"STRUCTURED_OUTPUT:\s*(\{.*\})"
            match = re.search(pattern1, assistant_message, re.DOTALL)

            if match:
                json_str = match.group(1)
                return json.loads(json_str)

            # Pattern 2: Any JSON object in the message
            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            matches = re.findall(json_pattern, assistant_message, re.DOTALL)

            if matches:
                # Try to parse the last (most complete) JSON
                for json_str in reversed(matches):
                    try:
                        data = json.loads(json_str)
                        # Check if it looks like playbook output
                        if any(
                            key in data
                            for key in [
                                "project_data",
                                "work_rhythm_data",
                                "onboarding_task",
                            ]
                        ):
                            return data
                    except:
                        continue

            return None

        except Exception as e:
            logger.error(f"Failed to extract structured output: {e}")
            return None

    def _normalize_tool_call_json(
        self, parsed_json: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        return normalize_tool_call_json(parsed_json)

    def _normalize_tool_name(self, tool_name: str) -> str:
        return normalize_tool_name(tool_name)

    def _get_tool_schema_for_error(
        self, tool_name: str, error_msg: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get tool schema definition to help LLM correct tool calls.

        Only attempts to fetch schema if error suggests parameter mismatch.
        """
        # Only fetch schema for parameter errors or tool not found errors
        if not (
            "parameter" in error_msg.lower()
            or "unexpected keyword" in error_msg.lower()
            or "not found" in error_msg.lower()
        ):
            return None

        try:
            from backend.app.services.tools.registry import (
                get_mindscape_tool,
                register_filesystem_tools,
            )
            from backend.app.shared.tool_executor import _tool_executor

            # Ensure filesystem tools are registered before fetching schema
            _tool_executor._ensure_filesystem_tools_registered()

            # Try normalized name first
            normalized_name = self._normalize_tool_name(tool_name)
            tool = get_mindscape_tool(normalized_name)

            # If not found, try original name
            if not tool:
                tool = get_mindscape_tool(tool_name)

            if tool:
                tool_dict = tool.to_dict()
                return {
                    "name": tool_dict.get("name", normalized_name),
                    "description": tool_dict.get("description", ""),
                    "input_schema": tool_dict.get("input_schema", {}),
                }
        except Exception as e:
            logger.debug(f"Failed to get tool schema for {tool_name}: {e}")

        return None

    def _parse_python_style_tool_call(self, text: str) -> List[Dict[str, Any]]:
        return parse_python_style_tool_call(text)

    def parse_tool_calls_from_response(
        self, assistant_message: str
    ) -> List[Dict[str, Any]]:
        return parse_tool_calls_from_response(assistant_message)

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

        tool_schemas: Dict[str, Optional[Dict[str, Any]]] = {}
        for result in tool_results:
            tool_name = result.get("tool_name", "unknown")
            success = result.get("success", False)
            if success:
                continue

            error_msg = result.get("error", "Execution failed")
            logger.debug(
                f"Attempting to get tool schema for {tool_name} with error: {error_msg[:100]}"
            )
            tool_schema = self._get_tool_schema_for_error(tool_name, error_msg)
            logger.debug(f"Tool schema result for {tool_name}: {tool_schema is not None}")
            if tool_schema:
                logger.info(f"Found tool schema for {tool_name}, adding to error message")
            else:
                logger.debug(f"Could not get tool schema for {tool_name}")
            tool_schemas[tool_name] = tool_schema

        results_text = build_tool_result_message(
            tool_results=tool_results,
            tool_schemas=tool_schemas,
            auto_execute=self.auto_execute,
        )

        self.conversation_history.append({"role": "system", "content": results_text})

    def to_dict(self) -> Dict[str, Any]:
        """Serialize ConversationManager state to dict for database storage"""
        return {
            "conversation_history": self.conversation_history,
            "current_step": self.current_step,
            "extracted_data": self.extracted_data,
            "workspace_id": self.workspace_id,
            "playbook_code": (
                self.playbook.metadata.playbook_code if self.playbook else None
            ),
            "locale": self.locale,
            "target_language": self.target_language,
            "variant": self.variant,
            "skip_steps": self.skip_steps,
            "custom_checklist": self.custom_checklist,
            "profile_id": self.profile.id if self.profile else "default-user",
            "project_id": getattr(self.project, "id", None) if self.project else None,
        }

    @classmethod
    async def from_dict(
        cls, state: Dict[str, Any], store: Any, playbook_service: Any
    ) -> "PlaybookConversationManager":
        """Restore ConversationManager from serialized state"""
        from backend.app.shared.i18n_loader import get_locale_from_context

        playbook_code = state.get("playbook_code")
        locale = state.get("locale", "zh-TW")
        workspace_id = state.get("workspace_id")

        # Load playbook
        playbook = await playbook_service.get_playbook(
            playbook_code=playbook_code, locale=locale, workspace_id=workspace_id
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
            workspace_id=workspace_id,
        )

        # Restore state
        manager.conversation_history = state.get("conversation_history", [])
        manager.current_step = state.get("current_step", 0)
        manager.extracted_data = state.get("extracted_data", {})
        manager.variant = state.get("variant")
        manager.skip_steps = state.get("skip_steps", [])
        manager.custom_checklist = state.get("custom_checklist", [])

        return manager
