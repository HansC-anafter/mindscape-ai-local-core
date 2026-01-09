"""
Parameter Mapping Strategy

Generic parameter name/format transformation strategy.
Supports configurable parameter mappings.

Responsibilities:
- Parameter name transformation (e.g., path -> file_path)
- Parameter format transformation (e.g., type conversion)
- Not responsible for:
  - Business-specific logic
  - Contract definition
"""

import logging
from typing import Dict, Any, Optional, List, Callable

from .base import ParameterAdaptationStrategy
from ..context import ExecutionContext
from ..contracts import ToolContract

logger = logging.getLogger(__name__)


class ParameterMappingStrategy(ParameterAdaptationStrategy):
    """
    Generic parameter mapping strategy

    Supports configurable parameter name and format transformations.
    Mappings are defined externally (not hardcoded).
    """

    def __init__(self, mappings: Optional[Dict[str, Dict[str, str]]] = None):
        """
        Initialize parameter mapping strategy

        Args:
            mappings: Optional mapping configuration
                Format: {tool_name: {old_name: new_name}}
        """
        self.mappings = mappings or {}
        self._register_default_mappings()

    def _register_default_mappings(self):
        """Register default parameter mappings (generic patterns only)"""
        # Generic filesystem tool mappings (not business-specific)
        self.mappings.setdefault("filesystem_read_file", {"path": "file_path"})
        self.mappings.setdefault("filesystem_write_file", {"path": "file_path"})

    def adapt(
        self,
        tool_name: str,
        capability: Optional[str],
        tool: str,
        raw_params: Dict[str, Any],
        execution_context: ExecutionContext,
        contract: Optional[ToolContract] = None
    ) -> Dict[str, Any]:
        """
        Apply parameter name mappings

        Generic transformation: rename parameters based on mapping rules
        """
        adapted = raw_params.copy()

        # Get mappings for this tool
        tool_mappings = self.mappings.get(tool_name, {})

        # Apply name transformations
        for old_name, new_name in tool_mappings.items():
            if old_name in adapted and new_name not in adapted:
                adapted[new_name] = adapted.pop(old_name)
                logger.debug(f"Mapped parameter {old_name} -> {new_name} for {tool_name}")

        return adapted

    def register_mapping(
        self,
        tool_name: str,
        old_param_name: str,
        new_param_name: str
    ):
        """
        Register a parameter mapping for a tool

        Args:
            tool_name: Tool identifier
            old_param_name: Original parameter name
            new_param_name: New parameter name
        """
        if tool_name not in self.mappings:
            self.mappings[tool_name] = {}
        self.mappings[tool_name][old_param_name] = new_param_name
        logger.debug(f"Registered mapping for {tool_name}: {old_param_name} -> {new_param_name}")

    def get_supported_capabilities(self) -> List[str]:
        """Mapping strategy is tool-specific, not capability-specific"""
        return []

    def supports_tool(self, tool_name: str) -> bool:
        """Check if tool has mappings defined"""
        return tool_name in self.mappings

