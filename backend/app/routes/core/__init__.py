"""
Core routes module

Layer 0: Kernel routes that must be hardcoded in the core system.
These routes provide the fundamental OS-level functionality.
"""

from . import (
    agents,
    workspace,
    playbook,
    playbook_execution,
    config,
    system_settings,
    tools,
    vector_db,
    vector_search,
    capability_packs,
    capability_suites,
    sandbox,
    deployment,
    blueprint,
)
