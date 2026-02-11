"""
Tool Policy Engine

Validates tool execution against policy constraints.
"""

import logging
import re
from typing import Optional, List
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from backend.app.models.playbook import ToolPolicy
from backend.app.core.trace import get_trace_recorder, TraceNodeType, TraceStatus

logger = logging.getLogger(__name__)


class PolicyViolationError(Exception):
    """Raised when tool execution violates policy"""
    pass


class ToolPolicyEngine:
    """
    Validates tool execution against policy constraints

    Policy checks include:
    - Risk level (read vs write)
    - Environment (sandbox vs production)
    - Preview requirements
    - Tool pattern matching
    """

    def __init__(self):
        """Initialize policy engine"""
        pass

    def check(
        self,
        tool_id: str,
        policy: Optional[ToolPolicy],
        workspace_id: Optional[str] = None,
        execution_id: Optional[str] = None
    ) -> bool:
        """
        Check if tool execution conforms to policy

        Args:
            tool_id: Concrete tool ID to check
            policy: ToolPolicy instance (if None, no policy restrictions)
            workspace_id: Optional workspace ID (for future workspace-specific policies)
            execution_id: Optional execution ID (for trace recording)

        Returns:
            True if tool conforms to policy

        Raises:
            PolicyViolationError: If tool violates policy
        """
        # Start trace node for policy decision
        trace_node_id = None
        trace_id = None
        if execution_id and workspace_id:
            try:
                trace_recorder = get_trace_recorder()
                # Try to get existing trace or create new one
                trace_id = trace_recorder.create_trace(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                )
                trace_node_id = trace_recorder.start_node(
                    trace_id=trace_id,
                    node_type=TraceNodeType.POLICY,
                    name=f"policy:tool_check:{tool_id}",
                    input_data={
                        "tool_id": tool_id,
                        "policy": policy.dict() if policy and hasattr(policy, 'dict') else str(policy),
                    },
                    metadata={
                        "workspace_id": workspace_id,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to start trace node for policy check: {e}")

        if not policy:
            # No policy = allow all (backward compatibility)
            if trace_node_id and trace_id:
                try:
                    trace_recorder = get_trace_recorder()
                    trace_recorder.end_node(
                        trace_id=trace_id,
                        node_id=trace_node_id,
                        status=TraceStatus.SUCCESS,
                        output_data={"result": "approved", "reason": "No policy restrictions"},
                    )
                except Exception as e:
                    logger.warning(f"Failed to end trace node for policy check: {e}")
            return True

        # Check allowed tool patterns
        if policy.allowed_tool_patterns:
            if not self._matches_patterns(tool_id, policy.allowed_tool_patterns):
                # Integrate policy decision → DecisionState (rejection)
                try:
                    from backend.app.core.state.state_integration import StateIntegrationAdapter
                    from backend.app.core.state.decision_state import DecisionType
                    state_adapter = StateIntegrationAdapter()
                    decision_state = state_adapter.policy_decision_to_decision_state(
                        workspace_id=workspace_id or "",
                        decision_id=f"policy_check_{tool_id}_{_utc_now().isoformat()}",
                        decision_type=DecisionType.POLICY_OVERRIDE,
                        decision_data={
                            "tool_id": tool_id,
                            "policy": policy.dict() if hasattr(policy, 'dict') else str(policy),
                            "result": "rejected",
                            "reason": f"Tool '{tool_id}' does not match allowed patterns: {policy.allowed_tool_patterns}"
                        },
                        policy_name=f"policy_tool_policy_engine",
                        reasoning=f"Tool pattern mismatch: {tool_id} not in {policy.allowed_tool_patterns}"
                    )
                    logger.debug(f"ToolPolicyEngine: Recorded policy rejection in DecisionState (decision_id={decision_state.decision_id})")
                except Exception as e:
                    logger.warning(f"Failed to integrate policy decision to DecisionState: {e}", exc_info=True)

                # End trace node for rejected policy check
                if trace_node_id and trace_id:
                    try:
                        trace_recorder = get_trace_recorder()
                        trace_recorder.end_node(
                            trace_id=trace_id,
                            node_id=trace_node_id,
                            status=TraceStatus.FAILED,
                            output_data={
                                "result": "rejected",
                                "reason": f"Tool '{tool_id}' does not match allowed patterns: {policy.allowed_tool_patterns}"
                            },
                            error_message=f"Tool '{tool_id}' does not match allowed patterns: {policy.allowed_tool_patterns}",
                        )
                    except Exception as e:
                        logger.warning(f"Failed to end trace node for rejected policy check: {e}")

                raise PolicyViolationError(
                    f"Tool '{tool_id}' does not match allowed patterns: {policy.allowed_tool_patterns}"
                )

        # Check allowed slots (if specified, tool must come from one of these slots)
        # Note: This check is typically done at slot resolution time, not here
        # But we can validate if tool_id was resolved from an allowed slot

        # Risk level and environment checks are typically done at runtime
        # based on the tool's actual operations, not just the tool_id
        # For now, we just log these for future implementation

        # Integrate policy decision → DecisionState (approval)
        try:
            from backend.app.core.state.state_integration import StateIntegrationAdapter
            from backend.app.core.state.decision_state import DecisionType
            from datetime import datetime, timezone
            state_adapter = StateIntegrationAdapter()
            decision_state = state_adapter.policy_decision_to_decision_state(
                workspace_id=workspace_id or "",
                decision_id=f"policy_check_{tool_id}_{_utc_now().isoformat()}",
                decision_type=DecisionType.POLICY_OVERRIDE,
                decision_data={
                    "tool_id": tool_id,
                    "policy": policy.dict() if hasattr(policy, 'dict') else str(policy),
                    "result": "approved",
                    "risk_level": policy.risk_level if hasattr(policy, 'risk_level') else None,
                    "env": policy.env if hasattr(policy, 'env') else None,
                },
                policy_name=f"policy_tool_policy_engine",
                reasoning=f"Tool '{tool_id}' passed policy checks"
            )
            logger.debug(f"ToolPolicyEngine: Recorded policy approval in DecisionState (decision_id={decision_state.decision_id})")
        except Exception as e:
            logger.warning(f"Failed to integrate policy decision to DecisionState: {e}", exc_info=True)

        logger.debug(f"Tool '{tool_id}' passed policy checks: risk={policy.risk_level}, env={policy.env}")

        # End trace node for approved policy check
        if trace_node_id and trace_id:
            try:
                trace_recorder = get_trace_recorder()
                trace_recorder.end_node(
                    trace_id=trace_id,
                    node_id=trace_node_id,
                    status=TraceStatus.SUCCESS,
                    output_data={
                        "result": "approved",
                        "reason": "Tool conforms to policy"
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to end trace node for approved policy check: {e}")

        return True

    def _matches_patterns(self, tool_id: str, patterns: List[str]) -> bool:
        """
        Check if tool_id matches any of the patterns

        Supports wildcards:
        - '*' matches any characters
        - '?' matches single character

        Args:
            tool_id: Tool ID to check
            patterns: List of pattern strings

        Returns:
            True if tool_id matches any pattern
        """
        for pattern in patterns:
            # Convert wildcard pattern to regex
            regex_pattern = pattern.replace('.', r'\.')  # Escape dots
            regex_pattern = regex_pattern.replace('*', '.*')  # * -> .*
            regex_pattern = regex_pattern.replace('?', '.')  # ? -> .
            regex_pattern = f"^{regex_pattern}$"  # Anchor to start and end

            if re.match(regex_pattern, tool_id):
                return True

        return False

    def check_risk_level(
        self,
        tool_id: str,
        operation_type: str,
        policy: Optional[ToolPolicy]
    ) -> bool:
        """
        Check if operation type conforms to policy risk level

        Args:
            tool_id: Tool ID
            operation_type: 'read' or 'write'
            policy: ToolPolicy instance

        Returns:
            True if operation is allowed

        Raises:
            PolicyViolationError: If operation violates risk level policy
        """
        if not policy:
            return True

        if policy.risk_level == "read" and operation_type == "write":
            raise PolicyViolationError(
                f"Tool '{tool_id}' attempted write operation, but policy only allows read operations"
            )

        return True

    def check_environment(
        self,
        tool_id: str,
        environment: str,
        policy: Optional[ToolPolicy]
    ) -> bool:
        """
        Check if environment conforms to policy

        Args:
            tool_id: Tool ID
            environment: 'sandbox' or 'production'
            policy: ToolPolicy instance

        Returns:
            True if environment is allowed

        Raises:
            PolicyViolationError: If environment violates policy
        """
        if not policy:
            return True

        if policy.env == "sandbox_only" and environment == "production":
            raise PolicyViolationError(
                f"Tool '{tool_id}' attempted production access, but policy only allows sandbox"
            )

        return True

    def requires_preview(
        self,
        tool_id: str,
        operation_type: str,
        policy: Optional[ToolPolicy]
    ) -> bool:
        """
        Check if operation requires preview before execution

        Args:
            tool_id: Tool ID
            operation_type: 'read' or 'write'
            policy: ToolPolicy instance

        Returns:
            True if preview is required
        """
        if not policy:
            return False

        if operation_type == "write" and policy.requires_preview:
            return True

        return False


# Global instance
_policy_engine_instance: Optional[ToolPolicyEngine] = None


def get_tool_policy_engine() -> ToolPolicyEngine:
    """
    Get global ToolPolicyEngine instance

    Returns:
        ToolPolicyEngine instance
    """
    global _policy_engine_instance
    if _policy_engine_instance is None:
        _policy_engine_instance = ToolPolicyEngine()
    return _policy_engine_instance

