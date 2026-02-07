"""
Workspace Sandbox Resolver

Resolves and validates sandbox paths for external agent execution.
Ensures all external agents execute within workspace boundaries.

Security Policy:
- sandbox_path MUST be within workspace's storage_base_path/sandboxes/
- workspace_id is REQUIRED for all external agent execution
- Sandbox paths are automatically generated, not manually specified
"""

import logging
import os
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkspaceSandboxResolver:
    """
    Resolve and validate sandbox paths for external agent execution.

    Enforces workspace-bound sandbox restriction:
    - All sandboxes must be under workspace's storage_base_path/sandboxes/
    - Sandbox paths are auto-generated per execution
    """

    # Fixed sandbox subdirectory name
    SANDBOX_SUBDIR = "agent_sandboxes"

    @staticmethod
    def get_sandbox_path_for_execution(
        workspace_storage_base: str,
        workspace_id: str,
        execution_id: str,
        agent_id: str = "default",
    ) -> Path:
        """
        Generate a sandbox path for an agent execution.

        Path structure:
        <workspace_storage_base>/agent_sandboxes/<agent_id>/<execution_id>/

        Args:
            workspace_storage_base: Workspace's storage_base_path
            workspace_id: Workspace ID (for validation)
            execution_id: Unique execution ID
            agent_id: Agent identifier (e.g., 'moltbot', 'langgraph')

        Returns:
            Path object pointing to the sandbox directory

        Raises:
            ValueError: If workspace_id is not provided
        """
        if not workspace_id:
            raise ValueError(
                "workspace_id is REQUIRED for external agent execution. "
                "All agent sandboxes must be bound to a workspace."
            )

        if not workspace_storage_base:
            raise ValueError(
                "workspace_storage_base is REQUIRED. "
                "Workspace must have a storage_base_path configured."
            )

        # Build sandbox path
        base_path = Path(workspace_storage_base).expanduser().resolve()
        sandbox_path = (
            base_path
            / WorkspaceSandboxResolver.SANDBOX_SUBDIR
            / agent_id
            / execution_id
        )

        # Ensure directory exists
        sandbox_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Created agent sandbox: {sandbox_path}",
            extra={
                "workspace_id": workspace_id,
                "agent_id": agent_id,
                "execution_id": execution_id,
            },
        )

        return sandbox_path

    @staticmethod
    def validate_sandbox_path(
        sandbox_path: str,
        workspace_storage_base: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that a sandbox path is within workspace boundaries.

        Args:
            sandbox_path: Path to validate
            workspace_storage_base: Workspace's storage_base_path

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not sandbox_path:
            return False, "sandbox_path cannot be empty"

        if not workspace_storage_base:
            return False, "workspace_storage_base is required for validation"

        try:
            sandbox = Path(sandbox_path).resolve()
            workspace_base = Path(workspace_storage_base).expanduser().resolve()
            expected_sandbox_root = (
                workspace_base / WorkspaceSandboxResolver.SANDBOX_SUBDIR
            )

            # Check if sandbox is under the expected sandbox root
            try:
                sandbox.relative_to(expected_sandbox_root)
                return True, None
            except ValueError:
                return False, (
                    f"Sandbox path '{sandbox}' is NOT within workspace boundary. "
                    f"Expected path under: {expected_sandbox_root}"
                )

        except Exception as e:
            return False, f"Path validation failed: {str(e)}"

    @staticmethod
    def is_path_within_workspace(
        path: str,
        workspace_storage_base: str,
    ) -> bool:
        """
        Check if any path is within the workspace storage area.

        Args:
            path: Path to check
            workspace_storage_base: Workspace's storage_base_path

        Returns:
            True if path is within workspace, False otherwise
        """
        try:
            target = Path(path).resolve()
            workspace_base = Path(workspace_storage_base).expanduser().resolve()
            target.relative_to(workspace_base)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def cleanup_sandbox(sandbox_path: str, keep_logs: bool = True) -> bool:
        """
        Clean up a sandbox directory after execution.

        Args:
            sandbox_path: Path to the sandbox directory
            keep_logs: If True, preserve execution logs

        Returns:
            True if cleanup succeeded, False otherwise
        """
        import shutil

        try:
            sandbox = Path(sandbox_path)
            if not sandbox.exists():
                return True

            if keep_logs:
                # Move logs to a preserved location
                log_files = list(sandbox.glob("*.log")) + list(sandbox.glob("*.json"))
                if log_files:
                    logs_dir = sandbox.parent / f"{sandbox.name}_logs"
                    logs_dir.mkdir(exist_ok=True)
                    for log_file in log_files:
                        shutil.copy2(log_file, logs_dir / log_file.name)

            shutil.rmtree(sandbox)
            logger.info(f"Cleaned up sandbox: {sandbox_path}")
            return True

        except Exception as e:
            logger.warning(f"Failed to cleanup sandbox {sandbox_path}: {e}")
            return False


# Convenience functions
def get_agent_sandbox(
    workspace_storage_base: str,
    workspace_id: str,
    execution_id: str,
    agent_id: str = "default",
) -> Path:
    """
    Convenience function to get a sandbox path for agent execution.

    Usage:
        sandbox = get_agent_sandbox(
            workspace_storage_base="/path/to/workspace",
            workspace_id="ws-123",
            execution_id="exec-456",
            agent_id="moltbot"
        )
    """
    return WorkspaceSandboxResolver.get_sandbox_path_for_execution(
        workspace_storage_base=workspace_storage_base,
        workspace_id=workspace_id,
        execution_id=execution_id,
        agent_id=agent_id,
    )


def validate_agent_sandbox(
    sandbox_path: str,
    workspace_storage_base: str,
) -> Tuple[bool, Optional[str]]:
    """
    Convenience function to validate a sandbox path.

    Usage:
        is_valid, error = validate_agent_sandbox(
            sandbox_path="/path/to/sandbox",
            workspace_storage_base="/path/to/workspace"
        )
        if not is_valid:
            raise ValueError(error)
    """
    return WorkspaceSandboxResolver.validate_sandbox_path(
        sandbox_path=sandbox_path,
        workspace_storage_base=workspace_storage_base,
    )
