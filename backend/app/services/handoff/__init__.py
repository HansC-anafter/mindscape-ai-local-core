"""
Handoff package — local-core adapter for site-hub Handoff Registry.

Contract 4: translate + verify + retry. No local state.
"""

from .registry_client import HandoffRegistryClient, RegistryUnavailable
from .adapter import HandoffAdapter

__all__ = [
    "HandoffRegistryClient",
    "HandoffAdapter",
    "RegistryUnavailable",
]
