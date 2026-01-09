"""
Core Parameter Adapter

Main adapter interface that coordinates strategy selection and execution.
Responsible for:
- Strategy selection based on tool name/capability
- Delegating to appropriate strategy
- Parameter validation
- Error handling
"""

import logging
from typing import Dict, Any, Optional, List

from .context import ExecutionContext
from .contracts import ContractRegistry
from .strategies.base import ParameterAdaptationStrategy, PassthroughStrategy
from .strategies.contract_based import ContractBasedStrategy
from .strategies.parameter_mapping import ParameterMappingStrategy
from .validators import ParameterValidator

logger = logging.getLogger(__name__)

# Global adapter instance
_adapter_instance: Optional["ParameterAdapter"] = None


class ParameterAdapter:
    """
    Main parameter adapter that coordinates parameter transformation

    Responsibilities:
    - Strategy selection and delegation
    - Parameter validation
    - Error handling and logging
    - Not responsible for:
      - Specific parameter transformation logic (delegated to strategies)
      - Execution context creation (delegated to ExecutionContextBuilder)
      - Contract definition (contracts loaded from external sources)
    """

    def __init__(
        self,
        contract_registry: Optional[ContractRegistry] = None,
        validator: Optional[ParameterValidator] = None
    ):
        """
        Initialize parameter adapter

        Args:
            contract_registry: Contract registry for tool contract lookup
            validator: Parameter validator instance
        """
        self.contract_registry = contract_registry or ContractRegistry()
        self.validator = validator or ParameterValidator()

        # Register generic strategies (no business logic)
        self.contract_strategy = ContractBasedStrategy()
        self.mapping_strategy = ParameterMappingStrategy()
        self.passthrough_strategy = PassthroughStrategy()

        # Auto-load contracts from capability manifests
        self._load_contracts_from_capabilities()

        # Register test contract for yogacoach.intake_router (temporary, for testing)
        # In production, contracts should be loaded from manifest.yaml
        self._register_test_contracts()

    def adapt_parameters(
        self,
        tool_name: str,
        raw_params: Dict[str, Any],
        execution_context: ExecutionContext
    ) -> Dict[str, Any]:
        """
        Adapt parameters for tool execution

        Generic adaptation process:
        1. Apply parameter name mappings (if any)
        2. Apply contract-based adaptation (if contract exists)
        3. Validate adapted parameters

        Args:
            tool_name: Tool identifier (e.g., 'yogacoach.intake_router')
            raw_params: Raw parameters from playbook
            execution_context: Execution context with workspace_id, profile_id, etc.

        Returns:
            Adapted parameters ready for tool execution

        Raises:
            ValueError: If parameter adaptation fails
        """
        try:
            # Extract capability and tool from tool_name
            capability, tool = self._parse_tool_name(tool_name)

            # Get tool contract for validation and adaptation
            contract = self.contract_registry.get_contract(tool_name, capability, tool)

            # Step 1: Apply parameter name mappings (generic transformation)
            adapted_params = self.mapping_strategy.adapt(
                tool_name=tool_name,
                capability=capability,
                tool=tool,
                raw_params=raw_params,
                execution_context=execution_context,
                contract=contract
            )

            # Step 2: Apply contract-based adaptation (context injection, defaults)
            if contract:
                logger.debug(f"Found contract for {tool_name}, applying contract-based adaptation")
                adapted_params = self.contract_strategy.adapt(
                    tool_name=tool_name,
                    capability=capability,
                    tool=tool,
                    raw_params=adapted_params,
                    execution_context=execution_context,
                    contract=contract
                )
            else:
                logger.debug(f"No contract found for {tool_name}, skipping contract-based adaptation")

            # Step 3: Validate adapted parameters
            self.validator.validate(adapted_params, contract)

            logger.debug(
                f"Adapted parameters for {tool_name}: "
                f"input_keys={list(raw_params.keys())}, "
                f"output_keys={list(adapted_params.keys())}"
            )

            return adapted_params

        except Exception as e:
            logger.error(f"Parameter adaptation failed for {tool_name}: {e}", exc_info=True)
            raise ValueError(f"Failed to adapt parameters for {tool_name}: {str(e)}") from e

    def _parse_tool_name(self, tool_name: str) -> tuple[Optional[str], str]:
        """
        Parse tool name to extract capability and tool

        Args:
            tool_name: Tool identifier

        Returns:
            Tuple of (capability, tool)
        """
        if '.' in tool_name:
            parts = tool_name.split('.', 1)
            if len(parts) == 2:
                return parts[0], parts[1]
        return None, tool_name

    def get_supported_tools(self) -> List[str]:
        """
        Get list of tools with contracts or mappings defined

        Returns:
            List of supported tool names
        """
        # Return tools that have contracts or mappings
        # This is informational only
        return []

    def _load_contracts_from_capabilities(self):
        """Load contracts from all capability manifests"""
        try:
            from backend.app.capabilities.registry import get_registry
            from pathlib import Path

            registry = get_registry()
            capabilities = registry.list_capabilities()

            for capability_code in capabilities:
                capability_info = registry.get_capability(capability_code)
                if capability_info:
                    directory = capability_info.get('directory')
                    if directory:
                        manifest_path = Path(directory) / "manifest.yaml"
                        if manifest_path.exists():
                            self.contract_registry.load_contracts_from_manifest(
                                manifest_path,
                                capability_code
                            )
            logger.info(f"Loaded {len(self.contract_registry._contracts)} tool contracts from capabilities")
        except Exception as e:
            logger.warning(f"Failed to auto-load contracts from capabilities: {e}", exc_info=True)

    def _register_test_contracts(self):
        """Register test contracts (temporary, for testing)"""
        from .contracts import ToolContract, ParameterDefinition, ParameterRequirement

        # Test contract for yogacoach.intake_router
        test_contract = ToolContract(
            tool_name="yogacoach.intake_router",
            capability="yogacoach",
            parameters={
                "tenant_id": ParameterDefinition(
                    name="tenant_id",
                    requirement=ParameterRequirement.INJECTED,
                    source="context.workspace_id",
                    description="Tenant ID for multi-tenant isolation"
                ),
                "actor_id": ParameterDefinition(
                    name="actor_id",
                    requirement=ParameterRequirement.INJECTED,
                    source="context.profile_id",
                    description="Who triggered the action"
                ),
                "subject_user_id": ParameterDefinition(
                    name="subject_user_id",
                    requirement=ParameterRequirement.INJECTED,
                    source="context.profile_id",
                    description="The person being analyzed"
                ),
            }
        )
        self.contract_registry.register_contract(test_contract)
        logger.info("Registered test contract for yogacoach.intake_router")


def get_parameter_adapter() -> ParameterAdapter:
    """
    Get global parameter adapter instance (singleton)

    Returns:
        Global ParameterAdapter instance
    """
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = ParameterAdapter()
    return _adapter_instance
