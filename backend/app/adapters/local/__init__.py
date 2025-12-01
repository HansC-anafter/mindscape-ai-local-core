"""
Local adapters - Single-user, single-workspace implementations

Provides LocalIdentityAdapter and LocalIntentRegistryAdapter for local-only usage.
"""

from .local_identity_adapter import LocalIdentityAdapter
from .local_intent_registry_adapter import LocalIntentRegistryAdapter

__all__ = [
    "LocalIdentityAdapter",
    "LocalIntentRegistryAdapter",
]

