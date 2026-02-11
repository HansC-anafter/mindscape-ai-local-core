"""Postgres adaptation of ProjectsStore."""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional
from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.project import Project

logger = logging.getLogger(__name__)


class PostgresProjectsStore(PostgresStoreBase):
    """Postgres implementation of ProjectsStore."""

    def create_project(self, project: Project) -> Project:
        """Create a new project."""
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO projects (
                    id, "type", title, home_workspace_id, flow_id, state,
                    initiator_user_id, human_owner_user_id, ai_pm_id,
                    created_at, updated_at, metadata
                ) VALUES (
                    :id, :type, :title, :home_workspace_id, :flow_id, :state,
                    :initiator_user_id, :human_owner_user_id, :ai_pm_id,
                    :created_at, :updated_at, :metadata
                )
            """
            )
            params = {
                "id": project.id,
                "type": project.type,
                "title": project.title,
                "home_workspace_id": project.home_workspace_id,
                "flow_id": project.flow_id,
                "state": project.state,
                "initiator_user_id": project.initiator_user_id,
                "human_owner_user_id": project.human_owner_user_id,
                "ai_pm_id": project.ai_pm_id,
                "created_at": project.created_at,
                "updated_at": project.updated_at,
                "metadata": (
                    self.serialize_json(project.metadata) if project.metadata else None
                ),
            }
            conn.execute(query, params)
            logger.info(f"Created project: {project.id}")
            return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get project by ID."""
        with self.get_connection() as conn:
            query = text("SELECT * FROM projects WHERE id = :id")
            result = conn.execute(query, {"id": project_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_project(row)

    def list_projects(
        self,
        workspace_id: Optional[str] = None,
        state: Optional[str] = None,
        project_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Project]:
        """List projects with optional filters."""
        with self.get_connection() as conn:
            query_str = "SELECT * FROM projects WHERE 1=1"
            params = {"limit": limit}

            if workspace_id:
                query_str += " AND home_workspace_id = :workspace_id"
                params["workspace_id"] = workspace_id

            if state:
                query_str += " AND state = :state"
                params["state"] = state

            if project_type:
                query_str += ' AND "type" = :project_type'
                params["project_type"] = project_type

            query_str += " ORDER BY updated_at DESC LIMIT :limit"

            result = conn.execute(text(query_str), params)
            rows = result.fetchall()
            return [self._row_to_project(row) for row in rows]

    def update_project(self, project: Project) -> Project:
        """Update an existing project."""
        project.updated_at = _utc_now()
        with self.transaction() as conn:
            query = text(
                """
                UPDATE projects SET
                    "type" = :type,
                    title = :title,
                    home_workspace_id = :home_workspace_id,
                    flow_id = :flow_id,
                    state = :state,
                    initiator_user_id = :initiator_user_id,
                    human_owner_user_id = :human_owner_user_id,
                    ai_pm_id = :ai_pm_id,
                    updated_at = :updated_at,
                    metadata = :metadata
                WHERE id = :id
            """
            )
            params = {
                "type": project.type,
                "title": project.title,
                "home_workspace_id": project.home_workspace_id,
                "flow_id": project.flow_id,
                "state": project.state,
                "initiator_user_id": project.initiator_user_id,
                "human_owner_user_id": project.human_owner_user_id,
                "ai_pm_id": project.ai_pm_id,
                "updated_at": project.updated_at,
                "metadata": (
                    self.serialize_json(project.metadata) if project.metadata else None
                ),
                "id": project.id,
            }
            conn.execute(query, params)
            return project

    def delete_project(self, project_id: str) -> bool:
        """Delete a project."""
        with self.transaction() as conn:
            query = text("DELETE FROM projects WHERE id = :id")
            result = conn.execute(query, {"id": project_id})
            return result.rowcount > 0

    def _row_to_project(self, row) -> Project:
        """Convert database row to Project."""
        return Project(
            id=row.id,
            type=row.type,
            title=row.title,
            home_workspace_id=row.home_workspace_id,
            flow_id=row.flow_id,
            state=row.state,
            initiator_user_id=row.initiator_user_id,
            human_owner_user_id=row.human_owner_user_id,
            ai_pm_id=row.ai_pm_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            metadata=self.deserialize_json(row.metadata, {}),
        )
