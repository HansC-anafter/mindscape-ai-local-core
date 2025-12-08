"""
Project Sandbox Manager

Manages sandbox directories for Projects.
Provides isolated file system spaces for project artifacts.

Now uses unified SandboxManager internally while maintaining backward compatibility.
"""

import os
from pathlib import Path
from typing import Optional
import logging

from backend.app.services.project.project_manager import ProjectManager
from backend.app.services.mindscape_store import MindscapeStore
# Import SandboxPlaybookAdapter lazily to avoid circular import

logger = logging.getLogger(__name__)


class ProjectSandboxManager:
    """
    Manages project sandbox directories

    Provides isolated sandbox spaces for each project, organized by:
    sandboxes/{workspace_id}/{project_type}/{project_id}/
    """

    def __init__(self, store: MindscapeStore, base_sandbox_dir: Optional[str] = None):
        """
        Initialize Project Sandbox Manager

        Now uses unified SandboxManager internally while maintaining backward compatibility.

        Args:
            store: MindscapeStore instance
            base_sandbox_dir: Base directory for sandboxes (default: data/sandboxes)
        """
        self.store = store
        self.project_manager = ProjectManager(store)
        self._sandbox_adapter = None  # Lazy initialization to avoid circular dependency

    @property
    def sandbox_adapter(self):
        """Lazy initialization of SandboxPlaybookAdapter"""
        if self._sandbox_adapter is None:
            from backend.app.services.sandbox.playbook_integration import SandboxPlaybookAdapter
            self._sandbox_adapter = SandboxPlaybookAdapter(self.store)
        return self._sandbox_adapter

        if base_sandbox_dir:
            self.base_sandbox_dir = Path(base_sandbox_dir)
        else:
            data_dir = Path(store.db_path).parent
            self.base_sandbox_dir = data_dir / "sandboxes"

        self.base_sandbox_dir.mkdir(parents=True, exist_ok=True)

    async def get_sandbox_path(
        self,
        project_id: str,
        workspace_id: str
    ) -> Path:
        """
        Get or create sandbox directory for a project

        Now uses unified SandboxManager internally while maintaining backward compatibility.
        Returns path to current version of unified sandbox.

        Args:
            project_id: Project ID
            workspace_id: Workspace ID (for validation and path isolation)

        Returns:
            Path to project sandbox directory (current version)

        Raises:
            ValueError: If project not found or workspace mismatch
        """
        try:
            return await self.sandbox_adapter.get_sandbox_path_for_compatibility(
                project_id=project_id,
                workspace_id=workspace_id
            )
        except Exception as e:
            logger.warning(f"Failed to get unified sandbox path, falling back to legacy: {e}")
            project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
            if not project:
                raise ValueError(f"Project {project_id} not found")

            sandbox_path = self.base_sandbox_dir / workspace_id / project.type / project_id
            sandbox_path.mkdir(parents=True, exist_ok=True)

            logger.debug(f"Sandbox path for project {project_id} (workspace {workspace_id}): {sandbox_path}")
            return sandbox_path

    async def get_artifact_path(
        self,
        project_id: str,
        workspace_id: str,
        artifact_id: str,
        artifact_type: str
    ) -> Path:
        """
        Get path for an artifact within project sandbox

        Args:
            project_id: Project ID
            workspace_id: Workspace ID
            artifact_id: Artifact identifier
            artifact_type: Artifact type (markdown, html, json, etc.)

        Returns:
            Path to artifact file
        """
        sandbox_path = await self.get_sandbox_path(project_id, workspace_id)

        type_extensions = {
            "markdown": ".md",
            "md": ".md",
            "html": ".html",
            "json": ".json",
            "txt": ".txt"
        }

        extension = type_extensions.get(artifact_type.lower(), ".txt")
        artifact_path = sandbox_path / f"{artifact_id}{extension}"

        return artifact_path

    async def cleanup_sandbox(
        self,
        project_id: str,
        workspace_id: str
    ) -> bool:
        """
        Clean up sandbox directory for a project

        Args:
            project_id: Project ID
            workspace_id: Workspace ID

        Returns:
            True if cleanup successful, False otherwise
        """
        project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            logger.warning(f"Project {project_id} not found for cleanup")
            return False

        sandbox_path = self.base_sandbox_dir / workspace_id / project.type / project_id

        if not sandbox_path.exists():
            return True

        try:
            import shutil
            shutil.rmtree(sandbox_path)
            logger.info(f"Cleaned up sandbox for project {project_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup sandbox for project {project_id}: {e}")
            return False

