"""
Contract-Based Parameter Adaptation Strategy

Generic strategy that adapts parameters based on tool contracts.
No business logic - purely contract-driven adaptation.

Responsibilities:
- Inject parameters from execution context based on contract definitions
- Apply default values from contract
- Not responsible for:
  - Contract definition (contracts come from external sources)
  - Business-specific transformations
"""

import logging
from typing import Dict, Any, Optional, List

from .base import ParameterAdaptationStrategy
from ..context import ExecutionContext
from ..contracts import ToolContract, ParameterRequirement

logger = logging.getLogger(__name__)


class ContractBasedStrategy(ParameterAdaptationStrategy):
    """
    Generic contract-based parameter adaptation strategy

    Adapts parameters based on tool contract definitions.
    This is a neutral, generic strategy that works with any contract.
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
        """
        Adapt parameters based on contract

        Generic adaptation process:
        1. Inject parameters from context (if contract defines INJECTED params)
        2. Apply default values (if contract defines defaults)
        3. Pass through other parameters unchanged
        """
        if not contract:
            # No contract = no adaptation needed
            return raw_params

        adapted = raw_params.copy()

        # Step 1: Inject parameters from execution context
        adapted = self._inject_context_params(adapted, execution_context, contract)

        # Step 2: Apply default values for optional parameters
        adapted = self._apply_defaults(adapted, contract)

        logger.debug(
            f"Contract-based adaptation for {tool_name}: "
            f"injected={len(contract.get_injected_parameters())} params, "
            f"output_keys={list(adapted.keys())}"
        )

        return adapted

    def _apply_defaults(
        self,
        params: Dict[str, Any],
        contract: ToolContract
    ) -> Dict[str, Any]:
        """
        Apply default values from contract

        Args:
            params: Current parameters
            contract: Tool contract

        Returns:
            Parameters with defaults applied
        """
        result = params.copy()

        for param_name, param_def in contract.parameters.items():
            if param_name not in result:
                if param_def.requirement == ParameterRequirement.OPTIONAL:
                    if param_def.default_value is not None:
                        result[param_name] = param_def.default_value
                        logger.debug(f"Applied default value for {param_name}: {param_def.default_value}")

        return result

    def get_supported_capabilities(self) -> List[str]:
        """
        Contract-based strategy supports all capabilities
        (it's generic and contract-driven)
        """
        return []

    def supports_tool(self, tool_name: str) -> bool:
        """
        Supports any tool that has a contract defined
        (check is done by adapter based on contract availability)
        """
        return False

