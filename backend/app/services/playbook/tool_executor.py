"""
Playbook Tool Executor
Handles tool parsing, execution loop, and tool call management
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Awaitable

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.shared.tool_executor import execute_tool
from backend.app.services.conversation.workflow_tracker import WorkflowTracker

logger = logging.getLogger(__name__)

# Ensure filesystem tools are registered (cross-process via Redis)
def _init_filesystem_tools():
    """
    Register filesystem tools with cross-process coordination via Redis.
    Called at module import and before tool execution.
    """
    try:
        from backend.app.services.tools.registry import register_filesystem_tools, _mindscape_tools
        from backend.app.services.cache.redis_cache import get_cache_service

        required = ["filesystem_list_files", "filesystem_read_file", "filesystem_write_file", "filesystem_search"]
        missing = [t for t in required if t not in _mindscape_tools]

        if not missing:
            return  # All tools already registered

        logger.info(f"PlaybookToolExecutor: Registering filesystem tools (missing: {missing})")
        register_filesystem_tools()

        # Verify and set Redis marker
        still_missing = [t for t in required if t not in _mindscape_tools]
        if still_missing:
            logger.error(f"PlaybookToolExecutor: Failed to register: {still_missing}")
        else:
            logger.info(f"PlaybookToolExecutor: Successfully registered filesystem tools")
            try:
                cache = get_cache_service()
                cache.set("builtin_tools:filesystem:registered", "true", ttl=3600)
            except Exception:
                pass  # Non-critical

    except Exception as e:
        logger.error(f"PlaybookToolExecutor: Failed to init filesystem tools: {e}", exc_info=True)

_init_filesystem_tools()


class PlaybookToolExecutor:
    """Handles tool execution for Playbook runs"""

    # Patterns that indicate LLM tried to call tools but used wrong format
    TOOL_INTENT_PATTERNS = [
        (r'tool_code', "使用了 'tool_code' 而非 'tool_call'"),
        (r'tool_command', "使用了 'tool_command' 而非 'tool_call'"),
        (r'function_call', "使用了 'function_call' 而非 'tool_call'"),
        (r'fs\.read_file', "使用了 'fs.read_file' 而非 'filesystem_read_file'"),
        (r'fs\.write_file', "使用了 'fs.write_file' 而非 'filesystem_write_file'"),
        (r'fs\.list_files', "使用了 'fs.list_files' 而非 'filesystem_list_files'"),
        (r'print\s*\(\s*filesystem_', "使用了 Python print() 語法調用工具"),
        (r'await\s+filesystem_', "使用了 async/await 語法調用工具"),
    ]

    def __init__(
        self,
        store: Any,
        workflow_tracker: WorkflowTracker
    ):
        self.store = store
        self.workflow_tracker = workflow_tracker
        self.execution_context: Dict[str, Any] = {}

    def _detect_tool_call_intent(self, response: str) -> Optional[str]:
        """
        Detect if LLM intended to call tools but used wrong format.

        Returns:
            Error description if wrong format detected, None otherwise
        """
        import re

        if not response:
            return None

        for pattern, error_msg in self.TOOL_INTENT_PATTERNS:
            if re.search(pattern, response, re.IGNORECASE):
                logger.debug(f"Detected tool intent pattern: {pattern}")
                return error_msg

        return None

    def _build_format_correction_message(self, error: str) -> str:
        """Build a message asking LLM to correct the tool call format."""
        return f"""⚠️ **工具調用格式錯誤**

{error}

請使用正確的 JSON 格式重新調用工具：

```json
{{
  "tool_call": {{
    "tool_name": "filesystem_read_file",
    "parameters": {{
      "path": "檔案路徑"
    }}
  }}
}}
```

**注意**：
- 必須使用 `tool_call`（不是 `tool_code`）
- 必須使用 `filesystem_read_file`（不是 `fs.read_file`）
- 值必須是 JSON 對象（不是 Python 代碼字符串）

