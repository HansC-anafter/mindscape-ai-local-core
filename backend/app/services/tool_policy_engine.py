"""
Tool Policy Engine

Validates tool execution against policy constraints.
"""

import logging
import re
from typing import Optional, List

from backend.app.models.playbook import ToolPolicy

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
        workspace_id: Optional[str] = None
    ) -> bool:
        """
        Check if tool execution conforms to policy

        Args:
            tool_id: Concrete tool ID to check
            policy: ToolPolicy instance (if None, no policy restrictions)
            workspace_id: Optional workspace ID (for future workspace-specific policies)

        Returns:
            True if tool conforms to policy

        Raises:
            PolicyViolationError: If tool violates policy
        """
        if not policy:
            # No policy = allow all (backward compatibility)
            return True

        # Check allowed tool patterns
        if policy.allowed_tool_patterns:
            if not self._matches_patterns(tool_id, policy.allowed_tool_patterns):
                raise PolicyViolationError(
                    f"Tool '{tool_id}' does not match allowed patterns: {policy.allowed_tool_patterns}"
                )

        # Check allowed slots (if specified, tool must come from one of these slots)
        # Note: This check is typically done at slot resolution time, not here
        # But we can validate if tool_id was resolved from an allowed slot

        # Risk level and environment checks are typically done at runtime
        # based on the tool's actual operations, not just the tool_id
        # For now, we just log these for future implementation

        logger.debug(f"Tool '{tool_id}' passed policy checks: risk={policy.risk_level}, env={policy.env}")
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

