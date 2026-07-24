"""Workspace capability admission facade seam."""

from .contracts import (
    AdmissionDenied,
    ExecutionAdmissionSnapshot,
    RootAdmissionRequest,
    RootAdmissionResult,
)
from .facade import WorkspaceCapabilityAdmissionFacade

__all__ = [
    "AdmissionDenied",
    "ExecutionAdmissionSnapshot",
    "RootAdmissionRequest",
    "RootAdmissionResult",
    "WorkspaceCapabilityAdmissionFacade",
]
