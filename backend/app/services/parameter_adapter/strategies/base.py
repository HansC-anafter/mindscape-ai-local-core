"""
Base Parameter Adaptation Strategy

Defines the interface for parameter adaptation strategies.
Provides passthrough implementation for tools that don't need adaptation.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from ..context import ExecutionContext
from ..contracts import ToolContract

logger = logging.getLogger(__name__)


class ParameterAdaptationStrategy(ABC):
    """
    Base class for parameter adaptation strategies

    Each strategy is responsible for:
    - Adapting parameters for specific tool types/capabilities
    - Injecting context parameters when needed
    - Parameter name/format transformation

    Not responsible for:
    - Strategy selection (delegated to ParameterAdapter)
    - Parameter validation (delegated to validators)
    - Contract definition (delegated to ContractRegistry)
    """

    @abstractmethod
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
        Adapt parameters for tool execution

        Args:
            tool_name: Full tool name
            capability: Capability code
            tool: Tool name
            raw_params: Raw parameters from playbook
            execution_context: Execution context
            contract: Tool contract (optional)

        Returns:
            Adapted parameters
        """
        pass

    @abstractmethod
    def get_supported_capabilities(self) -> List[str]:
        """
        Get list of capabilities this strategy supports

        Returns:
            List of capability codes
        """
        pass

    def supports_tool(self, tool_name: str) -> bool:
        """
        Check if this strategy supports a specific tool

        Args:
            tool_name: Tool identifier

        Returns:
            True if strategy supports this tool
        """
        return False

    def get_supported_tools(self) -> List[str]:
        """
        Get list of specific tools this strategy supports

        Returns:
            List of tool names
        """
        return []

    def _inject_context_params(
        self,
        params: Dict[str, Any],
        execution_context: ExecutionContext,
        contract: Optional[ToolContract] = None
    ) -> Dict[str, Any]:
        """
        Inject parameters from execution context based on contract

        Args:
            params: Current parameters
            execution_context: Execution context
            contract: Tool contract

        Returns:
            Parameters with injected context values
        """
        if not contract:
            return params

        result = params.copy()
        injected_params = contract.get_injected_parameters()

        for param_name, source_path in injected_params.items():
            if param_name not in result:
                # Extract value from context using source path
                value = self._extract_from_context(execution_context, source_path)
                if value is not None:
                    result[param_name] = value

        return result

    def _extract_from_context(
        self,
        context: ExecutionContext,
        source_path: str
    ) -> Any:
        """
        Extract value from context using source path

        Args:
            context: Execution context
            source_path: Path like 'context.workspace_id' or 'context.profile_id'

        Returns:
            Extracted value or None
        """
        if not source_path.startswith("context."):
            return None

        field_name = source_path.replace("context.", "")
        return context.get(field_name)


class PassthroughStrategy(ParameterAdaptationStrategy):
    """
    Passthrough strategy that doesn't modify parameters

    Used for tools that don't need parameter adaptation.
    """

    def adapt(
        self,
        tool_name: str,
        capability: Optional[str],
        tool: str,
        raw_params: Dict[str, Any],
        execution_context: ExecutionContext,
        contract: Optional[ToolContract] = None
    ) -> Dict[str, Any]:
        """Pass through parameters without modification"""
        return self._inject_context_params(raw_params, execution_context, contract)

    def get_supported_capabilities(self) -> List[str]:
        """Passthrough supports all capabilities (fallback)"""
        return []

