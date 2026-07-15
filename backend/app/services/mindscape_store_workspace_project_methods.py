from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import (
    AgentExecution,
    Entity,
    EntityTag,
    EntityType,
    EventActor,
    EventType,
    IntentCard,
    IntentLog,
    IntentStatus,
    MindEvent,
    MindscapeProfile,
    PriorityLevel,
    Tag,
    TagCategory,
)
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store_utils import _utc_now


class MindscapeStoreWorkspaceProjectMixin:
    def create_workspace(self, workspace: Workspace) -> Workspace:
        """Create a new workspace"""
        return self.workspaces.create_workspace(workspace)

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID"""
        return await self.workspaces.get_workspace(workspace_id)

    async def get_workspace_summary(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get lightweight workspace data for shell rendering."""
        if hasattr(self.workspaces, "get_workspace_summary"):
            return await self.workspaces.get_workspace_summary(workspace_id)
        workspace = await self.workspaces.get_workspace(workspace_id)
        return workspace.model_dump() if workspace else None

    def list_workspaces(
        self,
        owner_user_id: str,
        primary_project_id: Optional[str] = None,
        limit: int = 50,
        group_id: Optional[str] = None,
    ) -> List[Workspace]:
        """List workspaces for a user"""
        return self.workspaces.list_workspaces(
            owner_user_id,
            primary_project_id=primary_project_id,
            group_id=group_id,
            limit=limit,
        )

    def list_workspace_summaries(
        self,
        owner_user_id: str,
        primary_project_id: Optional[str] = None,
        limit: int = 50,
        group_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List lightweight workspace summaries for navigation."""
        if hasattr(self.workspaces, "list_workspace_summaries"):
            return self.workspaces.list_workspace_summaries(
                owner_user_id,
                primary_project_id=primary_project_id,
                group_id=group_id,
                limit=limit,
            )
        return [
            workspace.model_dump()
            for workspace in self.workspaces.list_workspaces(
                owner_user_id,
                primary_project_id=primary_project_id,
                group_id=group_id,
                limit=limit,
            )
        ]

    async def update_workspace(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace"""
        return await self.workspaces.update_workspace(workspace)

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace"""
        return self.workspaces.delete_workspace(workspace_id)

    # ==================== Project Methods (Delegated) ====================

    def create_project(self, project: Any) -> Any:
        """Create a new project"""
        return self.projects.create_project(project)

    def get_project(self, project_id: str) -> Optional[Any]:
        """Get project by ID"""
        return self.projects.get_project(project_id)

    def list_projects(
        self,
        workspace_id: Optional[str] = None,
        state: Optional[str] = None,
        project_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Any]:
        """List projects with optional filters"""
        return self.projects.list_projects(
            workspace_id=workspace_id,
            state=state,
            project_type=project_type,
            limit=limit,
        )

    def update_project(self, project: Any) -> Any:
        """Update an existing project"""
        return self.projects.update_project(project)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project"""
        return self.projects.delete_project(project_id)
