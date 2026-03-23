"""
Playbook Tool Executor Facade
Orchestrates the detached pipeline components (Normalization, Policy, Events, Loop)
"""
import logging
import uuid
from typing import Dict, List, Optional, Any, Callable, Awaitable, Tuple

from backend.app.shared.tool_executor import execute_tool as shared_execute_tool
from backend.app.services.conversation.workflow_tracker import WorkflowTracker

# Import extracted components
from .normalization import ToolParameterNormalizer
from .policy import ToolPolicyEnforcer
from .events import ToolEventReporter, _utc_now
from .loop import ToolExecutionLoop

logger = logging.getLogger(__name__)

class PlaybookToolExecutor:
    """Handles tool execution for Playbook runs, orchestrating the pipeline."""

    def __init__(self, store: Any, workflow_tracker: WorkflowTracker):
        self.store = store
        self.workflow_tracker = workflow_tracker
        self.execution_context: Dict[str, Any] = {}
        
        self.policy_enforcer = ToolPolicyEnforcer()
        self.event_reporter = ToolEventReporter(store, workflow_tracker)
        # Pass self.execute_tool bound method to the loop component
        self.loop_runner = ToolExecutionLoop(self.execute_tool, self.execution_context)

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
        **kwargs,
    ) -> Any:
        
        # 1. Slot Resolution
        if tool_slot:
            if not workspace_id:
                raise ValueError("workspace_id is required when using tool_slot")

            from backend.app.services.tool_slot_resolver import get_tool_slot_resolver, SlotNotFoundError
            from backend.app.services.tool_policy_engine import get_tool_policy_engine, PolicyViolationError

            resolver = get_tool_slot_resolver(store=self.store)
            try:
                resolved_tool_id = await resolver.resolve(
                    slot=tool_slot, workspace_id=workspace_id, project_id=project_id
                )
                tool_fqn = resolved_tool_id
                logger.info(f"Resolved tool slot '{tool_slot}' to tool '{tool_fqn}'")
            except SlotNotFoundError as e:
                logger.error(f"Failed to resolve tool slot '{tool_slot}': {e}")
                error_parts = [f"Tool slot '{tool_slot}' is not configured."]
                if hasattr(e, "suggestion") and e.suggestion:
                    error_parts.append(f"\n{e.suggestion}")
                config_level = "project" if project_id else "workspace"
                error_parts.append(
                    f"\nTo configure this slot:\n"
                    f"1. Use the API endpoint: POST /api/v1/tool-slots\n"
                    f"2. Or configure it in the {config_level} settings\n"
                    f"3. Required fields: slot='{tool_slot}', tool_id=<concrete_tool_id>"
                )
                if hasattr(e, "available_slots") and e.available_slots:
                    error_parts.append(f"\nNote: You can also use an existing slot directly, or use a concrete tool_id instead of a slot.")
                raise ValueError("\n".join(error_parts))

            if tool_policy:
                policy_engine = get_tool_policy_engine()
                try:
                    policy_engine.check(tool_id=tool_fqn, policy=tool_policy, workspace_id=workspace_id)
                except PolicyViolationError as e:
                    logger.error(f"Tool '{tool_fqn}' violates policy: {e}")
                    policy_info = []
                    policy_info.append(f"Policy constraints:")
                    if tool_policy.risk_level: policy_info.append(f"  - Risk level: {tool_policy.risk_level}")
                    if tool_policy.env: policy_info.append(f"  - Environment: {tool_policy.env}")
                    if tool_policy.allowed_tool_patterns: policy_info.append(f"  - Allowed patterns: {', '.join(tool_policy.allowed_tool_patterns)}")
                    error_msg = f"Tool execution blocked by policy: {str(e)}"
                    if policy_info: error_msg += f"\n\n{chr(10).join(policy_info)}"
                    error_msg += f"\n\nTo resolve this:\n1. Check if the tool '{tool_fqn}' matches the policy constraints\n2. Update the tool slot mapping to use a different tool\n3. Or adjust the policy in the playbook definition"
                    raise ValueError(error_msg)
        elif not tool_fqn:
            raise ValueError("Either tool_fqn or tool_slot must be provided")

        # 2. Phase 2 PolicyGuard Enforcement
        await self.policy_enforcer.enforce(
            tool_fqn=tool_fqn, 
            kwargs=kwargs, 
            workspace_id=workspace_id, 
            execution_id=execution_id, 
            execution_context=self.execution_context
        )

        tool_start_time = _utc_now()

        # 3. Resolve Factory Cluster
        if not factory_cluster:
            default_cluster = self.execution_context.get("default_cluster")
            if default_cluster:
                factory_cluster = default_cluster
            else:
                connection_id = None
                if "." in tool_fqn:
                    parts = tool_fqn.split(".", 1)
                    if len(parts) >= 1:
                        potential_connection_id = parts[0]
                        if potential_connection_id and not potential_connection_id.startswith(("filesystem_", "sandbox.", "capability.")):
                            connection_id = potential_connection_id
                
                if connection_id:
                    try:
                        from backend.app.services.stores.postgres.connections_store import PostgresConnectionsStore
                        connections_store = PostgresConnectionsStore()
                        connection = connections_store.get_connection(connection_id)
                        if connection and connection.is_remote:
                            factory_cluster = connection.connection_type or "remote"
                        elif connection:
                            factory_cluster = "local_mcp"
                        else:
                            factory_cluster = "local_mcp"
                    except Exception as e:
                        factory_cluster = "local_mcp"
                else:
                    if tool_fqn.startswith(("filesystem_", "sandbox.", "local_")) or "mcp" in tool_fqn.lower():
                        factory_cluster = "local_mcp"
                    else:
                        factory_cluster = "local_mcp"

        # 4. Tracing and Start Events
        trace_node_id = self.event_reporter.start_trace_node(
            tool_fqn, kwargs, tool_slot, factory_cluster, step_id, execution_id, workspace_id, self.execution_context
        )
        tool_call = self.event_reporter.record_tool_start(tool_fqn, kwargs, factory_cluster, step_id, execution_id)
        tool_call_id = str(uuid.uuid4())

        # 5. Parameter Normalization
        normalized_kwargs = ToolParameterNormalizer.normalize(
            tool_fqn, kwargs, self.execution_context, workspace_id
        )

        try:
            # 6. Actual Tool Execution
            result = await shared_execute_tool(tool_fqn, **normalized_kwargs)

            # 7. WorldState Integration
            self.event_reporter.integrate_state(
                tool_fqn, tool_slot, result, execution_id, workspace_id, step_id, tool_start_time
            )

            tool_end_time = _utc_now()
            duration_ms = int((tool_end_time - tool_start_time).total_seconds() * 1000)

            # 8. Post-Execution Events
            self.event_reporter.end_trace_node(trace_node_id, result, duration_ms, execution_id, workspace_id, self.execution_context)
            self.event_reporter.record_tool_complete(tool_call, result, execution_id)
            self.event_reporter.emit_mind_event(
                tool_fqn, kwargs, factory_cluster, tool_call_id, result, 
                duration_ms / 1000.0, profile_id, project_id, workspace_id, execution_id, step_id
            )

        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            tool_end_time = _utc_now()
            duration_ms = int((tool_end_time - tool_start_time).total_seconds() * 1000)
            
            self.event_reporter.end_trace_node(trace_node_id, str(e), duration_ms, execution_id, workspace_id, self.execution_context)
            self.event_reporter.record_tool_complete(tool_call, f"Error: {str(e)}", execution_id)
            raise

        return result

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
        
        return await self.loop_runner.execute_tool_loop(
            conv_manager, assistant_response, execution_id, profile_id, provider, 
            model_name, max_iterations, workspace_id, sandbox_id
        )
