"""
Tool Policy Resolver

Resolves tool_id to capability_code and risk_class for Runtime Profile policy enforcement.
Includes fallback logic and caching.
"""

from typing import Optional, Dict
from dataclasses import dataclass
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.models.tool_registry import RegisteredTool
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolPolicyInfo:
    """Tool policy information for Runtime Profile enforcement"""
    tool_id: str
    capability_code: str
    risk_class: str
    tool_info: Optional[RegisteredTool] = None


class ToolPolicyResolver:
    """
    Tool Policy Resolver - 解析 tool_id → capability_code / risk_class

    Features:
    - Fallback logic (uses effective_capability_code / effective_risk_class)
    - Caching (optional, for performance)
    - Handles missing fields gracefully
    """

    def __init__(self, tool_registry: ToolRegistryService, cache: Optional[Dict[str, ToolPolicyInfo]] = None):
        """
        Initialize ToolPolicyResolver

        Args:
            tool_registry: ToolRegistryService instance
            cache: Optional cache dict (keyed by tool_id)
        """
        self.tool_registry = tool_registry
        self.cache = cache or {}

    def resolve_policy_info(self, tool_id: str) -> Optional[ToolPolicyInfo]:
        """
        Resolve tool_id to policy information (capability_code, risk_class)

        Args:
            tool_id: Tool ID to resolve

        Returns:
            ToolPolicyInfo or None if tool not found
        """
        # Check cache first
        if tool_id in self.cache:
            return self.cache[tool_id]

        # Get tool from registry
        tool = self.tool_registry.get_tool(tool_id)
        if not tool:
            logger.warning(f"Tool {tool_id} not found in registry")
            return None

        # Resolve capability_code (with fallback)
        capability_code = tool.effective_capability_code
        if not capability_code:
            # Fallback: infer from tool_id (e.g., "wp.my-site.post.create_draft" -> "wp")
            parts = tool_id.split(".")
            capability_code = parts[0] if parts else "unknown"
            logger.warning(f"Tool {tool_id} missing capability_code, inferred: {capability_code}")

        # Resolve risk_class (with fallback)
        risk_class = tool.effective_risk_class

        # Create policy info
        policy_info = ToolPolicyInfo(
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            tool_info=tool
        )

        # Cache result
        self.cache[tool_id] = policy_info

        return policy_info

    def clear_cache(self):
        """Clear the cache"""
        self.cache.clear()

