"""PostgreSQL implementation of ProjectPhasesStore."""

import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.project import ProjectPhase

logger = logging.getLogger(__name__)


class PostgresProjectPhasesStore(PostgresStoreBase):
    """Postgres implementation of ProjectPhasesStore."""

    def create_phase(
        self,
        phase: ProjectPhase,
        workspace_id: str,
        execution_plan_id: Optional[str] = None,
    ) -> ProjectPhase:
        """Create a new project phase."""
        query = text(
            """
            INSERT INTO project_phases (
                id, workspace_id, project_id, created_at, created_by_message_id,
                execution_plan_id, kind, summary, tags, metadata
            ) VALUES (
                :id, :workspace_id, :project_id, :created_at, :created_by_message_id,
                :execution_plan_id, :kind, :summary, :tags, :metadata
            )
        """
        )
        with self.transaction() as conn:
            conn.execute(
                query,
                {
                    "id": phase.id,
                    "workspace_id": workspace_id,
                    "project_id": phase.project_id,
                    "created_at": phase.created_at,
                    "created_by_message_id": phase.created_by_message_id,
                    "execution_plan_id": execution_plan_id,
                    "kind": phase.kind,
                    "summary": phase.summary,
                    "tags": self.serialize_json(phase.tags) if phase.tags else "[]",
                    "metadata": (
                        self.serialize_json(phase.metadata) if phase.metadata else "{}"
                    ),
                },
            )
        logger.info(
            f"Created phase {phase.id} for project {phase.project_id} "
            f"in workspace {workspace_id}"
        )
        return phase

    def get_phase(self, phase_id: str) -> Optional[ProjectPhase]:
        """Get phase by ID."""
        query = text("SELECT * FROM project_phases WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": phase_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_phase(row)

    def list_phases(self, project_id: str, limit: int = 50) -> List[ProjectPhase]:
        """List phases for a project."""
        query = text(
            "SELECT * FROM project_phases WHERE project_id = :project_id "
            "ORDER BY created_at DESC LIMIT :limit"
        )
        with self.get_connection() as conn:
            result = conn.execute(
                query,
                {
                    "project_id": project_id,
                    "limit": limit,
                },
            )
            rows = result.fetchall()
            return [self._row_to_phase(row) for row in rows]

    def get_recent_phases(self, project_id: str, limit: int = 5) -> List[ProjectPhase]:
        """Get recent phases for a project."""
        return self.list_phases(project_id=project_id, limit=limit)

    def update_phase(self, phase: ProjectPhase) -> ProjectPhase:
        """Update an existing phase."""
        execution_plan_id = None
        if phase.metadata:
            execution_plan_id = phase.metadata.get("execution_plan_id")

        query = text(
            """
            UPDATE project_phases SET
                kind = :kind,
                summary = :summary,
                tags = :tags,
                metadata = :metadata,
                execution_plan_id = :execution_plan_id
            WHERE id = :id
        """
        )
        with self.transaction() as conn:
            conn.execute(
                query,
                {
                    "kind": phase.kind,
                    "summary": phase.summary,
                    "tags": self.serialize_json(phase.tags) if phase.tags else "[]",
                    "metadata": (
                        self.serialize_json(phase.metadata) if phase.metadata else "{}"
                    ),
                    "execution_plan_id": execution_plan_id,
                    "id": phase.id,
                },
            )
        logger.info(f"Updated phase {phase.id}")
        return phase

    def delete_phase(self, phase_id: str) -> bool:
        """Delete a phase."""
        query = text("DELETE FROM project_phases WHERE id = :id")
        with self.transaction() as conn:
            result = conn.execute(query, {"id": phase_id})
            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"Deleted phase {phase_id}")
            return deleted

    def _row_to_phase(self, row) -> ProjectPhase:
        """Convert database row to ProjectPhase."""
        try:
            tags = self.deserialize_json(row.tags, default=[]) if row.tags else []
            metadata = (
                self.deserialize_json(row.metadata, default={}) if row.metadata else {}
            )
            if hasattr(row, "execution_plan_id") and row.execution_plan_id:
                metadata["execution_plan_id"] = row.execution_plan_id
        except Exception as e:
            logger.warning(f"Error parsing phase row data: {e}")
            tags = []
            metadata = {}

        return ProjectPhase(
            id=row.id,
            project_id=row.project_id,
            created_at=row.created_at,
            created_by_message_id=row.created_by_message_id,
            kind=row.kind,
            summary=row.summary,
            tags=tags if isinstance(tags, list) else [],
            metadata=metadata if isinstance(metadata, dict) else {},
        )
