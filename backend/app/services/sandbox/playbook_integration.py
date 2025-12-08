"""
Playbook integration adapter for Sandbox system

Provides adapter layer to integrate new Sandbox system with existing Playbook execution flow.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.sandbox.sandbox_manager import SandboxManager
from backend.app.services.project.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class SandboxPlaybookAdapter:
    """
    Adapter to integrate Sandbox system with Playbook execution

    Provides compatibility layer between existing ProjectSandboxManager usage
    and new unified Sandbox system.
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize adapter

        Args:
            store: MindscapeStore instance
        """
        self.store = store
        self.sandbox_manager = SandboxManager(store)
        self.project_manager = ProjectManager(store)

    async def get_or_create_sandbox_for_project(
        self,
        project_id: str,
        workspace_id: str,
        sandbox_type: Optional[str] = None
    ) -> str:
        """
        Get or create sandbox for a project

        This method provides compatibility with existing ProjectSandboxManager usage.
        It creates a sandbox if it doesn't exist, or returns existing sandbox ID.

        Args:
            project_id: Project identifier
            workspace_id: Workspace identifier
            sandbox_type: Optional sandbox type (default: infer from project type)

        Returns:
            Sandbox identifier
        """
        try:
            project = await self.project_manager.get_project(project_id, workspace_id=workspace_id)
            if not project:
                raise ValueError(f"Project {project_id} not found")

            if not sandbox_type:
                sandbox_type = self._infer_sandbox_type(project.type)

            sandboxes = await self.sandbox_manager.list_sandboxes(
                workspace_id=workspace_id,
                sandbox_type=sandbox_type
            )

            project_sandbox = next(
                (s for s in sandboxes if s.get("metadata", {}).get("context", {}).get("project_id") == project_id),
                None
            )

            if project_sandbox:
                return project_sandbox["sandbox_id"]

            sandbox_id = await self.sandbox_manager.create_sandbox(
                sandbox_type=sandbox_type,
                workspace_id=workspace_id,
                context={"project_id": project_id, "project_type": project.type}
            )

            logger.info(f"Created sandbox {sandbox_id} for project {project_id}")
            return sandbox_id
        except Exception as e:
            logger.error(f"Failed to get or create sandbox for project {project_id}: {e}")
            raise

    async def get_sandbox_path_for_compatibility(
        self,
        project_id: str,
        workspace_id: str
    ) -> Path:
        """
        Get sandbox path for compatibility with existing code

        This method provides the same interface as ProjectSandboxManager.get_sandbox_path()
        but uses the new Sandbox system internally.

        Args:
            project_id: Project identifier
            workspace_id: Workspace identifier

        Returns:
            Path to sandbox directory (current version)
        """
        sandbox_id = await self.get_or_create_sandbox_for_project(project_id, workspace_id)
        sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)

        if not sandbox:
            raise ValueError(f"Sandbox {sandbox_id} not found")

        sandbox_path = self.sandbox_manager._get_sandbox_path(
            sandbox_id,
            workspace_id,
            sandbox.sandbox_type
        )

        current_path = sandbox_path / "current"
        return current_path

    def _infer_sandbox_type(self, project_type: str) -> str:
        """
        Infer sandbox type from project type

        Args:
            project_type: Project type identifier

        Returns:
            Sandbox type identifier
        """
        type_mapping = {
            "web_page": "web_page",
            "threejs_hero": "threejs_hero",
            "writing_project": "writing_project",
            "project_repo": "project_repo",
        }

        return type_mapping.get(project_type, "project_repo")

