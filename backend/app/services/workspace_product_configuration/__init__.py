"""Workspace Product Configuration public facade."""

from .contracts import (
    ReplaceScopeCommand,
    WorkspaceCapabilitySetSnapshot,
)
from .facade import WorkspaceProductConfigurationFacade

__all__ = [
    "ReplaceScopeCommand",
    "WorkspaceCapabilitySetSnapshot",
    "WorkspaceProductConfigurationFacade",
]
