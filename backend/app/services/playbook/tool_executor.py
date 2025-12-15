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
        (r'tool_code', "Used 'tool_code' instead of 'tool_call'"),
        (r'tool_command', "Used 'tool_command' instead of 'tool_call'"),
        (r'function_call', "Used 'function_call' instead of 'tool_call'"),
        (r'fs\.read_file', "Used 'fs.read_file' instead of 'filesystem_read_file'"),
        (r'fs\.write_file', "Used 'fs.write_file' instead of 'filesystem_write_file'"),
        (r'fs\.list_files', "Used 'fs.list_files' instead of 'filesystem_list_files'"),
        (r'print\s*\(\s*filesystem_', "Used Python print() syntax to call tools"),
        (r'await\s+filesystem_', "Used async/await syntax to call tools"),
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
        return f"""**Tool Call Format Error**

{error}

Please use the correct JSON format to retry the tool call:

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

    async def execute_tool(
        self,
        tool_fqn: Optional[str] = None,
        tool_slot: Optional[str] = None,
        tool_policy: Optional[Any] = None,
        profile_id: str = None,
        workspace_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        step_id: Optional[str] = None,
        factory_cluster: Optional[str] = None,
        project_id: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Unified tool execution entry point

        This method provides a single entry point for all tool calls from Playbooks.
        Supports both tool_slot (new) and tool_fqn (legacy) modes.

        Args:
            tool_fqn: Fully qualified tool name (e.g., "major_proposal.import_template_from_files")
            tool_slot: Tool slot identifier (e.g., "cms.footer.apply_style") - new format
            tool_policy: Tool policy constraints (optional, used when tool_slot is provided)
            profile_id: Profile ID (optional, for event recording)
            workspace_id: Workspace ID (required for tool_slot resolution)
            execution_id: Execution ID
            step_id: Step ID
            factory_cluster: Factory cluster name
            project_id: Project ID (optional, for project-level slot mapping)
            **kwargs: Parameters to pass to the tool

        Returns:
            Tool execution result
        """
        # Resolve tool_slot to tool_fqn if provided
        if tool_slot:
            if not workspace_id:
                raise ValueError("workspace_id is required when using tool_slot")

            # Resolve slot to tool_id
            from backend.app.services.tool_slot_resolver import get_tool_slot_resolver, SlotNotFoundError
            from backend.app.services.tool_policy_engine import get_tool_policy_engine, PolicyViolationError

            resolver = get_tool_slot_resolver(store=self.store)
            try:
                resolved_tool_id = await resolver.resolve(
                    slot=tool_slot,
                    workspace_id=workspace_id,
                    project_id=project_id
                )
                tool_fqn = resolved_tool_id
                logger.info(f"Resolved tool slot '{tool_slot}' to tool '{tool_fqn}'")
            except SlotNotFoundError as e:
                logger.error(f"Failed to resolve tool slot '{tool_slot}': {e}")
                # Build detailed error message with suggestions
                error_parts = [
                    f"Tool slot '{tool_slot}' is not configured."
                ]

                # Add suggestion if available
                if hasattr(e, 'suggestion') and e.suggestion:
                    error_parts.append(f"\n{e.suggestion}")

                # Add configuration steps
                config_level = "project" if project_id else "workspace"
                error_parts.append(
                    f"\nTo configure this slot:\n"
                    f"1. Use the API endpoint: POST /api/v1/tool-slots\n"
                    f"2. Or configure it in the {config_level} settings\n"
                    f"3. Required fields: slot='{tool_slot}', tool_id=<concrete_tool_id>"
                )

                # Add available slots hint
                if hasattr(e, 'available_slots') and e.available_slots:
                    error_parts.append(
                        f"\nNote: You can also use an existing slot directly, "
                        f"or use a concrete tool_id instead of a slot."
                    )

                raise ValueError("\n".join(error_parts))

            # Check policy if provided
            if tool_policy:
                policy_engine = get_tool_policy_engine()
                try:
                    policy_engine.check(
                        tool_id=tool_fqn,
                        policy=tool_policy,
                        workspace_id=workspace_id
                    )
                    logger.debug(f"Tool '{tool_fqn}' passed policy check")
                except PolicyViolationError as e:
                    logger.error(f"Tool '{tool_fqn}' violates policy: {e}")
                    policy_info = []
                    if tool_policy:
                        policy_info.append(f"Policy constraints:")
                        if tool_policy.risk_level:
                            policy_info.append(f"  - Risk level: {tool_policy.risk_level}")
                        if tool_policy.env:
                            policy_info.append(f"  - Environment: {tool_policy.env}")
                        if tool_policy.allowed_tool_patterns:
                            policy_info.append(f"  - Allowed patterns: {', '.join(tool_policy.allowed_tool_patterns)}")

                    error_msg = f"Tool execution blocked by policy: {str(e)}"
                    if policy_info:
                        error_msg += f"\n\n{chr(10).join(policy_info)}"
                    error_msg += f"\n\nTo resolve this:\n1. Check if the tool '{tool_fqn}' matches the policy constraints\n2. Update the tool slot mapping to use a different tool\n3. Or adjust the policy in the playbook definition"

                    raise ValueError(error_msg)
        elif not tool_fqn:
            raise ValueError("Either tool_fqn or tool_slot must be provided")

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
                        "error": "Format error"
                    }])

                    # Get LLM to retry with correct format
                    messages = await conv_manager.get_messages_for_llm()
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
                tool_slot = tool_call.get("tool_slot")
                tool_name = tool_call.get("tool_name")
                parameters = tool_call.get("parameters", {})

                # Extract tool_policy if present (for slot-based calls)
                tool_policy = tool_call.get("tool_policy")

                if not tool_slot and not tool_name:
                    logger.warning(f"Invalid tool call: missing tool_slot or tool_name")
                    continue

                try:
                    # Execute tool (support both slot and name modes)
                    if tool_slot:
                        logger.info(f"PlaybookToolExecutor: Executing tool slot {tool_slot} with parameters: {list(parameters.keys())}")
                        result = await self.execute_tool(
                            tool_slot=tool_slot,
                            tool_policy=tool_policy,
                            profile_id=profile_id,
                            workspace_id=conv_manager.workspace_id,
                            project_id=conv_manager.project_id,
                            execution_id=execution_id,
                            step_id=None,  # Will be set when step event is created
                            **parameters
                        )
                        display_name = tool_slot
                    else:
                        logger.info(f"PlaybookToolExecutor: Executing tool {tool_name} with parameters: {list(parameters.keys())}")
                        result = await self.execute_tool(
                            tool_fqn=tool_name,
                            profile_id=profile_id,
                            workspace_id=conv_manager.workspace_id,
                            execution_id=execution_id,
                            step_id=None,  # Will be set when step event is created
                            **parameters
                        )
                        display_name = tool_name

                    tool_results.append({
                        "tool_name": display_name,
                        "tool_slot": tool_slot if tool_slot else None,
                        "result": result,
                        "success": True
                    })
                    used_tools.append(display_name)

                    logger.info(f"PlaybookToolExecutor: Tool {display_name} executed successfully")

                except Exception as e:
                    error_msg = str(e)[:500]
                    display_name = tool_slot if tool_slot else tool_name
                    logger.error(f"PlaybookToolExecutor: Tool {display_name} execution failed: {e}", exc_info=True)

                    # Enhanced error message for slot-related errors
                    enhanced_error = error_msg
                    if tool_slot and ("not configured" in error_msg.lower() or "not found" in error_msg.lower()):
                        enhanced_error = error_msg  # Already enhanced by SlotNotFoundError handling
                    elif tool_slot:
                        # Add context for slot execution failures
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
                        "error": enhanced_error
                    })

            # Add tool call results to conversation
            if tool_results:
                conv_manager.add_tool_call_results(tool_results)

            # Continue conversation with tool results
            # Always let LLM retry on errors (it will see the error message and can correct parameters)
            # Only exit if we've reached max iterations to avoid infinite loops
            messages = conv_manager.get_messages_for_llm()
            current_response = await provider.chat_completion(messages, model=model_name if model_name else None)
            conv_manager.add_assistant_message(current_response)
            tool_iteration += 1

            # If all tools failed and we've tried multiple times, check if LLM is stuck
            if not any(r.get("success", False) for r in tool_results) and tool_iteration >= 2:
                # Check if LLM is still trying to call the same failed tool
                new_tool_calls = conv_manager.parse_tool_calls_from_response(current_response)
                if new_tool_calls:
                    # LLM is trying again, let it continue
                    logger.info(f"PlaybookToolExecutor: LLM is retrying after tool failures, allowing continuation")
                    continue
                else:
                    # LLM gave up or changed approach, exit loop
                    logger.warning(f"PlaybookToolExecutor: All tool calls failed and LLM stopped retrying, exiting loop")
                    break

        return current_response, used_tools

