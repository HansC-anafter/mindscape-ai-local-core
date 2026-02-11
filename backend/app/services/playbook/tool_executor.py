"""
Playbook Tool Executor
Handles tool parsing, execution loop, and tool call management
"""

import logging
import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, List, Optional, Any, Callable, Awaitable

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.shared.tool_executor import execute_tool
from backend.app.services.conversation.workflow_tracker import WorkflowTracker
from backend.app.core.trace import get_trace_recorder, TraceNodeType, TraceStatus
from backend.app.services.conversation.policy_guard import PolicyGuard, PolicyCheckResult
from backend.app.services.stores.workspace_runtime_profile_store import WorkspaceRuntimeProfileStore
from backend.app.services.tool_registry import ToolRegistryService

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

    def _find_related_tools(self, attempted_name: str, workspace_id: Optional[str] = None) -> List[str]:
        """
        Find related tools based on keywords in the attempted tool name.
        This is used when no similar tools are found, to provide context.

        Args:
            attempted_name: The tool name that was attempted
            workspace_id: Workspace ID for tool list lookup

        Returns:
            List of related tool names (filtered by keywords)
        """
        try:
            from backend.app.services.tools.registry import get_all_mindscape_tools
            from backend.app.services.tool_list_service import get_tool_list_service

            # Extract keywords from attempted name
            attempted_lower = attempted_name.lower()
            keywords = [word for word in attempted_lower.replace('.', '_').replace('-', '_').split('_') if len(word) > 2]

            if not keywords:
                return []

            # Get all available tools
            all_tools = []

            # Get MindscapeTools
            try:
                mindscape_tools = get_all_mindscape_tools()
                all_tools.extend([tool.metadata.name for tool in mindscape_tools.values() if hasattr(tool, 'metadata')])
            except Exception:
                pass

            # Get tools from ToolListService
            if workspace_id:
                try:
                    tool_list_service = get_tool_list_service()
                    tool_infos = tool_list_service.get_tools(
                        workspace_id=workspace_id,
                        enabled_only=True
                    )
                    all_tools.extend([tool.tool_id for tool in tool_infos])
                except Exception:
                    pass

            # Remove duplicates
            all_tools = list(set(all_tools))

            # Find tools that contain any of the keywords
            related = []
            for tool_name in all_tools:
                tool_lower = tool_name.lower()
                # Check if tool name contains any keyword
                if any(keyword in tool_lower for keyword in keywords):
                    related.append(tool_name)

            # Sort by relevance (more keywords matched = higher priority)
            related.sort(key=lambda t: sum(1 for k in keywords if k in t.lower()), reverse=True)
            return related[:10]  # Return top 10

        except Exception as e:
            logger.debug(f"Failed to find related tools: {e}")
            return []

    def _suggest_tool_names(self, attempted_name: str, workspace_id: Optional[str] = None) -> List[str]:
        """
        Suggest similar tool names when a tool is not found.

        Args:
            attempted_name: The tool name that was attempted
            workspace_id: Workspace ID for tool list lookup

        Returns:
            List of suggested tool names (similar matches)
        """
        suggestions = []
        try:
            from backend.app.services.tools.registry import get_all_mindscape_tools
            from backend.app.services.tool_list_service import get_tool_list_service

            # Get all available tools
            all_tools = []

            # Get MindscapeTools
            try:
                mindscape_tools = get_all_mindscape_tools()
                all_tools.extend([tool.metadata.name for tool in mindscape_tools if hasattr(tool, 'metadata')])
            except Exception:
                pass

            # Get tools from ToolListService
            if workspace_id:
                try:
                    tool_list_service = get_tool_list_service()
                    tool_infos = tool_list_service.get_tools(
                        workspace_id=workspace_id,
                        enabled_only=True
                    )
                    all_tools.extend([tool.tool_id for tool in tool_infos])
                except Exception:
                    pass

            # Remove duplicates
            all_tools = list(set(all_tools))

            # Find similar tool names
            attempted_lower = attempted_name.lower()
            attempted_parts = set(attempted_lower.replace('.', '_').replace('-', '_').split('_'))

            for tool_name in all_tools:
                tool_lower = tool_name.lower()
                tool_parts = set(tool_lower.replace('.', '_').replace('-', '_').split('_'))

                # Calculate similarity score
                common_parts = attempted_parts.intersection(tool_parts)
                if common_parts:
                    # If there's overlap, it's a potential match
                    score = len(common_parts) / max(len(attempted_parts), len(tool_parts))
                    if score > 0.3:  # At least 30% similarity
                        suggestions.append((tool_name, score))

            # Sort by score (descending) and return tool names
            suggestions.sort(key=lambda x: x[1], reverse=True)
            return [name for name, score in suggestions]

        except Exception as e:
            logger.debug(f"Failed to suggest tool names: {e}")
            return []

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

        # Runtime Profile PolicyGuard check (before tool execution)
        # Try to get workspace_id from multiple sources to ensure PolicyGuard always runs
        effective_workspace_id = workspace_id or self.execution_context.get("workspace_id")

        if effective_workspace_id:
            try:
                # Get runtime profile (create default if not exists, like GET API)
                profile_store = WorkspaceRuntimeProfileStore(db_path=self.store.db_path)
                runtime_profile = profile_store.get_runtime_profile(effective_workspace_id)

                if not runtime_profile:
                    # Create default profile if not exists (ensure PolicyGuard always works)
                    runtime_profile = profile_store.create_default_profile(effective_workspace_id)
                    logger.info(f"Created default runtime profile for workspace {effective_workspace_id}")

                # Get tool registry
                tool_registry = ToolRegistryService(db_path=self.store.db_path)

                # Get event store for event recording
                from backend.app.services.stores.events_store import EventsStore
                event_store = EventsStore(db_path=self.store.db_path)

                # Check policy (always check, even with default profile)
                policy_guard = PolicyGuard(strict_mode=True, tool_registry=tool_registry)

                # Track tool call chain for Phase 2 max_tool_call_chain enforcement
                previous_tool_id = self.execution_context.get("last_tool_id")

                policy_result = policy_guard.check_tool_call(
                    tool_id=tool_fqn,
                    runtime_profile=runtime_profile,
                    tool_call_params=kwargs,
                    tool_registry=tool_registry,
                    execution_id=execution_id,
                    previous_tool_id=previous_tool_id,
                    workspace_id=effective_workspace_id,
                    profile_id=getattr(runtime_profile, 'profile_id', None),
                    event_store=event_store
                )

                # Record tool call in chain tracker (Phase 2)
                if execution_id:
                    from backend.app.services.conversation.tool_call_chain_tracker import get_chain_tracker
                    chain_tracker = get_chain_tracker(execution_id)
                    chain_tracker.record_tool_call(tool_fqn, previous_tool_id)
                    self.execution_context["last_tool_id"] = tool_fqn

                    # Phase 2: Record tool call in MultiAgentOrchestrator (for LoopBudget tracking)
                    try:
                        from backend.app.services.orchestration.orchestrator_registry import get_orchestrator_registry
                        orchestrator_registry = get_orchestrator_registry()

                        # Try execution_id first (primary key)
                        orchestrator = orchestrator_registry.get(execution_id)

                        # Fallback: try multiple keys if execution_id lookup fails
                        if not orchestrator:
                            # Get possible fallback keys from execution_context
                            trace_id = self.execution_context.get("trace_id")
                            message_id = self.execution_context.get("message_id")

                            # Try fallback keys in order of priority
                            fallback_keys = []
                            if trace_id:
                                fallback_keys.append(trace_id)
                            if message_id:
                                fallback_keys.append(message_id)

                            if fallback_keys:
                                orchestrator = orchestrator_registry.find_by_any_key(*fallback_keys)
                                if orchestrator:
                                    logger.info(
                                        f"OrchestratorRegistry: Found orchestrator using fallback key "
                                        f"(execution_id={execution_id} not found, used one of: {fallback_keys})"
                                    )

                            # Last resort: try to find any registered orchestrator (risky but better than nothing)
                            if not orchestrator:
                                orchestrator = orchestrator_registry.find_any()
                                if orchestrator:
                                    logger.warning(
                                        f"OrchestratorRegistry: Using 'find_any' fallback for execution_id={execution_id}. "
                                        f"This may return incorrect orchestrator if multiple executions are running."
                                    )

                            # If still not found, log warning
                            if not orchestrator:
                                logger.warning(
                                    f"OrchestratorRegistry: No orchestrator found for execution_id={execution_id} "
                                    f"(tried fallback keys: {fallback_keys}). "
                                    f"Tool call will not be counted in LoopBudget. "
                                    f"This may indicate a registration key mismatch or orchestrator not initialized."
                                )

                        if orchestrator:
                            orchestrator.record_tool_call()
                            logger.debug(
                                f"MultiAgentOrchestrator: Recorded tool call '{tool_fqn}' "
                                f"(total: {orchestrator.state.tool_call_count}, "
                                f"execution_id={execution_id})"
                            )
                    except Exception as e:
                        logger.warning(f"Failed to record tool call in orchestrator: {e}", exc_info=True)

                if not policy_result.allowed:
                    error_msg = f"Tool execution blocked by Runtime Profile policy: {policy_result.reason}"
                    if policy_result.user_message:
                        error_msg += f"\n{policy_result.user_message}"
                    logger.warning(f"PolicyGuard blocked tool '{tool_fqn}': {policy_result.reason}")
                    raise ValueError(error_msg)

                if policy_result.requires_approval:
                    logger.info(f"Tool '{tool_fqn}' requires approval: {policy_result.reason}")
                    # TODO: In future, implement approval flow
                    # For now, log and proceed (can be enhanced in stage 2)
            except ValueError:
                raise  # Re-raise policy violations
            except Exception as e:
                logger.warning(f"Failed to check Runtime Profile policy: {e}", exc_info=True)
                # Don't block execution if policy check fails (fail-open for MVP)
        else:
            # No workspace_id available - log warning but allow execution (fail-open for MVP)
            # This should be rare and indicates a code path that doesn't provide workspace context
            logger.warning(
                f"PolicyGuard skipped for tool '{tool_fqn}': no workspace_id available. "
                f"This may indicate a code path that bypasses workspace context. "
                f"Consider ensuring workspace_id is always provided."
            )

        tool_start_time = _utc_now()
        tool_call_id = str(uuid.uuid4())

        # Start trace node for tool execution
        trace_node_id = None
        if execution_id and workspace_id:
            try:
                trace_recorder = get_trace_recorder()
                # Get or create trace for this execution
                trace_id = self.execution_context.get("trace_id")
                if not trace_id:
                    trace_id = trace_recorder.create_trace(
                        workspace_id=workspace_id,
                        execution_id=execution_id,
                        user_id=self.execution_context.get("user_id"),
                    )
                    self.execution_context["trace_id"] = trace_id

                trace_node_id = trace_recorder.start_node(
                    trace_id=trace_id,
                    node_type=TraceNodeType.TOOL,
                    name=f"tool:{tool_fqn}",
                    input_data={
                        "tool_fqn": tool_fqn,
                        "tool_slot": tool_slot,
                        "parameters": {k: str(v)[:200] for k, v in kwargs.items()},
                    },
                    metadata={
                        "factory_cluster": factory_cluster,
                        "step_id": step_id,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to start trace node for tool execution: {e}")

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
            # Unsplash tools are provided by cloud capability pack
            # They should be called via capability registry (e.g., "unsplash.unsplash_search_photos")
            # If tool_fqn is "unsplash.xxx", it should be handled by capability registry

            normalized_kwargs = kwargs.copy()
            # Parameter normalization: convert common incorrect parameter names to correct ones
            if tool_fqn == "filesystem_write_file" and "path" in normalized_kwargs and "file_path" not in normalized_kwargs:
                normalized_kwargs["file_path"] = normalized_kwargs.pop("path")
                logger.debug(f"Normalized parameter 'path' -> 'file_path' for {tool_fqn}")

            # Normalize core_llm.structured_extract parameters
            if tool_fqn == "core_llm.structured_extract":
                if "input" in normalized_kwargs and "text" not in normalized_kwargs:
                    normalized_kwargs["text"] = normalized_kwargs.pop("input")
                    logger.debug(f"Normalized parameter 'input' -> 'text' for {tool_fqn}")
                if "schema" in normalized_kwargs and "schema_description" not in normalized_kwargs:
                    normalized_kwargs["schema_description"] = normalized_kwargs.pop("schema")
                    logger.debug(f"Normalized parameter 'schema' -> 'schema_description' for {tool_fqn}")

            if tool_fqn.startswith("sandbox."):
                execution_sandbox_id = self.execution_context.get("sandbox_id")
                execution_workspace_id = workspace_id or self.execution_context.get("workspace_id")
                if execution_sandbox_id and execution_workspace_id:
                    if "sandbox_id" not in normalized_kwargs:
                        normalized_kwargs["sandbox_id"] = execution_sandbox_id
                    if "workspace_id" not in normalized_kwargs:
                        normalized_kwargs["workspace_id"] = execution_workspace_id
                    logger.debug(f"Auto-injected sandbox_id={execution_sandbox_id} and workspace_id={execution_workspace_id} for {tool_fqn}")

            # Auto-inject workspace_id for capability tools that need it
            # (unsplash tools are cloud capability tools, handled via capability registry)
            if tool_fqn and "." in tool_fqn:
                capability, tool = tool_fqn.split(".", 1)
                execution_workspace_id = workspace_id or self.execution_context.get("workspace_id")
                if execution_workspace_id and "workspace_id" not in normalized_kwargs:
                    normalized_kwargs["workspace_id"] = execution_workspace_id
                    logger.debug(f"Auto-injected workspace_id={execution_workspace_id} for {tool_fqn}")

            result = await execute_tool(tool_fqn, **normalized_kwargs)

            # Integrate tool result → WorldState
            try:
                from backend.app.core.state.state_integration import StateIntegrationAdapter
                state_adapter = StateIntegrationAdapter()
                world_entry = state_adapter.tool_result_to_world_state(
                    workspace_id=workspace_id or "",
                    tool_id=tool_fqn,
                    tool_slot=tool_slot,
                    result=result,
                    execution_id=execution_id,
                    metadata={
                        "duration_ms": int((_utc_now() - tool_start_time).total_seconds() * 1000),
                        "step_id": step_id,
                    }
                )
                logger.debug(f"PlaybookToolExecutor: Converted tool result to WorldStateEntry (entry_id={world_entry.entry_id})")
            except Exception as e:
                logger.warning(f"Failed to integrate tool result to WorldState: {e}", exc_info=True)

            tool_end_time = _utc_now()
            duration_ms = int((tool_end_time - tool_start_time).total_seconds() * 1000)

            # End trace node for tool execution
            if trace_node_id and execution_id and workspace_id:
                try:
                    trace_recorder = get_trace_recorder()
                    trace_id = self.execution_context.get("trace_id")
                    if trace_id:
                        trace_recorder.end_node(
                            trace_id=trace_id,
                            node_id=trace_node_id,
                            status=TraceStatus.SUCCESS,
                            output_data={"result": str(result)[:1000] if result else None},
                            latency_ms=duration_ms,
                        )
                except Exception as e:
                    logger.warning(f"Failed to end trace node for tool execution: {e}")

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

                # Emit TOOL_RESULT event (ReAct: Observe)
                try:
                    tool_result_event = MindEvent(
                        id=str(uuid.uuid4()),
                        timestamp=tool_end_time,
                        actor=EventActor.AGENT,
                        channel="playbook",
                        profile_id=profile_id,
                        project_id=project_id,
                        workspace_id=workspace_id,
                        event_type=EventType.TOOL_RESULT,
                        payload={
                            "tool_fqn": tool_fqn,
                            "tool_call_id": tool_call_id,
                            "execution_id": execution_id,
                            "step_id": step_id,
                            "status": "completed",
                            "result_summary": str(result)[:500] if result else None,  # Truncate for event payload
                            "duration_seconds": (tool_end_time - tool_start_time).total_seconds(),
                            "has_changeset": "_changeset_id" in result if isinstance(result, dict) else False,
                            "changeset_id": result.get("_changeset_id") if isinstance(result, dict) else None,
                        },
                        entity_ids=[project_id] if project_id else [],
                        metadata={
                            "factory_cluster": factory_cluster,
                            "tool_params_summary": {k: str(v)[:50] for k, v in list(kwargs.items())[:5] if k != "project_id"},
                        }
                    )
                    self.store.create_event(tool_result_event)
                except Exception as e:
                    logger.warning(f"Failed to record tool result event: {e}")

            # Integrate with ChangeSet pipeline for write operations
            try:
                from backend.app.services.changeset.changeset_pipeline import ChangeSetPipeline
                from backend.app.models.playbook import ToolPolicy

                # Check if this is a write operation (based on tool_policy or tool_id)
                is_write_operation = (
                    tool_policy and hasattr(tool_policy, 'risk_level') and tool_policy.risk_level in ['write', 'publish']
                ) or (
                    tool_fqn and any(keyword in tool_fqn.lower() for keyword in ['write', 'update', 'create', 'delete', 'publish', 'wordpress', 'wp'])
                )

                if is_write_operation and workspace_id:
                    pipeline = ChangeSetPipeline(store=self.store)
                    changeset = await pipeline.create_and_apply(
                        workspace_id=workspace_id,
                        tool_id=tool_fqn,
                        tool_slot=tool_slot,
                        result=result,
                        execution_id=execution_id,
                        sandbox_type="web_page" if "wordpress" in tool_fqn.lower() or "wp" in tool_fqn.lower() else "project_repo",
                        auto_create_rollback=True
                    )
                    logger.info(f"PlaybookToolExecutor: Created changeset {changeset.changeset_id} for write operation {tool_fqn}")
                    # Store changeset_id in result metadata for later promotion
                    if isinstance(result, dict):
                        result["_changeset_id"] = changeset.changeset_id
                        result["_preview_url"] = changeset.preview_url
            except Exception as e:
                logger.warning(f"PlaybookToolExecutor: Failed to integrate with ChangeSet pipeline: {e}", exc_info=True)

            return result

        except Exception as e:
            tool_end_time = _utc_now()
            duration_ms = int((tool_end_time - tool_start_time).total_seconds() * 1000)

            # End trace node for failed tool execution
            if trace_node_id and execution_id and workspace_id:
                try:
                    trace_recorder = get_trace_recorder()
                    trace_id = self.execution_context.get("trace_id")
                    if trace_id:
                        import traceback
                        trace_recorder.end_node(
                            trace_id=trace_id,
                            node_id=trace_node_id,
                            status=TraceStatus.FAILED,
                            error_message=str(e)[:500],
                            error_stack=traceback.format_exc(),
                            latency_ms=duration_ms,
                        )
                except Exception as e2:
                    logger.warning(f"Failed to end trace node for failed tool execution: {e2}")

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

        # Phase 2: Set execution_id and trace_id in execution_context for orchestrator fallback lookup
        if execution_id:
            self.execution_context["execution_id"] = execution_id
            # Use execution_id as trace_id if not set (for orchestrator fallback)
            if "trace_id" not in self.execution_context:
                self.execution_context["trace_id"] = execution_id

        # Load runtime profile and get LoopBudget (Phase 2)
        effective_workspace_id = workspace_id or self.execution_context.get("workspace_id")
        loop_budget_max_iterations = max_iterations  # Default fallback
        loop_budget_max_tool_calls = None  # No limit by default

        if effective_workspace_id:
            try:
                profile_store = WorkspaceRuntimeProfileStore(db_path=self.store.db_path)
                runtime_profile = profile_store.get_runtime_profile(effective_workspace_id)
                if runtime_profile:
                    runtime_profile.ensure_phase2_fields()
                    loop_budget = runtime_profile.loop_budget
                    loop_budget_max_iterations = min(max_iterations, loop_budget.max_iterations)
                    loop_budget_max_tool_calls = loop_budget.max_tool_calls
                    logger.debug(f"Using LoopBudget: max_iterations={loop_budget_max_iterations}, max_tool_calls={loop_budget_max_tool_calls}")
            except Exception as e:
                logger.debug(f"Failed to load runtime profile for LoopBudget: {e}")

        max_tool_iterations = loop_budget_max_iterations
        tool_iteration = 0
        tool_call_count = 0  # Track total tool calls for max_tool_calls check
        used_tools = []
        current_response = assistant_response
        format_retry_count = 0
        max_format_retries = 2  # Max retries for format errors

        while tool_iteration < max_tool_iterations:
            # Parse tool calls from current assistant response
            logger.debug(f"PlaybookToolExecutor: Parsing tool calls from response (length={len(current_response) if current_response else 0})")
            tool_calls = conv_manager.parse_tool_calls_from_response(current_response)

            if not tool_calls:
                # Log response preview for debugging (first 500 chars)
                logger.info(f"PlaybookToolExecutor: No tool calls found in iteration {tool_iteration + 1}, "
                           f"response preview (first 500 chars):\n{current_response[:500] if current_response else 'None'}")
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

                # In auto_execute mode, be more persistent - prompt LLM to continue if we haven't reached max iterations
                if conv_manager.auto_execute and tool_iteration < max_tool_iterations - 1:
                    logger.info(f"PlaybookToolExecutor: Auto-execute mode - no tool calls found but prompting LLM to continue (iteration {tool_iteration + 1}/{max_tool_iterations})")
                    # Add a prompt to continue executing
                    continue_prompt = (
                        "**⚡ AUTO-EXECUTE MODE: You must continue executing the next steps in the SOP.**\n"
                        "- Review the conversation history and tool results above\n"
                        "- Check the SOP for the next required tool to call\n"
                        "- Immediately call the next tool using the correct JSON format\n"
                        "- Do NOT stop or provide explanations without calling tools\n"
                        "- Continue until all SOP phases are complete\n"
                    )
                    conv_manager.conversation_history.append({
                        "role": "system",
                        "content": continue_prompt
                    })
                    # Get LLM response again
                    messages = await conv_manager.get_messages_for_llm()
                    current_response = await provider.chat_completion(messages, model=model_name if model_name else None)
                    conv_manager.add_assistant_message(current_response)
                    tool_iteration += 1
                    continue  # Try parsing again

                logger.info(f"PlaybookToolExecutor: No tool calls found in iteration {tool_iteration + 1}, exiting loop")
                break  # No tool calls found, exit loop

            # Reset format retry counter on successful parse
            format_retry_count = 0
            logger.info(f"PlaybookToolExecutor: Found {len(tool_calls)} tool call(s) in iteration {tool_iteration + 1}")

            # Check max_tool_calls limit (Phase 2 LoopBudget)
            if loop_budget_max_tool_calls is not None:
                remaining_tool_calls = loop_budget_max_tool_calls - tool_call_count
                if remaining_tool_calls <= 0:
                    logger.warning(
                        f"LoopBudget: Tool call limit reached ({loop_budget_max_tool_calls}). "
                        f"Stopping tool execution loop."
                    )
                    break
                if len(tool_calls) > remaining_tool_calls:
                    logger.warning(
                        f"LoopBudget: Limiting tool calls in this iteration from {len(tool_calls)} to {remaining_tool_calls}"
                    )
                    tool_calls = tool_calls[:remaining_tool_calls]

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
                        # Prepare execution kwargs - remove workspace_id and project_id from kwargs if present
                        # They are passed as method parameters for slot resolution, not in kwargs
                        execution_kwargs = {k: v for k, v in parameters.items() if k not in ["workspace_id", "project_id"]}
                        result = await self.execute_tool(
                            tool_slot=tool_slot,
                            tool_policy=tool_policy,
                            profile_id=profile_id,
                            workspace_id=conv_manager.workspace_id,
                            project_id=conv_manager.project_id,
                            execution_id=execution_id,
                            step_id=None,  # Will be set when step event is created
                            **execution_kwargs
                        )
                        display_name = tool_slot
                    else:
                        logger.info(f"PlaybookToolExecutor: Executing tool {tool_name} with parameters: {list(parameters.keys())}")
                        # Prepare execution kwargs
                        execution_kwargs = parameters.copy()
                        # workspace_id is not a method parameter for direct tool calls, only for slot resolution
                        # So we keep it in kwargs if present, or add it if the tool needs it
                        if "workspace_id" not in execution_kwargs and conv_manager.workspace_id:
                            execution_kwargs["workspace_id"] = conv_manager.workspace_id
                        result = await self.execute_tool(
                            tool_fqn=tool_name,
                            profile_id=profile_id,
                            execution_id=execution_id,
                            step_id=None,  # Will be set when step event is created
                            **execution_kwargs
                        )
                        display_name = tool_name

                    tool_results.append({
                        "tool_name": display_name,
                        "tool_slot": tool_slot if tool_slot else None,
                        "result": result,
                        "success": True
                    })
                    used_tools.append(display_name)
                    tool_call_count += 1  # Increment tool call count for LoopBudget

                    logger.info(f"PlaybookToolExecutor: Tool {display_name} executed successfully (call #{tool_call_count})")

                    # Check max_tool_calls limit after each call (Phase 2 LoopBudget)
                    if loop_budget_max_tool_calls is not None and tool_call_count >= loop_budget_max_tool_calls:
                        logger.warning(
                            f"LoopBudget: Tool call limit reached ({loop_budget_max_tool_calls}). "
                            f"Stopping tool execution loop."
                        )
                        break

                except Exception as e:
                    error_msg = str(e)[:500]
                    display_name = tool_slot if tool_slot else tool_name
                    logger.error(f"PlaybookToolExecutor: Tool {display_name} execution failed: {e}", exc_info=True)

                    # Enhanced error message with tool name suggestions
                    enhanced_error = error_msg
                    if "not found" in error_msg.lower() and tool_name:
                        logger.info(f"PlaybookToolExecutor: Tool '{tool_name}' not found, attempting to find suggestions...")
                        # Try to find similar tool names
                        suggestions = self._suggest_tool_names(tool_name, conv_manager.workspace_id)
                        logger.info(f"PlaybookToolExecutor: Found {len(suggestions)} suggestions for '{tool_name}'")
                        if suggestions:
                            enhanced_error = (
                                f"Tool '{tool_name}' not found.\n"
                                f"**Did you mean one of these?**\n"
                            )
                            for i, suggestion in enumerate(suggestions[:5], 1):
                                enhanced_error += f"{i}. `{suggestion}`\n"
                            enhanced_error += f"\nPlease retry with the correct tool name from the list above."
                        else:
                            # Dynamically find related tools based on attempted name
                            logger.info(f"PlaybookToolExecutor: No suggestions found, trying to find related tools for '{tool_name}'...")
                            related_tools = self._find_related_tools(tool_name, conv_manager.workspace_id)
                            logger.info(f"PlaybookToolExecutor: Found {len(related_tools)} related tools for '{tool_name}'")
                            if related_tools:
                                enhanced_error = (
                                    f"Tool '{tool_name}' not found.\n"
                                    f"**Related tools you might want to use:**\n"
                                )
                                for i, tool in enumerate(related_tools[:5], 1):
                                    enhanced_error += f"{i}. `{tool}`\n"
                                enhanced_error += f"\nPlease check the available tools list and use the exact tool name."
                            else:
                                logger.warning(f"PlaybookToolExecutor: No suggestions or related tools found for '{tool_name}'")
                                enhanced_error = (
                                    f"Tool '{tool_name}' not found.\n"
                                    f"Please check the available tools list and use the exact tool name."
                                )
                    elif tool_slot and ("not configured" in error_msg.lower() or "not found" in error_msg.lower()):
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
            messages = await conv_manager.get_messages_for_llm()
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

