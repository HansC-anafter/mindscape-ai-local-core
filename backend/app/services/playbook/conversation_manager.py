"""
Playbook Conversation Manager
Manages multi-turn conversations for Playbook execution
"""

import json
import re
import logging
from typing import Dict, List, Optional, Any

from backend.app.models.playbook import Playbook
from backend.app.models.mindscape import MindscapeProfile

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
            from backend.app.shared.i18n_loader import get_locale_from_context
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
        # Tool call format instructions (shared between both branches)
        tool_format_instructions = [
            "\n## ⚠️ 工具調用格式（必須嚴格遵守）",
            "\n當你需要使用工具時，**必須**使用以下 JSON 格式之一：",
            "\n### 格式 A（標準格式）:",
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
            "\n### 格式 B（簡化格式）:",
            "```json",
            "{",
            '  "tool_name": "filesystem_write_file",',
            '  "parameters": {',
            '    "file_path": "pages/index.tsx",',
            '    "content": "// file content here"',
            "  }",
            "}",
            "```",
            "\n### ❌ 禁止的格式（系統無法解析）：",
            "- `tool_code`、`tool_command` 等其他欄位名 ❌",
            "- Python 語法如 `tool_name(arg=value)` ❌",
            "- 函數調用語法如 `print(filesystem_list_files(...))` ❌",
            "\n工具調用後，系統會自動執行並將結果返回給你。"
        ]

        if self.cached_tools_str:
            logger.debug(f"PlaybookConversationManager: Using cached tools string (length={len(self.cached_tools_str)})")
            prompt_parts.append("\n[AVAILABLE_TOOLS]")
            prompt_parts.append(self.cached_tools_str)
            prompt_parts.append("\n\n**如何使用工具：**")
            prompt_parts.extend(tool_format_instructions)
            prompt_parts.append("[/AVAILABLE_TOOLS]")
        else:
            logger.warning(f"PlaybookConversationManager: No cached tools string available for playbook {self.playbook.metadata.playbook_code if self.playbook else 'unknown'}")
            prompt_parts.extend(tool_format_instructions)
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

    def _normalize_tool_call_json(self, parsed_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize various incorrect tool call formats to standard format.

        Handles:
        - tool_call: standard format
        - tool_code: LLM sometimes uses this instead
        - tool_command: another variant
        - tool_calls: array format (returns first item)
        """
        # Standard format
        if "tool_call" in parsed_json:
            return parsed_json["tool_call"]

        # Common mistakes: tool_code, tool_command
        for alt_key in ["tool_code", "tool_command", "function_call", "call"]:
            if alt_key in parsed_json:
                data = parsed_json[alt_key]
                if isinstance(data, dict) and "tool_name" in data:
                    logger.info(f"Normalized '{alt_key}' to 'tool_call'")
                    return data

        # tool_calls array format (LLM sometimes outputs this)
        if "tool_calls" in parsed_json:
            calls = parsed_json["tool_calls"]
            if isinstance(calls, list) and len(calls) > 0:
                first = calls[0]
                if isinstance(first, dict):
                    if "tool_name" in first:
                        logger.info("Normalized 'tool_calls' array to single tool_call")
                        return first
                    elif "tool_call" in first:
                        return first["tool_call"]

        return None

    def _parse_python_style_tool_call(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse Python-style function calls like:
        - filesystem_read_file('path')
        - print(filesystem_list_files(path='.'))
        - fs.read_file('path') -> maps to filesystem_read_file
        """
        import re
        tool_calls = []

        # Tool name mappings (aliases -> canonical name)
        tool_aliases = {
            "filesystem_list_files": "filesystem_list_files",
            "filesystem_read_file": "filesystem_read_file",
            "filesystem_write_file": "filesystem_write_file",
            "filesystem_search": "filesystem_search",
            # Common aliases LLM might use
            "fs.list_files": "filesystem_list_files",
            "fs.read_file": "filesystem_read_file",
            "fs.write_file": "filesystem_write_file",
            "fs.search": "filesystem_search",
            "list_files": "filesystem_list_files",
            "read_file": "filesystem_read_file",
            "write_file": "filesystem_write_file",
        }

        for alias, canonical_name in tool_aliases.items():
            # Escape dots for regex
            escaped_alias = alias.replace(".", r"\.")
            # Match: alias('arg') or alias(key='value', key2='value2')
            pattern = rf"{escaped_alias}\s*\(([^)]*)\)"
            matches = re.findall(pattern, text)

            for args_str in matches:
                parameters = {}
                # Parse simple string args: 'value' or "value"
                simple_match = re.match(r"^\s*['\"]([^'\"]+)['\"]\s*$", args_str)
                if simple_match:
                    # Single positional arg - assume it's 'path' for filesystem tools
                    parameters["path"] = simple_match.group(1)
                else:
                    # Parse keyword args: key='value' or key="value"
                    kv_pattern = r"(\w+)\s*=\s*['\"]([^'\"]+)['\"]"
                    kv_matches = re.findall(kv_pattern, args_str)
                    for key, value in kv_matches:
                        parameters[key] = value

                    # Also handle: key=True/False
                    bool_pattern = r"(\w+)\s*=\s*(True|False)"
                    bool_matches = re.findall(bool_pattern, args_str)
                    for key, value in bool_matches:
                        parameters[key] = value == "True"

                if parameters:
                    tool_calls.append({
                        "tool_name": canonical_name,
                        "parameters": parameters
                    })
                    logger.info(f"Parsed Python-style tool call: {alias} -> {canonical_name}({parameters})")

        return tool_calls

    def parse_tool_calls_from_response(self, assistant_message: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response.

        Uses shared JSON parser utility to extract tool calls from various formats:
        1. JSON object with tool_call field: {"tool_call": {"tool_name": "...", "parameters": {...}}}
        2. JSON in markdown code blocks: ```json\n{"tool_call": {...}}\n```
        3. Array of tool calls: [{"tool_call": {...}}, ...]
        4. (Fallback) Incorrect formats: tool_code, tool_command, tool_calls
        5. (Fallback) Python-style calls: filesystem_read_file('path')

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
                # Try to normalize various formats
                normalized = self._normalize_tool_call_json(parsed_json)
                if normalized and isinstance(normalized, dict) and "tool_name" in normalized:
                    tool_calls.append({
                        "tool_name": normalized["tool_name"],
                        "parameters": normalized.get("parameters", normalized.get("args", {}))
                    })
                    logger.info(f"Parsed 1 tool call (normalized): {normalized.get('tool_name')}")
                    return tool_calls

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
                    # Try normalized format first
                    normalized = self._normalize_tool_call_json(parsed)
                    if normalized and isinstance(normalized, dict) and "tool_name" in normalized:
                        tool_calls.append({
                            "tool_name": normalized["tool_name"],
                            "parameters": normalized.get("parameters", normalized.get("args", {}))
                        })
                        continue

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

            # Final fallback: try to parse Python-style function calls
            # e.g., filesystem_read_file('path') or print(filesystem_list_files(path='.'))
            python_calls = self._parse_python_style_tool_call(assistant_message)
            if python_calls:
                logger.info(f"Parsed {len(python_calls)} tool call(s) from Python-style syntax (fallback)")
                return python_calls

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
        from backend.app.shared.i18n_loader import get_locale_from_context

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

