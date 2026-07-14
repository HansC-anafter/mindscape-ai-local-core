"""
Compatibility facade for capability API loading.

The implementation is split by responsibility so route discovery, runtime
state, and activation logic can be audited independently while preserving the
original import path for callers.
"""

from .capability_api_loader_activation import (
    activate_capability_api_code,
    activate_seeded_capability_apis,
    load_capability_apis,
)
from .capability_api_loader_core import (
    CapabilityAPILoader,
    discover_capability_api_descriptors,
)
from .capability_api_loader_state import (
    _capability_registration_complete,
    _descriptor_state_key,
    _extract_registered_routes_from_app,
    _get_runtime_state,
    _remove_routes_for_prefixes,
    build_descriptor_registered_prefixes,
    capability_api_registration_complete,
    find_seeded_capability_for_path,
    get_capability_api_activation_policy,
    get_capability_api_startup_activation_allowlist,
    group_capability_api_descriptors,
    load_manifest_for_descriptor,
    refresh_seeded_capability_descriptors,
    seed_capability_api_descriptors,
)
from .capability_api_loader_types import (
    _APP_STATE_KEY,
    _DEFAULT_SEED_ONLY_STARTUP_ACTIVATION_ALLOWLIST,
    _VALID_ACTIVATION_POLICIES,
    CapabilityAPIDescriptor,
)

__all__ = [
    "CapabilityAPIDescriptor",
    "CapabilityAPILoader",
    "activate_capability_api_code",
    "activate_seeded_capability_apis",
    "build_descriptor_registered_prefixes",
    "capability_api_registration_complete",
    "discover_capability_api_descriptors",
    "find_seeded_capability_for_path",
    "get_capability_api_activation_policy",
    "get_capability_api_startup_activation_allowlist",
    "group_capability_api_descriptors",
    "load_capability_apis",
    "load_manifest_for_descriptor",
    "refresh_seeded_capability_descriptors",
    "seed_capability_api_descriptors",
    "_APP_STATE_KEY",
    "_DEFAULT_SEED_ONLY_STARTUP_ACTIVATION_ALLOWLIST",
    "_VALID_ACTIVATION_POLICIES",
    "_capability_registration_complete",
    "_descriptor_state_key",
    "_extract_registered_routes_from_app",
    "_get_runtime_state",
    "_remove_routes_for_prefixes",
]
