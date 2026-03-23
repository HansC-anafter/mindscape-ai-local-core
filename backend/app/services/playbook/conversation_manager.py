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
        prompt_parts = []

        # Playbook role and instructions
        prompt_parts.append(f"[PLAYBOOK: {self.playbook.metadata.name}]")
        prompt_parts.append(self.playbook.sop_content)
        prompt_parts.append("[/PLAYBOOK]")

        # Add variant customizations if present
        if self.variant:
            if self.skip_steps:
                prompt_parts.append(f"\n[SKIP_STEPS]")
                prompt_parts.append(
                    f"Skip the following steps: {', '.join(map(str, self.skip_steps))}"
                )
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
        prompt_parts.append(
            f"Use terminology appropriate for {self.target_language} locale."
        )
        prompt_parts.append(
            f"Maintain a conversational, friendly tone in {self.target_language}."
        )
        prompt_parts.append("[/LANGUAGE_INSTRUCTION]")

        # Execution instructions
        prompt_parts.append("\n[EXECUTION_INSTRUCTIONS]")
        prompt_parts.append("Follow the SOP steps exactly as described.")
        prompt_parts.append(
            "At the end, output structured JSON with the key 'STRUCTURED_OUTPUT'."
        )

        # Auto-execute mode: skip confirmations and execute tools directly
        if self.auto_execute:
            prompt_parts.append("\n⚡ **AUTO-EXECUTE MODE ENABLED**:")
            prompt_parts.append(
                "- Do NOT ask for user confirmation before executing tools"
            )
            prompt_parts.append("- Execute all tool calls immediately and directly")
            prompt_parts.append("- Skip any 'needs_review' or 'confirmation' steps")
            prompt_parts.append(
                "- Complete all SOP phases in a single response if possible"
            )
            prompt_parts.append(
                "- Generate all required output files without waiting for user input"
            )

        prompt_parts.append("[/EXECUTION_INSTRUCTIONS]")

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

        # Tool call format instructions (enhanced with slot support)
        tool_format_instructions = [
            "\n## Tool Call Format (Must Follow Strictly)",
            "\nWhen you need to use tools, you **must** use one of the following JSON formats:",
        ]

        # Add slot format if slots are available
        if slot_info_str:
            tool_format_instructions.extend(
                [
                    "\n### Format A (Use Tool Slot, Recommended):",
                    "```json",
                    "{",
                    '  "tool_call": {',
                    '    "tool_slot": "cms.footer.apply_style",',
                    '    "parameters": {',
                    '      "footer_content": "..."',
                    "    }",
                    "  }",
                    "}",
                    "```",
                    "\nUsing tool_slot allows more flexible tool binding, recommend using this format first.",
                ]
            )

        tool_format_instructions.extend(
            [
                "\n### Format B (Use Concrete Tool ID, Backward Compatible):",
                "```json",
                "{",
                '  "tool_call": {',
                '    "tool_name": "filesystem_list_files",',
                '    "parameters": {',
                '      "path": "./",',
                '      "recursive": true',
                "    }",
                "  }",
                "}",
                "```",
                "\n### Format C (Simplified Format):",
                "```json",
                "{",
                '  "tool_name": "filesystem_write_file",',
                '  "parameters": {',
                '    "file_path": "pages/index.tsx",',
                '    "content": "// file content here"',
                "  }",
                "}",
                "```",
                "\n### Invalid Formats (System Cannot Parse):",
                "- Field names like `tool_code`, `tool_command`, etc.",
                "- Python syntax like `tool_name(arg=value)`",
                "- Function call syntax like `print(filesystem_list_files(...))`",
                "\nAfter tool calls, the system will automatically execute and return results to you.",
            ]
        )

        # Inject tool slot information (if available)
        if slot_info_str:
            prompt_parts.append(slot_info_str)
            prompt_parts.append("\n**How to Use Tools:**")
            prompt_parts.extend(tool_format_instructions)

        # Inject traditional tool list (as fallback/backward compatibility)
        if self.cached_tools_str:
            logger.debug(
                f"PlaybookConversationManager: Using cached tools string (length={len(self.cached_tools_str)})"
            )
            if not slot_info_str:  # Only show if no slot info
                prompt_parts.append("\n[AVAILABLE_TOOLS]")
                prompt_parts.append(self.cached_tools_str)
                prompt_parts.append("\n\n**How to Use Tools:**")
                prompt_parts.extend(tool_format_instructions)
                prompt_parts.append("[/AVAILABLE_TOOLS]")
            else:
                # Show as fallback option
                prompt_parts.append("\n[AVAILABLE_TOOLS]")
                prompt_parts.append(
                    "If no suitable slot is available, you can also directly use the following tools:"
                )
                prompt_parts.append(self.cached_tools_str)
                prompt_parts.append("[/AVAILABLE_TOOLS]")
        else:
            if not slot_info_str:  # Only show format instructions if no slot info
                logger.warning(
                    f"PlaybookConversationManager: No cached tools string available for playbook {self.playbook.metadata.playbook_code if self.playbook else 'unknown'}"
                )
                prompt_parts.append("\n[AVAILABLE_TOOLS]")
                prompt_parts.extend(tool_format_instructions)
                prompt_parts.append("[/AVAILABLE_TOOLS]")

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

        results_text = "**Tool Call Results:**\n\n"
        for i, result in enumerate(tool_results, 1):
            tool_name = result.get("tool_name", "unknown")
            success = result.get("success", False)

            if success:
                result_value = result.get("result", "Execution successful")
                results_text += f"{i}. **{tool_name}**: Execution successful\n"
                # Format result for LLM understanding
                if isinstance(result_value, (dict, list)):
                    result_str = json.dumps(result_value, ensure_ascii=False, indent=2)
                    results_text += f"   Result:\n```json\n{result_str}\n```\n\n"
                else:
                    result_str = str(result_value)[:500]  # Limit length
                    results_text += f"   Result: {result_str}\n\n"
            else:
                error_msg = result.get("error", "Execution failed")
                results_text += f"{i}. **{tool_name}**: Execution failed\n"
                results_text += f"   Error: {error_msg}\n\n"

                # Try to get tool definition to help LLM correct the call
                logger.debug(
                    f"Attempting to get tool schema for {tool_name} with error: {error_msg[:100]}"
                )
                tool_schema = self._get_tool_schema_for_error(tool_name, error_msg)
                logger.debug(
                    f"Tool schema result for {tool_name}: {tool_schema is not None}"
                )
                if tool_schema:
                    logger.info(
                        f"Found tool schema for {tool_name}, adding to error message"
                    )
                    results_text += f"   **Tool Definition:**\n"
                    results_text += (
                        f"   - Tool Name: `{tool_schema.get('name', tool_name)}`\n"
                    )
                    results_text += (
                        f"   - Description: {tool_schema.get('description', 'N/A')}\n"
                    )
                    if tool_schema.get("input_schema"):
                        params = tool_schema["input_schema"].get("properties", {})
                        if params:
                            results_text += f"   - **Correct Parameters:**\n"
                            for param_name, param_def in params.items():
                                param_type = param_def.get("type", "unknown")
                                param_desc = param_def.get("description", "")
                                required = param_name in tool_schema[
                                    "input_schema"
                                ].get("required", [])
                                req_marker = " (required)" if required else ""
                                results_text += f"     - `{param_name}` ({param_type}){req_marker}: {param_desc}\n"
                    results_text += "\n"
                else:
                    logger.debug(f"Could not get tool schema for {tool_name}")

        # In auto_execute mode, add stronger prompt to continue
        if self.auto_execute:
            results_text += "\n**⚡ AUTO-EXECUTE MODE: You MUST continue executing the next steps in the SOP immediately.**\n"
            results_text += "- Review the tool results above\n"
            results_text += "- Immediately call the next required tool from the SOP\n"
            results_text += "- Do NOT stop or ask for confirmation\n"
            results_text += "- Continue until all SOP phases are complete\n"
        else:
            results_text += "Please continue processing based on the above tool call results. If tool calls failed, please retry with the correct parameters from the tool definition.\n"

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
