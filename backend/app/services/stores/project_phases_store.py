"""
Project Phases store for Mindscape data persistence
Handles project phase CRUD operations
"""

from datetime import datetime
from typing import List, Optional
from backend.app.services.stores.base import StoreBase
from backend.app.models.project import ProjectPhase
import logging

logger = logging.getLogger(__name__)


class ProjectPhasesStore(StoreBase):
    """Store for managing project phases"""

    def create_phase(self, phase: ProjectPhase, workspace_id: str, execution_plan_id: Optional[str] = None) -> ProjectPhase:
        """
        Create a new project phase

        Args:
            phase: ProjectPhase object
            workspace_id: Workspace ID (for database organization)
            execution_plan_id: Optional execution plan ID to link this phase

        Returns:
            Created ProjectPhase
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO project_phases (
                    id, workspace_id, project_id, created_at, created_by_message_id,
                    execution_plan_id, kind, summary, tags, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                phase.id,
                workspace_id,
                phase.project_id,
                self.to_isoformat(phase.created_at),
                phase.created_by_message_id,
                execution_plan_id,
                phase.kind,
                phase.summary,
                self.serialize_json(phase.tags) if phase.tags else '[]',
                self.serialize_json(phase.metadata) if phase.metadata else '{}'
            ))
            conn.commit()
            logger.info(f"Created phase {phase.id} for project {phase.project_id} in workspace {workspace_id}")
            return phase

    def get_phase(self, phase_id: str) -> Optional[ProjectPhase]:
        """
        Get phase by ID

        Args:
            phase_id: Phase ID

        Returns:
            ProjectPhase or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM project_phases WHERE id = ?', (phase_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_phase(row)

    def list_phases(
        self,
        project_id: str,
        limit: int = 50
    ) -> List[ProjectPhase]:
        """
        List phases for a project

        Args:
            project_id: Project ID
            limit: Maximum number of phases to return

        Returns:
            List of ProjectPhase objects, ordered by created_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM project_phases
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (project_id, limit))
            rows = cursor.fetchall()
            return [self._row_to_phase(row) for row in rows]

    def get_recent_phases(
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
            List of recent ProjectPhase objects, ordered by created_at DESC
        """
        return self.list_phases(project_id=project_id, limit=limit)

    def update_phase(self, phase: ProjectPhase) -> ProjectPhase:
        """
        Update an existing phase

        Args:
            phase: ProjectPhase object with updated fields

        Returns:
            Updated ProjectPhase
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Extract execution_plan_id from metadata if present, but don't rely on it for the column
            execution_plan_id = None
            if phase.metadata:
                execution_plan_id = phase.metadata.get('execution_plan_id')

            cursor.execute('''
                UPDATE project_phases SET
                    kind = ?,
                    summary = ?,
                    tags = ?,
                    metadata = ?,
                    execution_plan_id = ?
                WHERE id = ?
            ''', (
                phase.kind,
                phase.summary,
                self.serialize_json(phase.tags) if phase.tags else '[]',
                self.serialize_json(phase.metadata) if phase.metadata else '{}',
                execution_plan_id,
                phase.id
            ))
            conn.commit()
            logger.info(f"Updated phase {phase.id}")
            return phase

    def delete_phase(self, phase_id: str) -> bool:
        """
        Delete a phase

        Args:
            phase_id: Phase ID

        Returns:
            True if deleted, False if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM project_phases WHERE id = ?', (phase_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_phase(self, row) -> ProjectPhase:
        """Convert database row to ProjectPhase"""
        try:
            tags = self.deserialize_json(row['tags'], []) if row['tags'] else []
            metadata = self.deserialize_json(row['metadata'], {}) if row['metadata'] else {}

            # Add execution_plan_id to metadata if present
            if row.get('execution_plan_id'):
                metadata['execution_plan_id'] = row['execution_plan_id']
        except (KeyError, IndexError) as e:
            logger.warning(f"Error parsing phase row data: {e}")
            tags = []
            metadata = {}

        return ProjectPhase(
            id=row['id'],
            project_id=row['project_id'],
            created_at=self.from_isoformat(row['created_at']),
            created_by_message_id=row['created_by_message_id'],
            kind=row['kind'],
            summary=row['summary'],
            tags=tags if isinstance(tags, list) else [],
            metadata=metadata if isinstance(metadata, dict) else {}
        )

