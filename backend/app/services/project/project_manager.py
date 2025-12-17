"""
Project Manager service

Handles Project CRUD operations and manages project lifecycle.
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging

from backend.app.models.project import Project
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.projects_store import ProjectsStore

logger = logging.getLogger(__name__)


class ProjectManager:
    """
    Project Manager - manages Project lifecycle and operations

    Provides high-level operations for creating, retrieving, and managing
    Projects within Workspaces.
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize Project Manager

        Args:
            store: MindscapeStore instance
        """
        self.store = store
        self.projects_store = ProjectsStore(db_path=store.db_path)

    async def create_project(
        self,
        project_type: str,
        title: str,
        workspace_id: str,
        flow_id: Optional[str] = None,
        initiator_user_id: str = None,
        human_owner_user_id: Optional[str] = None,
        ai_pm_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        playbook_sequence: Optional[List[str]] = None
    ) -> Project:
        """
        Create a new Project

        Args:
            project_type: Project type (web_page, book, course, campaign, etc.)
            title: Project title
            workspace_id: Home workspace ID
            flow_id: Playbook flow ID
            initiator_user_id: User who initiated this project
            human_owner_user_id: Optional human PM user ID
            ai_pm_id: Optional AI PM ID
            metadata: Optional metadata dictionary

        Returns:
            Created Project object
        """
        # Generate project ID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        project_id = f"{project_type}_{timestamp}_{uuid.uuid4().hex[:8]}"

        # Generate unique flow_id for this project (if not provided)
        # Use UUID to avoid conflicts between projects
        if not flow_id:
            flow_id = f"flow_{uuid.uuid4().hex[:12]}"
            logger.info(f"Generated unique flow_id for project: {flow_id}")

        project = Project(
            id=project_id,
            type=project_type,
            title=title,
            home_workspace_id=workspace_id,
            flow_id=flow_id,
            state="open",
            initiator_user_id=initiator_user_id,
            human_owner_user_id=human_owner_user_id,
            ai_pm_id=ai_pm_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            metadata=metadata or {}
        )

        # Validate workspace exists
        workspace = self.store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace not found: {workspace_id}")

        # Validate flow exists, create default if not
        from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
        from backend.app.models.playbook_flow import PlaybookFlow
        flows_store = PlaybookFlowsStore(self.store.db_path)
        flow = flows_store.get_flow(flow_id)

        if not flow:
            logger.warning(f"Flow {flow_id} not found, creating default flow")
            # Validate playbook_sequence before creating flow
            from backend.app.services.project.playbook_validator import validate_playbook_sequence
            from pathlib import Path

            base_dir = Path(__file__).parent.parent.parent.parent
            validated_playbook_sequence = validate_playbook_sequence(playbook_sequence or [], base_dir)

            flow = PlaybookFlow(
                id=flow_id,
                name=f"{project_type.title()} Flow",
                description=f"Flow for {project_type} projects",
                flow_definition={
                    "nodes": [],
                    "edges": [],
                    "playbook_sequence": validated_playbook_sequence
                },
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            flows_store.create_flow(flow)
            logger.info(f"Created flow: {flow_id} with {len(validated_playbook_sequence)} validated playbooks")

        # Save project
        self.projects_store.create_project(project)
        logger.info(f"Created project: {project_id} in workspace: {workspace_id} with flow_id: {flow_id}")

        return project

    async def get_project(self, project_id: str, workspace_id: Optional[str] = None) -> Optional[Project]:
        """
        Get Project by ID with optional workspace validation

        Args:
            project_id: Project ID
            workspace_id: Optional workspace ID for boundary check

        Returns:
            Project object or None if not found

        Raises:
            PermissionError: If workspace_id is provided and project doesn't belong to it
        """
        project = self.projects_store.get_project(project_id)
        if not project:
            return None

        # Workspace boundary check
        if workspace_id and project.home_workspace_id != workspace_id:
            raise PermissionError(
                f"Project {project_id} does not belong to workspace {workspace_id}"
            )

        return project

    async def list_projects(
        self,
        workspace_id: Optional[str] = None,
        state: Optional[str] = None,
        project_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Project]:
        """
        List projects with optional filters

        Args:
            workspace_id: Optional workspace filter
            state: Optional state filter (open, closed, archived)
            project_type: Optional project type filter
            limit: Maximum number of projects to return

        Returns:
            List of Project objects, ordered by updated_at DESC
        """
        return self.projects_store.list_projects(
            workspace_id=workspace_id,
            state=state,
            project_type=project_type,
            limit=limit
        )

    async def update_project(self, project: Project) -> Project:
        """
        Update an existing Project

        Args:
            project: Project object with updated fields

        Returns:
            Updated Project object
        """
        project.updated_at = datetime.utcnow()
        self.projects_store.update_project(project)
        logger.info(f"Updated project: {project.id}")

        return project

    async def close_project(self, project_id: str) -> Project:
        """
        Close a project (set state to 'closed')

        Args:
            project_id: Project ID

        Returns:
            Updated Project object

        Raises:
            ValueError: If project not found
        """
        project = self.projects_store.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        project.state = "closed"
        return await self.update_project(project)

    async def archive_project(self, project_id: str) -> Project:
        """
        Archive a project (set state to 'archived')

        Args:
            project_id: Project ID

        Returns:
            Updated Project object

        Raises:
            ValueError: If project not found
        """
        project = self.projects_store.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        project.state = "archived"
        return await self.update_project(project)

