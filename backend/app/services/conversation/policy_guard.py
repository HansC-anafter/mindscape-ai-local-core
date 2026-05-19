"""Policy guard facade for runtime tool call enforcement."""

from typing import Any, Dict, Optional

from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile
from backend.app.services.conversation.policy_guard_core import (
    PolicyCheckResult,
    build_proposed_action,
    check_tool_call as check_tool_call_helper,
    record_policy_check_event,
    utc_now as _utc_now,
)
from backend.app.services.tool_policy_resolver import ToolPolicyResolver
from backend.app.services.tool_registry import ToolRegistryService


class PolicyGuard:
    """Server-side Runtime Profile policy guard."""

    def __init__(
        self,
        strict_mode: bool = True,
        tool_registry: Optional[ToolRegistryService] = None,
        tool_policy_resolver: Optional[ToolPolicyResolver] = None,
    ):
        self.strict_mode = strict_mode
        if tool_policy_resolver:
            self.resolver = tool_policy_resolver
        elif tool_registry:
            self.resolver = ToolPolicyResolver(tool_registry)
        else:
            self.resolver = None

    def check_tool_call(
        self,
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
        return check_tool_call_helper(
            guard=self,
            tool_id=tool_id,
            runtime_profile=runtime_profile,
            tool_call_params=tool_call_params,
            tool_registry=tool_registry,
            execution_id=execution_id,
            previous_tool_id=previous_tool_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )

    def _build_proposed_action(
        self,
        tool_id: str,
        tool_call_params: Dict[str, Any],
        risk_class: str,
    ) -> Dict[str, Any]:
        return build_proposed_action(
            tool_id=tool_id,
            tool_call_params=tool_call_params,
            risk_class=risk_class,
        )

    def _record_policy_check_event(
        self,
        tool_id: str,
        capability_code: Optional[str],
        risk_class: Optional[str],
        result: PolicyCheckResult,
        execution_id: Optional[str],
        workspace_id: Optional[str],
        profile_id: Optional[str],
        event_store: Optional[Any],
    ):
        return record_policy_check_event(
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            result=result,
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            event_store=event_store,
        )
