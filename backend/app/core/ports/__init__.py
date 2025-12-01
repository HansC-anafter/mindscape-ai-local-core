"""
Port Interfaces - Pluggable abstraction layer

Defines IdentityPort and IntentRegistryPort interfaces,
allowing local/cloud to be implemented through different adapters
"""

from .identity_port import IdentityPort
from .intent_registry_port import IntentRegistryPort, IntentResolutionResult, IntentDefinition

__all__ = [
    "IdentityPort",
    "IntentRegistryPort",
    "IntentResolutionResult",
    "IntentDefinition",
]