請重新調用工具。"""

    async def execute_tool(
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
            workspace_id: Workspace ID
            execution_id: Execution ID
            step_id: Step ID
            factory_cluster: Factory cluster name
            **kwargs: Parameters to pass to the tool

        Returns:
            Tool execution result
        """
        tool_start_time = datetime.utcnow()
        tool_call_id = str(uuid.uuid4())

        if not factory_cluster:
            # Try to get default_cluster from execution context
            default_cluster = self.execution_context.get("default_cluster")
            if default_cluster:
                factory_cluster = default_cluster
            else:
                # Try to extract connection_id from tool_fqn (format: {connection_id}.{tool_type}.{tool_name})
                # and get cluster from tool connection
                connection_id = None
                if "." in tool_fqn:
                    parts = tool_fqn.split(".", 1)
                    if len(parts) >= 1:
                        potential_connection_id = parts[0]
                        # Check if this looks like a connection_id (not a capability package name)
                        # Connection IDs are typically UUIDs or short identifiers
                        if potential_connection_id and not potential_connection_id.startswith(("filesystem_", "sandbox.", "capability.")):
                            connection_id = potential_connection_id

                if connection_id and workspace_id:
                    try:
                        from backend.app.services.tool_registry import ToolRegistryService
                        registry = ToolRegistryService(db_path=self.store.db_path)
                        connection = registry.get_connection(connection_id, profile_id=profile_id)
                        if connection and connection.remote_cluster_url:
                            # Extract cluster name from URL or use a generic identifier
                            # For remote clusters, use a generic identifier based on connection type
                            factory_cluster = connection.connection_type or "remote"
                        elif connection:
                            # Local connection, use local_mcp
                            factory_cluster = "local_mcp"
                        else:
                            # Fallback: use default from workspace or local_mcp
                            factory_cluster = default_cluster or "local_mcp"
                    except Exception as e:
                        logger.debug(f"Failed to get cluster from connection {connection_id}: {e}")
                        factory_cluster = default_cluster or "local_mcp"
                else:
                    # For built-in tools (filesystem, sandbox, etc.), use local_mcp
                    if tool_fqn.startswith(("filesystem_", "sandbox.", "local_")) or "mcp" in tool_fqn.lower():
                        factory_cluster = "local_mcp"
                    else:
                        # Default fallback
                        factory_cluster = default_cluster or "local_mcp"

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

            if tool_fqn.startswith("sandbox."):
                execution_sandbox_id = self.execution_context.get("sandbox_id")
                execution_workspace_id = workspace_id or self.execution_context.get("workspace_id")
                if execution_sandbox_id and execution_workspace_id:
                    if "sandbox_id" not in normalized_kwargs:
                        normalized_kwargs["sandbox_id"] = execution_sandbox_id
                    if "workspace_id" not in normalized_kwargs:
                        normalized_kwargs["workspace_id"] = execution_workspace_id
                    logger.debug(f"Auto-injected sandbox_id={execution_sandbox_id} and workspace_id={execution_workspace_id} for {tool_fqn}")

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

    async def execute_tool_loop(
        self,
        conv_manager: Any,
        assistant_response: str,
        execution_id: str,
        profile_id: str,
        provider: Any,
        model_name: Optional[str] = None,
        max_iterations: int = 5,
        workspace_id: Optional[str] = None,
        sandbox_id: Optional[str] = None
    ) -> tuple[str, List[str]]:
        """
        Execute tool calls in a loop until no more tools are found or max iterations reached.

        Args:
            conv_manager: ConversationManager instance
            assistant_response: Initial assistant response
            execution_id: Execution ID
            profile_id: Profile ID
            provider: LLM provider instance
            model_name: Model name for LLM calls
            max_iterations: Maximum number of tool execution iterations
            workspace_id: Workspace ID (for sandbox tools auto-injection)
            sandbox_id: Sandbox ID (for sandbox tools auto-injection)

        Returns:
            Tuple of (final_assistant_response, used_tools_list)
        """
        # Ensure filesystem tools are registered (may have been missed at import)
        _init_filesystem_tools()

        if workspace_id or sandbox_id:
            self.execution_context["workspace_id"] = workspace_id
            self.execution_context["sandbox_id"] = sandbox_id
            logger.debug(f"Set execution context: workspace_id={workspace_id}, sandbox_id={sandbox_id}")

        max_tool_iterations = max_iterations
        tool_iteration = 0
        used_tools = []
        current_response = assistant_response
        format_retry_count = 0
        max_format_retries = 2  # Max retries for format errors

        while tool_iteration < max_tool_iterations:
            # Parse tool calls from current assistant response
            logger.debug(f"PlaybookToolExecutor: Parsing tool calls from response (length={len(current_response) if current_response else 0})")
            tool_calls = conv_manager.parse_tool_calls_from_response(current_response)

            if not tool_calls:
                # Check if LLM intended to call tools but used wrong format
                format_error = self._detect_tool_call_intent(current_response)

                if format_error and format_retry_count < max_format_retries:
                    # LLM tried to call tools but format was wrong - ask to retry
                    format_retry_count += 1
                    logger.warning(f"PlaybookToolExecutor: Detected tool call intent with wrong format, asking LLM to retry ({format_retry_count}/{max_format_retries})")

                    # Add correction message to conversation
                    correction_msg = self._build_format_correction_message(format_error)
                    conv_manager.add_tool_call_results([{
                        "tool_name": "system",
                        "result": correction_msg,
                        "success": False,
                        "error": "格式錯誤"
                    }])

                    # Get LLM to retry with correct format
                    messages = conv_manager.get_messages_for_llm()
                    current_response = await provider.chat_completion(messages, model=model_name if model_name else None)
                    conv_manager.add_assistant_message(current_response)
                    continue  # Try parsing again

                logger.info(f"PlaybookToolExecutor: No tool calls found in iteration {tool_iteration + 1}, exiting loop")
                break  # No tool calls found, exit loop

            # Reset format retry counter on successful parse
            format_retry_count = 0
            logger.info(f"PlaybookToolExecutor: Found {len(tool_calls)} tool call(s) in iteration {tool_iteration + 1}")

            # Execute all tool calls
            tool_results = []
            for tool_call in tool_calls:
                tool_name = tool_call.get("tool_name")
                parameters = tool_call.get("parameters", {})

                if not tool_name:
                    logger.warning(f"Invalid tool call: missing tool_name")
                    continue

                try:
                    # Execute tool
                    logger.info(f"PlaybookToolExecutor: Executing tool {tool_name} with parameters: {list(parameters.keys())}")
                    result = await self.execute_tool(
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

                    logger.info(f"PlaybookToolExecutor: Tool {tool_name} executed successfully")

                except Exception as e:
                    error_msg = str(e)[:500]
                    logger.error(f"PlaybookToolExecutor: Tool {tool_name} execution failed: {e}", exc_info=True)
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
                current_response = await provider.chat_completion(messages, model=model_name if model_name else None)
                conv_manager.add_assistant_message(current_response)
                tool_iteration += 1
            else:
                # All tool calls failed, exit loop
                logger.warning(f"PlaybookToolExecutor: All tool calls failed, exiting tool execution loop")
                break

        return current_response, used_tools

