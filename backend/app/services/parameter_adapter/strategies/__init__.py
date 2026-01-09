"""
Parameter Adaptation Strategies

Generic, neutral parameter adaptation strategies.
No business logic - only generic transformation patterns.

Architecture:
- base.py: Base strategy interface and passthrough implementation
- contract_based.py: Contract-based parameter adaptation (generic)
- parameter_mapping.py: Generic parameter name/format transformation
"""

from .base import ParameterAdaptationStrategy, PassthroughStrategy
from .contract_based import ContractBasedStrategy
from .parameter_mapping import ParameterMappingStrategy

__all__ = [
    "ParameterAdaptationStrategy",
    "PassthroughStrategy",
    "ContractBasedStrategy",
    "ParameterMappingStrategy",
]
