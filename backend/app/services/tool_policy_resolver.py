"""
Tool Policy Resolver

Resolves tool_id to capability_code and risk_class for Runtime Profile policy enforcement.
Includes fallback logic and caching.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.models.tool_registry import RegisteredTool
import logging

from backend.app.services.tool_list_service import get_tool_list_service

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
        if tool:
            policy_info = self._build_policy_info_from_registered_tool(tool_id, tool)
            self.cache[tool_id] = policy_info
            return policy_info

        policy_info = self._resolve_policy_info_from_tool_list(tool_id)
        if not policy_info:
            logger.warning(f"Tool {tool_id} not found in registry")
            return None

        self.cache[tool_id] = policy_info
        return policy_info

    def _build_policy_info_from_registered_tool(
        self, tool_id: str, tool: RegisteredTool
    ) -> ToolPolicyInfo:
        capability_code = tool.effective_capability_code
        if not capability_code or capability_code.strip() == "":
            parts = tool_id.split(".")
            capability_code = parts[0] if parts else "unknown"
            logger.warning(
                f"Tool {tool_id} missing capability_code (empty string), inferred: {capability_code}"
            )

        risk_class = tool.effective_risk_class
        if not risk_class or risk_class.strip() == "":
            risk_class = "unknown"
            logger.warning(
                f"Tool {tool_id} missing risk_class (empty string), using default: {risk_class}"
            )

        return ToolPolicyInfo(
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            tool_info=tool,
        )

    def _resolve_policy_info_from_tool_list(
        self, tool_id: str
    ) -> Optional[ToolPolicyInfo]:
        tool_info = get_tool_list_service().get_tool_by_id(tool_id)
        if not tool_info:
            return None

        capability_code = self._infer_capability_code(tool_id, tool_info.metadata or {})
        risk_class = self._infer_risk_class(tool_info.metadata or {})
        return ToolPolicyInfo(
            tool_id=tool_id,
            capability_code=capability_code,
            risk_class=risk_class,
            tool_info=None,
        )

    def _infer_capability_code(
        self, tool_id: str, metadata: Dict[str, Any]
    ) -> str:
        builtin_tool = metadata.get("tool")
        if builtin_tool and hasattr(builtin_tool, "metadata"):
            provider = getattr(builtin_tool.metadata, "provider", None)
            if provider:
                return str(provider)

        tool_meta = metadata.get("tool_info")
        if isinstance(tool_meta, dict):
            for candidate in (
                tool_meta.get("capability_code"),
                tool_meta.get("provider"),
            ):
                if candidate:
                    return str(candidate)
            nested = tool_meta.get("tool_info")
            if isinstance(nested, dict):
                for candidate in (
                    nested.get("capability_code"),
                    nested.get("provider"),
                ):
                    if candidate:
                        return str(candidate)

        if "." in tool_id:
            return tool_id.split(".", 1)[0]
        return tool_id.split("_", 1)[0] if "_" in tool_id else "unknown"

    def _infer_risk_class(self, metadata: Dict[str, Any]) -> str:
        builtin_tool = metadata.get("tool")
        if builtin_tool and hasattr(builtin_tool, "metadata"):
            return self._map_danger_level_to_risk_class(
                getattr(builtin_tool.metadata, "danger_level", None)
            )

        tool_meta = metadata.get("tool_info")
        if isinstance(tool_meta, dict):
            for candidate in (
                tool_meta.get("risk_class"),
                tool_meta.get("side_effect_level"),
                tool_meta.get("danger_level"),
            ):
                risk_class = self._normalize_risk_candidate(candidate)
                if risk_class:
                    return risk_class
            nested = tool_meta.get("tool_info")
            if isinstance(nested, dict):
                for candidate in (
                    nested.get("risk_class"),
                    nested.get("side_effect_level"),
                    nested.get("danger_level"),
                ):
                    risk_class = self._normalize_risk_candidate(candidate)
                    if risk_class:
                        return risk_class

        return "readonly"

    def _normalize_risk_candidate(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().lower()
        if not text:
            return None
        if text in {"readonly", "soft_write", "external_write", "destructive"}:
            return text
        return self._map_danger_level_to_risk_class(text)

    def _map_danger_level_to_risk_class(self, value: Any) -> str:
        level = str(value or "").strip().lower()
        if level in {"medium", "moderate"}:
            return "soft_write"
        if level in {"high", "critical", "danger"}:
            return "external_write"
        return "readonly"

    def clear_cache(self):
        """Clear the cache"""
        self.cache.clear()

