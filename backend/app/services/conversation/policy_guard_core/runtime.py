"""Runtime decision tree for policy guard checks."""

import logging
from typing import Any, Dict, Optional

from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile
from backend.app.services.conversation.policy_guard_core import messages
from backend.app.services.conversation.policy_guard_core.models import PolicyCheckResult
from backend.app.services.tool_policy_resolver import ToolPolicyResolver
from backend.app.services.tool_registry import ToolRegistryService

logger = logging.getLogger(__name__)


def get_chain_tracker_for_execution(execution_id: str):
    """Load the tool call chain tracker lazily."""
    from backend.app.services.conversation.tool_call_chain_tracker import (
        get_chain_tracker,
    )

    return get_chain_tracker(execution_id)


def ensure_resolver(guard, tool_registry: ToolRegistryService):
    """Ensure the guard has a resolver."""
    if not hasattr(guard, "resolver") or guard.resolver is None:
        if tool_registry is None:
            raise ValueError(
                "PolicyGuard requires either tool_registry in __init__ or "
                "tool_registry in check_tool_call"
            )
        guard.resolver = ToolPolicyResolver(tool_registry)
    return guard.resolver


def record_and_return(
    *,
    guard,
    tool_id: str,
    capability_code: Optional[str],
    risk_class: Optional[str],
    result: PolicyCheckResult,
    execution_id: Optional[str],
    workspace_id: Optional[str],
    profile_id: Optional[str],
    event_store: Optional[Any],
) -> PolicyCheckResult:
    guard._record_policy_check_event(
        tool_id=tool_id,
        capability_code=capability_code,
        risk_class=risk_class,
        result=result,
        execution_id=execution_id,
        workspace_id=workspace_id,
        profile_id=profile_id,
        event_store=event_store,
    )
    return result


def check_tool_call(
    *,
    guard,
    tool_id: str,
    runtime_profile: WorkspaceRuntimeProfile,
    tool_call_params: Dict[str, Any],
    tool_registry: ToolRegistryService,
    execution_id: Optional[str] = None,
    previous_tool_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    event_store: Optional[Any] = None,
) -> PolicyCheckResult:
    """Check whether a tool call complies with Runtime Profile policy."""
    resolver = ensure_resolver(guard, tool_registry)
    policy_info = resolver.resolve_policy_info(tool_id)

    if not policy_info:
        if guard.strict_mode:
            result = PolicyCheckResult(
                allowed=False,
                reason="Tool not found in registry",
                user_message=messages.tool_not_found_blocked(),
            )
        else:
            logger.warning("Tool %s not found, allowing with warning", tool_id)
            result = PolicyCheckResult(
                allowed=True,
                requires_approval=True,
                reason="Tool not found in registry",
                user_message=messages.tool_not_found_allowed(),
            )
        return record_and_return(
            guard=guard,
            tool_id=tool_id,
            capability_code=None,
            risk_class=None,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )

    capability_code = policy_info.capability_code
    risk_class = policy_info.risk_class

    if not capability_code or capability_code == "unknown":
        if guard.strict_mode:
            result = PolicyCheckResult(
                allowed=False,
                reason=f"Tool {tool_id} missing capability_code",
                user_message=messages.missing_capability_blocked(tool_id),
            )
        else:
            logger.warning(
                "Tool %s missing capability_code, allowing with approval",
                tool_id,
            )
            result = PolicyCheckResult(
                allowed=True,
                requires_approval=True,
                reason=f"Tool {tool_id} missing capability_code",
                user_message=messages.missing_capability_allowed(tool_id),
            )
        return record_and_return(
            guard=guard,
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )

    tool_policy = runtime_profile.tool_policy

    if tool_policy.denylist and capability_code in tool_policy.denylist:
        result = PolicyCheckResult(
            allowed=False,
            reason=f"Capability {capability_code} is in denylist",
            user_message=messages.capability_denied(capability_code),
        )
        return record_and_return(
            guard=guard,
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )

    if tool_policy.allowlist and capability_code not in tool_policy.allowlist:
        result = PolicyCheckResult(
            allowed=False,
            reason=f"Capability {capability_code} is not in allowlist",
            user_message=messages.capability_not_allowed(capability_code),
        )
        return record_and_return(
            guard=guard,
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )

    if capability_code in tool_policy.require_approval_for_capabilities:
        result = PolicyCheckResult(
            allowed=True,
            requires_approval=True,
            proposed_action=guard._build_proposed_action(
                tool_id,
                tool_call_params,
                risk_class,
            ),
            reason=(
                f"Capability {capability_code} requires explicit approval "
                "(require_approval_for_capabilities)"
            ),
            user_message=messages.capability_requires_explicit_approval(
                capability_code
            ),
        )
        return record_and_return(
            guard=guard,
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )

    if execution_id and previous_tool_id:
        chain_tracker = get_chain_tracker_for_execution(execution_id)
        chain_length = chain_tracker.get_chain_length(previous_tool_id) + 1

        if chain_length > tool_policy.max_tool_call_chain:
            result = PolicyCheckResult(
                allowed=False,
                reason=(
                    f"Tool call chain length ({chain_length}) exceeds maximum "
                    f"({tool_policy.max_tool_call_chain})"
                ),
                user_message=messages.chain_too_long(
                    chain_length,
                    tool_policy.max_tool_call_chain,
                ),
            )
            return record_and_return(
                guard=guard,
                tool_id=tool_id,
                capability_code=capability_code,
                risk_class=risk_class,
                result=result,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                event_store=event_store,
            )

    confirmation_policy = runtime_profile.confirmation_policy

    if risk_class == "external_write" and confirmation_policy.confirm_external_write:
        result = PolicyCheckResult(
            allowed=True,
            requires_approval=True,
            proposed_action=guard._build_proposed_action(
                tool_id,
                tool_call_params,
                risk_class,
            ),
            reason=f"Tool {capability_code} requires approval (risk_class: {risk_class})",
            user_message=messages.risk_requires_confirmation(
                capability_code,
                risk_class,
            ),
        )
        return record_and_return(
            guard=guard,
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )

    if risk_class == "soft_write" and confirmation_policy.confirm_soft_write:
        result = PolicyCheckResult(
            allowed=True,
            requires_approval=True,
            proposed_action=guard._build_proposed_action(
                tool_id,
                tool_call_params,
                risk_class,
            ),
            reason=f"Tool {capability_code} requires approval (risk_class: {risk_class})",
            user_message=messages.risk_requires_confirmation(
                capability_code,
                risk_class,
            ),
        )
        return record_and_return(
            guard=guard,
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )

    if risk_class == "readonly" and confirmation_policy.auto_read:
        result = PolicyCheckResult(
            allowed=True,
            requires_approval=False,
            reason="Read-only operation, auto-allowed",
        )
        return record_and_return(
            guard=guard,
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )

    result = PolicyCheckResult(
        allowed=True,
        requires_approval=False,
        reason="No policy restrictions apply",
    )
    return record_and_return(
        guard=guard,
        tool_id=tool_id,
        capability_code=capability_code,
        risk_class=risk_class,
        result=result,
        execution_id=execution_id,
        workspace_id=workspace_id,
        profile_id=profile_id,
        event_store=event_store,
    )
