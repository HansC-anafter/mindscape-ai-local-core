"""PostgreSQL implementation of ArtifactRegistryStore."""

import logging
from typing import Optional, List
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.artifact_registry import ArtifactRegistry

logger = logging.getLogger(__name__)


class PostgresArtifactRegistryStore(PostgresStoreBase):
    """Postgres implementation of ArtifactRegistryStore."""

    def create_registry_entry(self, entry: ArtifactRegistry) -> ArtifactRegistry:
        """Create a new artifact registry entry."""
        query = text(
            """
            INSERT INTO artifact_registry (
                id, project_id, artifact_id, path, type,
                created_by, dependencies, created_at, updated_at
            ) VALUES (
                :id, :project_id, :artifact_id, :path, :type,
                :created_by, :dependencies, :created_at, :updated_at
            )
        """
        )
        with self.transaction() as conn:
            conn.execute(
                query,
                {
                    "id": entry.id,
                    "project_id": entry.project_id,
                    "artifact_id": entry.artifact_id,
                    "path": entry.path,
                    "type": entry.type,
                    "created_by": entry.created_by,
                    "dependencies": (
                        self.serialize_json(entry.dependencies)
                        if entry.dependencies
                        else None
                    ),
                    "created_at": entry.created_at,
                    "updated_at": entry.updated_at,
                },
            )
        return entry

    def get_registry_entry(self, entry_id: str) -> Optional[ArtifactRegistry]:
        """Get artifact registry entry by ID."""
        query = text("SELECT * FROM artifact_registry WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": entry_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_registry_entry(row)

    def get_artifact_entry(
        self, project_id: str, artifact_id: str
    ) -> Optional[ArtifactRegistry]:
        """Get artifact registry entry by project_id and artifact_id."""
        query = text(
            "SELECT * FROM artifact_registry "
            "WHERE project_id = :project_id AND artifact_id = :artifact_id"
        )
        with self.get_connection() as conn:
            result = conn.execute(
                query,
                {
                    "project_id": project_id,
                    "artifact_id": artifact_id,
                },
            )
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_registry_entry(row)

    def list_artifacts_by_project(
        self, project_id: str, limit: int = 100
    ) -> List[ArtifactRegistry]:
        """List all artifact registry entries for a project."""
        query = text(
            "SELECT * FROM artifact_registry "
            "WHERE project_id = :project_id "
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
            return [self._row_to_registry_entry(row) for row in rows]

    def list_artifacts_by_node(
        self, project_id: str, created_by: str
    ) -> List[ArtifactRegistry]:
        """List artifact registry entries created by a specific node."""
        query = text(
            "SELECT * FROM artifact_registry "
            "WHERE project_id = :project_id AND created_by = :created_by "
            "ORDER BY created_at DESC"
        )
        with self.get_connection() as conn:
            result = conn.execute(
                query,
                {
                    "project_id": project_id,
                    "created_by": created_by,
                },
            )
            rows = result.fetchall()
            return [self._row_to_registry_entry(row) for row in rows]

    def _row_to_registry_entry(self, row) -> ArtifactRegistry:
        """Convert database row to ArtifactRegistry."""
        deps = (
            self.deserialize_json(row.dependencies, default=[])
            if row.dependencies
            else []
        )
        return ArtifactRegistry(
            id=row.id,
            project_id=row.project_id,
            artifact_id=row.artifact_id,
            path=row.path,
            type=row.type,
            created_by=row.created_by,
            dependencies=deps,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
