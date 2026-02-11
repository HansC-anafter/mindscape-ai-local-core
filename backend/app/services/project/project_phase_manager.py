"""
Project Phase Manager

Manages Project Phase lifecycle:
- Create new phases for assignments
- Query phase history
- Link phases to execution plans
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
import uuid
from backend.app.models.project import ProjectPhase
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.project_phases_store import ProjectPhasesStore

logger = logging.getLogger(__name__)


class ProjectPhaseManager:
    """
    Project Phase Manager - manages project phases/assignments

    Uses ProjectPhasesStore for persistent storage in database.
    """

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.phases_store = ProjectPhasesStore(db_path=store.db_path)

    async def create_phase(
        self,
        project_id: str,
        message_id: str,
        summary: str,
        kind: str = "unknown",
        workspace_id: Optional[str] = None,
        execution_plan_id: Optional[str] = None
    ) -> ProjectPhase:
        """
        Create a new project phase

        Args:
            project_id: Project ID
            message_id: Message ID that created this phase
            summary: Phase summary
            kind: Phase kind
            workspace_id: Workspace ID (required for database storage)
            execution_plan_id: Optional execution plan ID to link this phase

        Returns:
            Created ProjectPhase
        """
        phase = ProjectPhase(
            id=str(uuid.uuid4()),
            project_id=project_id,
            created_at=_utc_now(),
            created_by_message_id=message_id,
            kind=kind,
            summary=summary,
            tags=[],
            metadata={}
        )

        # Get workspace_id if not provided
        if not workspace_id:
            # Try to get from project
            from backend.app.services.project.project_manager import ProjectManager
            project_manager = ProjectManager(self.store)
            project = await project_manager.get_project(project_id)
            if project:
                workspace_id = project.home_workspace_id

        if not workspace_id:
            raise ValueError(f"workspace_id is required to create phase for project {project_id}")

        # Save to database
        self.phases_store.create_phase(
            phase=phase,
            workspace_id=workspace_id,
            execution_plan_id=execution_plan_id
        )

        logger.info(f"Created phase {phase.id} for project {project_id} in workspace {workspace_id}")

        return phase

    async def get_recent_phases(
        self,
        project_id: str,
        limit: int = 5
    ) -> List[ProjectPhase]:
        """
        Get recent phases for a project

        Args:
            project_id: Project ID
            limit: Maximum number of phases to return

        Returns:
            List of recent phases, ordered by created_at DESC
        """
        return self.phases_store.get_recent_phases(project_id=project_id, limit=limit)

    async def get_phase(self, phase_id: str) -> Optional[ProjectPhase]:
        """
        Get phase by ID

        Args:
            phase_id: Phase ID

        Returns:
            ProjectPhase or None
        """
        return self.phases_store.get_phase(phase_id)

    async def update_phase(self, phase: ProjectPhase) -> ProjectPhase:
        """
        Update an existing phase

        Args:
            phase: ProjectPhase object with updated fields

        Returns:
            Updated ProjectPhase
        """
        return self.phases_store.update_phase(phase)

