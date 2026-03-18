"""
Tool Execution Loop
Handles multi-step tool calls, LLM retry looping, and format correction.
"""
import logging
import re
from typing import Dict, List, Optional, Any, Callable, Awaitable, Tuple

from backend.app.services.stores.workspace_runtime_profile_store import WorkspaceRuntimeProfileStore

logger = logging.getLogger(__name__)

class ToolExecutionLoop:
    TOOL_INTENT_PATTERNS = [
        (r"tool_code", "Used 'tool_code' instead of 'tool_call'"),
        (r"tool_command", "Used 'tool_command' instead of 'tool_call'"),
        (r"function_call", "Used 'function_call' instead of 'tool_call'"),
        (r"fs\.read_file", "Used 'fs.read_file' instead of 'filesystem_read_file'"),
        (r"fs\.write_file", "Used 'fs.write_file' instead of 'filesystem_write_file'"),
        (r"fs\.list_files", "Used 'fs.list_files' instead of 'filesystem_list_files'"),
        (r"print\s*\(\s*filesystem_", "Used Python print() syntax to call tools"),
        (r"await\s+filesystem_", "Used async/await syntax to call tools"),
    ]

    def __init__(self, execute_tool_fn: Callable[..., Awaitable[Any]], execution_context: Dict[str, Any]):
        self.execute_tool_fn = execute_tool_fn
        self.execution_context = execution_context

    def _find_related_tools(self, attempted_name: str, workspace_id: Optional[str] = None) -> List[str]:
        try:
            from backend.app.services.tools.registry import get_all_mindscape_tools
            from backend.app.services.tool_list_service import get_tool_list_service

            attempted_lower = attempted_name.lower()
            keywords = [
                word
                for word in attempted_lower.replace(".", "_").replace("-", "_").split("_")
                if len(word) > 2
            ]

            if not keywords:
                return []

            all_tools = []
            try:
                mindscape_tools = get_all_mindscape_tools()
                all_tools.extend([tool.metadata.name for tool in mindscape_tools.values() if hasattr(tool, "metadata")])
            except Exception:
                pass

            if workspace_id:
                try:
                    tool_list_service = get_tool_list_service()
                    tool_infos = tool_list_service.get_tools(workspace_id=workspace_id, enabled_only=True)
                    all_tools.extend([tool.tool_id for tool in tool_infos])
                except Exception:
                    pass

            all_tools = list(set(all_tools))
            related = []
            for tool_name in all_tools:
                tool_lower = tool_name.lower()
                if any(keyword in tool_lower for keyword in keywords):
                    related.append(tool_name)

            related.sort(key=lambda t: sum(1 for k in keywords if k in t.lower()), reverse=True)
            return related[:10]

        except Exception as e:
            logger.debug(f"Failed to find related tools: {e}")
            return []

    def _suggest_tool_names(self, attempted_name: str, workspace_id: Optional[str] = None) -> List[str]:
        suggestions = []
        try:
            from backend.app.services.tools.registry import get_all_mindscape_tools
            from backend.app.services.tool_list_service import get_tool_list_service

            all_tools = []
            try:
                mindscape_tools = get_all_mindscape_tools()
                all_tools.extend([tool.metadata.name for tool in mindscape_tools if hasattr(tool, "metadata")])
            except Exception:
                pass

            if workspace_id:
                try:
                    tool_list_service = get_tool_list_service()
                    tool_infos = tool_list_service.get_tools(workspace_id=workspace_id, enabled_only=True)
                    all_tools.extend([tool.tool_id for tool in tool_infos])
                except Exception:
                    pass

            all_tools = list(set(all_tools))
            attempted_lower = attempted_name.lower()
            attempted_parts = set(attempted_lower.replace(".", "_").replace("-", "_").split("_"))

            for tool_name in all_tools:
                tool_lower = tool_name.lower()
                tool_parts = set(tool_lower.replace(".", "_").replace("-", "_").split("_"))
                common_parts = attempted_parts.intersection(tool_parts)
                if common_parts:
                    score = len(common_parts) / max(len(attempted_parts), len(tool_parts))
                    if score > 0.3:
                        suggestions.append((tool_name, score))

            suggestions.sort(key=lambda x: x[1], reverse=True)
            return [name for name, score in suggestions]

        except Exception as e:
            logger.debug(f"Failed to suggest tool names: {e}")
            return []

    def _detect_tool_call_intent(self, response: str) -> Optional[str]:
        if not response:
            return None
        for pattern, error_msg in self.TOOL_INTENT_PATTERNS:
            if re.search(pattern, response, re.IGNORECASE):
                logger.debug(f"Detected tool intent pattern: {pattern}")
                return error_msg
        return None

    def _build_format_correction_message(self, error: str) -> str:
        return f"""**Tool Call Format Error**\n\n{error}\n\nPlease use the correct JSON format to retry the tool call:

```json
{{
  "tool_call": {{
    "tool_name": "filesystem_read_file",
    "parameters": {{
      "path": "file_path"
    }}
  }}
}}
```

**Note**:
- Must use `tool_call` (not `tool_code`)
- Must use `filesystem_read_file` (not `fs.read_file`)
- Values must be JSON objects (not Python code strings)

Please retry the tool call."""

    async def execute_tool_loop(
        self,
        conv_manager: Any,
        assistant_response: str,
        execution_id: str,
        profile_id: str,
        provider: Any,
        model_name: Optional[str],
        max_iterations: int = 5,
        workspace_id: Optional[str] = None,
        sandbox_id: Optional[str] = None,
    ) -> Tuple[str, List[str]]:
        
        # Ensure filesystem tools are registered
        try:
            from backend.app.services.playbook.tool_executor import _init_filesystem_tools
            _init_filesystem_tools()
        except Exception:
            pass

        if workspace_id or sandbox_id:
            self.execution_context["workspace_id"] = workspace_id
            self.execution_context["sandbox_id"] = sandbox_id
            logger.debug(f"Set execution context: workspace_id={workspace_id}, sandbox_id={sandbox_id}")

        if execution_id:
            self.execution_context["execution_id"] = execution_id
            if "trace_id" not in self.execution_context:
                self.execution_context["trace_id"] = execution_id

        effective_workspace_id = workspace_id or self.execution_context.get("workspace_id")
        loop_budget_max_iterations = max_iterations
        loop_budget_max_tool_calls = None

        if effective_workspace_id:
            try:
                profile_store = WorkspaceRuntimeProfileStore()
                runtime_profile = await profile_store.get_runtime_profile(effective_workspace_id)
                if runtime_profile:
                    runtime_profile.ensure_phase2_fields()
                    loop_budget = runtime_profile.loop_budget
                    loop_budget_max_iterations = min(max_iterations, loop_budget.max_iterations)
                    loop_budget_max_tool_calls = loop_budget.max_tool_calls
                    logger.debug(f"Using LoopBudget: max_iterations={loop_budget_max_iterations}, kwargs calls={loop_budget_max_tool_calls}")
            except Exception as e:
                logger.debug(f"Failed to load runtime profile for LoopBudget: {e}")

        max_tool_iterations = loop_budget_max_iterations
        tool_iteration = 0
        tool_call_count = 0 
        used_tools = []
        current_response = assistant_response
        format_retry_count = 0
        max_format_retries = 2

        _parent_ctx_token = None
        if execution_id:
            try:
                from backend.app.services.parameter_adapter.context import active_parent_execution_id
                _parent_ctx_token = active_parent_execution_id.set(execution_id)
            except Exception:
                pass 

        try:
            while tool_iteration < max_tool_iterations:
                logger.debug(f"PlaybookToolExecutor: Parsing tool calls from response")
                tool_calls = conv_manager.parse_tool_calls_from_response(current_response)

                if not tool_calls:
                    logger.info(f"PlaybookToolExecutor: No tool calls found in iteration {tool_iteration + 1}")
                    format_error = self._detect_tool_call_intent(current_response)

                    if format_error and format_retry_count < max_format_retries:
                        format_retry_count += 1
                        logger.warning(f"PlaybookToolExecutor: Detected tool call intent with wrong format, asking LLM to retry")
                        correction_msg = self._build_format_correction_message(format_error)
                        conv_manager.add_tool_call_results([{"tool_name": "system", "result": correction_msg, "success": False, "error": "Format error"}])
                        messages = await conv_manager.get_messages_for_llm()
                        current_response = await provider.chat_completion(messages, model=model_name if model_name else None)
                        conv_manager.add_assistant_message(current_response)
                        continue

                    if getattr(conv_manager, "auto_execute", False) and tool_iteration < max_tool_iterations - 1:
                        logger.info(f"PlaybookToolExecutor: Auto-execute mode - no tool calls but prompting LLM to continue")
                        continue_prompt = (
                            "**⚡ AUTO-EXECUTE MODE: You must continue executing the next steps in the SOP.**\n"
                            "- Review the conversation history and tool results above\n"
                            "- Check the SOP for the next required tool to call\n"
                            "- Immediately call the next tool using the correct JSON format\n"
                            "- Do NOT stop or provide explanations without calling tools\n"
                            "- Continue until all SOP phases are complete\n"
                        )
                        conv_manager.conversation_history.append({"role": "system", "content": continue_prompt})
                        messages = await conv_manager.get_messages_for_llm()
                        current_response = await provider.chat_completion(messages, model=model_name if model_name else None)
                        conv_manager.add_assistant_message(current_response)
                        tool_iteration += 1
                        continue

                    logger.info("PlaybookToolExecutor: No tool calls found, exiting loop")
                    break

                format_retry_count = 0
                logger.info(f"PlaybookToolExecutor: Found {len(tool_calls)} tool call(s)")

                if loop_budget_max_tool_calls is not None:
                    remaining_tool_calls = loop_budget_max_tool_calls - tool_call_count
                    if remaining_tool_calls <= 0:
                        logger.warning("LoopBudget: Tool call limit reached. Stopping tool execution loop.")
                        break
                    if len(tool_calls) > remaining_tool_calls:
                        logger.warning(f"LoopBudget: Limiting tool calls from {len(tool_calls)} to {remaining_tool_calls}")
                        tool_calls = tool_calls[:remaining_tool_calls]

                tool_results = []
                for tool_call in tool_calls:
                    tool_slot = tool_call.get("tool_slot")
                    tool_name = tool_call.get("tool_name")
                    parameters = tool_call.get("parameters", {})
                    tool_policy = tool_call.get("tool_policy")

                    if not tool_slot and not tool_name:
                        continue

                    try:
                        if tool_slot:
                            execution_kwargs = {k: v for k, v in parameters.items() if k not in ["workspace_id", "project_id"]}
                            result = await self.execute_tool_fn(
                                tool_slot=tool_slot,
                                tool_policy=tool_policy,
                                profile_id=profile_id,
                                workspace_id=getattr(conv_manager, "workspace_id", None),
                                project_id=getattr(conv_manager, "project_id", None),
                                execution_id=execution_id,
                                step_id=None,
                                **execution_kwargs,
                            )
                            display_name = tool_slot
                        else:
                            execution_kwargs = parameters.copy()
                            workspace_id_manager = getattr(conv_manager, "workspace_id", None)
                            if "workspace_id" not in execution_kwargs and workspace_id_manager:
                                execution_kwargs["workspace_id"] = workspace_id_manager
                            result = await self.execute_tool_fn(
                                tool_fqn=tool_name,
                                profile_id=profile_id,
                                execution_id=execution_id,
                                step_id=None,
                                **execution_kwargs,
                            )
                            display_name = tool_name

                        tool_results.append({
                            "tool_name": display_name,
                            "tool_slot": tool_slot if tool_slot else None,
                            "result": result,
                            "success": True,
                        })
                        used_tools.append(display_name)
                        tool_call_count += 1

                        if loop_budget_max_tool_calls is not None and tool_call_count >= loop_budget_max_tool_calls:
                            logger.warning(f"LoopBudget: Tool call limit reached. Stopping tool execution loop.")
                            break

                    except Exception as e:
                        error_msg = str(e)[:500]
                        display_name = tool_slot if tool_slot else tool_name
                        logger.error(f"PlaybookToolExecutor: Tool {display_name} execution failed: {e}", exc_info=True)

                        enhanced_error = error_msg
                        if "not found" in error_msg.lower() and tool_name:
                            suggestions = self._suggest_tool_names(tool_name, getattr(conv_manager, "workspace_id", None))
                            if suggestions:
                                enhanced_error = f"Tool '{tool_name}' not found.\n**Did you mean one of these?**\n"
                                for i, suggestion in enumerate(suggestions[:5], 1):
                                    enhanced_error += f"{i}. `{suggestion}`\n"
                                enhanced_error += "\nPlease retry with the correct tool name from the list above."
                            else:
                                related_tools = self._find_related_tools(tool_name, getattr(conv_manager, "workspace_id", None))
                                if related_tools:
                                    enhanced_error = f"Tool '{tool_name}' not found.\n**Related tools you might want to use:**\n"
                                    for i, tool in enumerate(related_tools[:5], 1):
                                        enhanced_error += f"{i}. `{tool}`\n"
                                    enhanced_error += "\nPlease check the available tools list and use the exact tool name."
                                else:
                                    enhanced_error = f"Tool '{tool_name}' not found.\nPlease check the available tools list and use the exact tool name."
                        elif tool_slot and "not configured" not in error_msg.lower() and "not found" not in error_msg.lower():
                            enhanced_error = (
                                f"Failed to execute tool slot '{tool_slot}': {error_msg}\n"
                                f"If this slot is not working, you can:\n"
                                f"1. Check the slot mapping configuration\n"
                                f"2. Verify the mapped tool '{tool_name}' is available and functional\n"
                                f"3. Try using the tool directly instead of the slot"
                            )

                        tool_results.append({
                            "tool_name": display_name,
                            "tool_slot": tool_slot if tool_slot else None,
                            "result": None,
                            "success": False,
                            "error": enhanced_error,
                        })

                if tool_results:
                    conv_manager.add_tool_call_results(tool_results)

                messages = await conv_manager.get_messages_for_llm()
                current_response = await provider.chat_completion(messages, model=model_name if model_name else None)
                conv_manager.add_assistant_message(current_response)
                tool_iteration += 1

                if not any(r.get("success", False) for r in tool_results) and tool_iteration >= 2:
                    new_tool_calls = conv_manager.parse_tool_calls_from_response(current_response)
                    if new_tool_calls:
                        logger.info("PlaybookToolExecutor: LLM is retrying after tool failures, allowing continuation")
                        continue
                    else:
                        logger.warning("PlaybookToolExecutor: All tool calls failed and LLM stopped retrying, exiting loop")
                        break

        finally:
            if _parent_ctx_token:
                try:
                    from backend.app.services.parameter_adapter.context import active_parent_execution_id
                    active_parent_execution_id.reset(_parent_ctx_token)
                except Exception:
                    pass

        return current_response, used_tools
