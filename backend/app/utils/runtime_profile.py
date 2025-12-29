"""
Runtime Profile Utilities

Utility functions for working with Workspace Runtime Profile.
"""

from typing import Optional
from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile
from backend.app.models.workspace import Workspace, ExecutionMode


def get_resolved_mode(
    workspace: Workspace,
    runtime_profile: Optional[WorkspaceRuntimeProfile] = None
) -> ExecutionMode:
    """
    Get resolved execution mode with priority: runtime_profile.default_mode > workspace.execution_mode

    Args:
        workspace: Workspace object
        runtime_profile: Optional Runtime Profile (if None, will try to load from workspace.metadata)

    Returns:
        Resolved ExecutionMode
    """
    # Priority 1: Runtime Profile default_mode
    if runtime_profile:
        return runtime_profile.resolved_mode

    # Try to load from workspace.metadata if not provided
    if workspace.metadata and 'runtime_profile' in workspace.metadata:
        try:
            from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile
            profile_data = workspace.metadata['runtime_profile']
            runtime_profile = WorkspaceRuntimeProfile(**profile_data)
            return runtime_profile.resolved_mode
        except Exception:
            pass  # Fallback to workspace.execution_mode

    # Priority 2: Workspace execution_mode
    if workspace.execution_mode:
        try:
            return ExecutionMode(workspace.execution_mode)
        except ValueError:
            pass  # Invalid execution_mode value

    # Default: QA mode
    return ExecutionMode.QA

