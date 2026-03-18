"""
Tool Policy Enforcer
Handles Runtime Profile PolicyGuard checks and Orchestrator loop budgeting.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ToolPolicyEnforcer:
    """Enforces Runtime Profile policies and LoopBudgets."""

    async def enforce(
        self,
        tool_fqn: str,
        kwargs: Dict[str, Any],
        workspace_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        execution_context: Optional[Dict[str, Any]] = None
    ):
        execution_context = execution_context or {}
        effective_workspace_id = workspace_id or execution_context.get("workspace_id")

        if effective_workspace_id:
            try:
                from backend.app.services.stores.workspace_runtime_profile_store import WorkspaceRuntimeProfileStore
                profile_store = WorkspaceRuntimeProfileStore()
                runtime_profile = await profile_store.get_runtime_profile(effective_workspace_id)

                if not runtime_profile:
                    runtime_profile = await profile_store.create_default_profile(effective_workspace_id)
                    logger.info(f"Created default runtime profile for workspace {effective_workspace_id}")

                from backend.app.routes.core.tools.base import get_tool_registry
                tool_registry = get_tool_registry()

                from backend.app.services.stores.postgres.events_store import PostgresEventsStore
                event_store = PostgresEventsStore()

                from backend.app.services.conversation.policy_guard import PolicyGuard
                policy_guard = PolicyGuard(strict_mode=True, tool_registry=tool_registry)

                previous_tool_id = execution_context.get("last_tool_id")

                policy_result = policy_guard.check_tool_call(
                    tool_id=tool_fqn,
                    runtime_profile=runtime_profile,
                    tool_call_params=kwargs,
                    tool_registry=tool_registry,
                    execution_id=execution_id,
                    previous_tool_id=previous_tool_id,
                    workspace_id=effective_workspace_id,
                    profile_id=getattr(runtime_profile, "profile_id", None),
                    event_store=event_store,
                )

                if execution_id:
                    from backend.app.services.conversation.tool_call_chain_tracker import get_chain_tracker
                    chain_tracker = get_chain_tracker(execution_id)
                    chain_tracker.record_tool_call(tool_fqn, previous_tool_id)
                    execution_context["last_tool_id"] = tool_fqn

                    try:
                        from backend.app.services.orchestration.orchestrator_registry import get_orchestrator_registry
                        orchestrator_registry = get_orchestrator_registry()
                        orchestrator = orchestrator_registry.get(execution_id)

                        if not orchestrator:
                            trace_id = execution_context.get("trace_id")
                            message_id = execution_context.get("message_id")
                            fallback_keys = []
                            if trace_id: fallback_keys.append(trace_id)
                            if message_id: fallback_keys.append(message_id)

                            if fallback_keys:
                                orchestrator = orchestrator_registry.find_by_any_key(*fallback_keys)
                                if orchestrator:
                                    logger.info(f"OrchestratorRegistry: Found orchestrator using fallback key")

                            if not orchestrator:
                                orchestrator = orchestrator_registry.find_any()
                                if orchestrator:
                                    logger.warning(f"OrchestratorRegistry: Using 'find_any' fallback for execution_id={execution_id}.")

                            if not orchestrator:
                                logger.warning(f"OrchestratorRegistry: No orchestrator found for execution_id={execution_id}")

                        if orchestrator:
                            orchestrator.record_tool_call()
                            logger.debug(f"MultiAgentOrchestrator: Recorded tool call '{tool_fqn}'")
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

            except ValueError:
                raise
            except Exception as e:
                logger.warning(f"Failed to check Runtime Profile policy: {e}", exc_info=True)
        else:
            logger.warning(f"PolicyGuard skipped for tool '{tool_fqn}': no workspace_id available.")
