"""
Projects store for Mindscape data persistence
Handles project CRUD operations
"""

from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional
from backend.app.services.stores.base import StoreBase
from ...models.project import Project
import logging

logger = logging.getLogger(__name__)


class ProjectsStore(StoreBase):
    """Store for managing projects"""

    def create_project(self, project: Project) -> Project:
        """Create a new project"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO projects (
                    id, type, title, home_workspace_id, flow_id, state,
                    initiator_user_id, human_owner_user_id, ai_pm_id,
                    created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                project.id,
                project.type,
                project.title,
                project.home_workspace_id,
                project.flow_id,
                project.state,
                project.initiator_user_id,
                project.human_owner_user_id,
                project.ai_pm_id,
                self.to_isoformat(project.created_at),
                self.to_isoformat(project.updated_at),
                self.serialize_json(project.metadata) if project.metadata else None
            ))
            conn.commit()
            return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get project by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_project(row)

    def list_projects(
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM projects WHERE 1=1'
            params = []

            if workspace_id:
                query += ' AND home_workspace_id = ?'
                params.append(workspace_id)

            if state:
                query += ' AND state = ?'
                params.append(state)

            if project_type:
                query += ' AND type = ?'
                params.append(project_type)

            query += ' ORDER BY updated_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_project(row) for row in rows]

    def update_project(self, project: Project) -> Project:
        """Update an existing project"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            project.updated_at = _utc_now()
            cursor.execute('''
                UPDATE projects SET
                    type = ?,
                    title = ?,
                    home_workspace_id = ?,
                    flow_id = ?,
                    state = ?,
                    initiator_user_id = ?,
                    human_owner_user_id = ?,
                    ai_pm_id = ?,
                    updated_at = ?,
                    metadata = ?
                WHERE id = ?
            ''', (
                project.type,
                project.title,
                project.home_workspace_id,
                project.flow_id,
                project.state,
                project.initiator_user_id,
                project.human_owner_user_id,
                project.ai_pm_id,
                self.to_isoformat(project.updated_at),
                self.serialize_json(project.metadata) if project.metadata else None,
                project.id
            ))
            conn.commit()
            return project

    def delete_project(self, project_id: str) -> bool:
        """Delete a project"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_project(self, row) -> Project:
        """Convert database row to Project"""
        try:
            metadata = self.deserialize_json(row['metadata'], {}) if row['metadata'] else {}
        except (KeyError, IndexError):
            metadata = {}

        return Project(
            id=row['id'],
            type=row['type'],
            title=row['title'],
            home_workspace_id=row['home_workspace_id'],
            flow_id=row['flow_id'],
            state=row['state'],
            initiator_user_id=row['initiator_user_id'],
            human_owner_user_id=row['human_owner_user_id'] if row['human_owner_user_id'] else None,
            ai_pm_id=row['ai_pm_id'] if row['ai_pm_id'] else None,
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at']),
            metadata=metadata
        )

