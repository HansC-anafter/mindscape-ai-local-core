"""
Parameter Adapter Module

Modular parameter adaptation system for transforming parameters between
playbook execution context and external service contracts.

Architecture:
- Core: Main adapter interface and coordination
- Context: Execution context management
- Contracts: Tool contract definitions
- Strategies: Tool-specific adaptation strategies
- Validators: Parameter validation
"""

from .core import ParameterAdapter, get_parameter_adapter
from .context import ExecutionContext, ExecutionContextBuilder
from .contracts import ToolContract, ContractRegistry

__all__ = [
    "ParameterAdapter",
    "get_parameter_adapter",
    "ExecutionContext",
    "ExecutionContextBuilder",
    "ToolContract",
    "ContractRegistry",
]

