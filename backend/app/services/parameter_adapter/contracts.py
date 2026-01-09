"""
Tool Contract Definitions

Defines contracts (parameter requirements) for tools.
Contracts describe what parameters a tool expects.

Responsibilities:
- Contract data structure definition
- Contract storage and lookup
- Contract loading from external sources (e.g., manifest.yaml)
- Not responsible for:
  - Parameter transformation
  - Parameter validation (delegated to validators)
  - Business-specific contract definitions (loaded from external sources)
"""

import logging
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ParameterRequirement(Enum):
    """Parameter requirement level"""
    REQUIRED = "required"
    OPTIONAL = "optional"
    INJECTED = "injected"  # Automatically injected from context


@dataclass
class ParameterDefinition:
    """Definition of a single parameter"""
    name: str
    requirement: ParameterRequirement
    description: Optional[str] = None
    default_value: Any = None
    source: Optional[str] = None  # Where to get this parameter (e.g., 'context.workspace_id')
    param_type: Optional[str] = None  # Parameter type hint (e.g., 'str', 'int', 'dict')


@dataclass
class ToolContract:
    """
    Contract defining parameter requirements for a tool

    This is a data structure describing what a tool needs.
    Contracts should be loaded from external sources (e.g., manifest.yaml),
    not hardcoded here.
    """
    tool_name: str
    capability: Optional[str] = None
    parameters: Dict[str, ParameterDefinition] = field(default_factory=dict)
    context_mappings: Dict[str, str] = field(default_factory=dict)

    def get_required_parameters(self) -> Set[str]:
        """Get set of required parameter names"""
        return {
            name for name, param in self.parameters.items()
            if param.requirement == ParameterRequirement.REQUIRED
        }

    def get_injected_parameters(self) -> Dict[str, str]:
        """Get parameters that should be injected from context"""
        return {
            name: param.source
            for name, param in self.parameters.items()
            if param.requirement == ParameterRequirement.INJECTED and param.source
        }


class ContractRegistry:
    """
    Registry for tool contracts

    Responsibilities:
    - Contract storage and lookup
    - Contract registration
    - Contract loading from external sources (e.g., capability manifests)
    - Not responsible for:
      - Contract creation (contracts are loaded from external sources)
      - Parameter transformation
    """

    def __init__(self):
        self._contracts: Dict[str, ToolContract] = {}
        # Contracts are loaded from external sources, not hardcoded

    def register_contract(self, contract: ToolContract):
        """
        Register a tool contract

        Args:
            contract: ToolContract instance
        """
        key = self._make_key(contract.tool_name, contract.capability)
        self._contracts[key] = contract
        logger.debug(f"Registered contract for {contract.tool_name}")

    def load_contracts_from_manifest(
        self,
        manifest_path: Path,
        capability_code: str
    ):
        """
        Load contracts from capability manifest.yaml

        Args:
            manifest_path: Path to manifest.yaml
            capability_code: Capability code
        """
        try:
            import yaml
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = yaml.safe_load(f)

            # Load tool contracts from manifest
            tools = manifest.get('tools', [])
            for tool in tools:
                tool_name = tool.get('name')
                if not tool_name:
                    continue

                full_tool_name = f"{capability_code}.{tool_name}"
                contract = self._create_contract_from_tool_def(
                    full_tool_name,
                    capability_code,
                    tool
                )
                if contract:
                    self.register_contract(contract)

        except Exception as e:
            logger.warning(f"Failed to load contracts from manifest {manifest_path}: {e}")

    def _create_contract_from_tool_def(
        self,
        tool_name: str,
        capability: str,
        tool_def: Dict[str, Any]
    ) -> Optional[ToolContract]:
        """
        Create contract from tool definition in manifest

        Args:
            tool_name: Full tool name
            capability: Capability code
            tool_def: Tool definition from manifest

        Returns:
            ToolContract or None
        """
        # Extract parameter definitions from tool metadata
        # This is a generic parser - no business logic
        parameters = {}

        # If tool has parameter schema defined, parse it
        param_schema = tool_def.get('parameters', {})
        if isinstance(param_schema, dict):
            for param_name, param_info in param_schema.items():
                if isinstance(param_info, dict):
                    requirement = ParameterRequirement.OPTIONAL
                    if param_info.get('required', False):
                        requirement = ParameterRequirement.REQUIRED
                    elif param_info.get('injected', False):
                        requirement = ParameterRequirement.INJECTED

                    parameters[param_name] = ParameterDefinition(
                        name=param_name,
                        requirement=requirement,
                        description=param_info.get('description'),
                        default_value=param_info.get('default'),
                        source=param_info.get('source'),  # e.g., 'context.workspace_id'
                        param_type=param_info.get('type')
                    )

        if not parameters:
            return None

        return ToolContract(
            tool_name=tool_name,
            capability=capability,
            parameters=parameters
        )

    def get_contract(
        self,
        tool_name: str,
        capability: Optional[str] = None,
        tool: Optional[str] = None
    ) -> Optional[ToolContract]:
        """
        Get contract for a tool

        Args:
            tool_name: Full tool name
            capability: Capability code
            tool: Tool name

        Returns:
            ToolContract or None if not found
        """
        # Try full tool name first
        key = self._make_key(tool_name, capability)
        if key in self._contracts:
            return self._contracts[key]

        # Try capability.tool format
        if capability and tool:
            key = self._make_key(f"{capability}.{tool}", capability)
            if key in self._contracts:
                return self._contracts[key]

        return None

    def _make_key(self, tool_name: str, capability: Optional[str]) -> str:
        """Create registry key for tool"""
        if capability:
            return f"{capability}:{tool_name}"
        return tool_name
