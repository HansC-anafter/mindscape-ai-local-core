"""
Artifact Registry Service

Manages artifact registration and tracking within Projects.
Used for flow orchestration and artifact dependency management.
"""

import uuid
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Optional, List
import logging

from backend.app.models.artifact_registry import ArtifactRegistry
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.base import StoreBase

logger = logging.getLogger(__name__)


class ArtifactRegistryStore(StoreBase):
    """Store for managing artifact registry entries"""

    def create_registry_entry(self, entry: ArtifactRegistry) -> ArtifactRegistry:
        """Create a new artifact registry entry"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO artifact_registry (
                    id, project_id, artifact_id, path, type,
                    created_by, dependencies, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entry.id,
                entry.project_id,
                entry.artifact_id,
                entry.path,
                entry.type,
                entry.created_by,
                self.serialize_json(entry.dependencies) if entry.dependencies else None,
                self.to_isoformat(entry.created_at),
                self.to_isoformat(entry.updated_at)
            ))
            conn.commit()
            return entry

    def get_registry_entry(self, entry_id: str) -> Optional[ArtifactRegistry]:
        """Get artifact registry entry by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM artifact_registry WHERE id = ?', (entry_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_registry_entry(row)

    def get_artifact_entry(
        self,
        project_id: str,
        artifact_id: str
    ) -> Optional[ArtifactRegistry]:
        """Get artifact registry entry by project_id and artifact_id"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM artifact_registry WHERE project_id = ? AND artifact_id = ?',
                (project_id, artifact_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_registry_entry(row)

    def list_artifacts_by_project(
        self,
        project_id: str,
        limit: int = 100
    ) -> List[ArtifactRegistry]:
        """List all artifact registry entries for a project"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM artifact_registry WHERE project_id = ? ORDER BY created_at DESC LIMIT ?',
                (project_id, limit)
            )
            rows = cursor.fetchall()
            return [self._row_to_registry_entry(row) for row in rows]

    def list_artifacts_by_node(
        self,
        project_id: str,
        created_by: str
    ) -> List[ArtifactRegistry]:
        """List artifact registry entries created by a specific node"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM artifact_registry WHERE project_id = ? AND created_by = ? ORDER BY created_at DESC',
                (project_id, created_by)
            )
            rows = cursor.fetchall()
            return [self._row_to_registry_entry(row) for row in rows]

    def _row_to_registry_entry(self, row) -> ArtifactRegistry:
        """Convert database row to ArtifactRegistry"""
        try:
            dependencies = self.deserialize_json(row['dependencies'], []) if row['dependencies'] else []
        except (KeyError, IndexError):
            dependencies = []

        return ArtifactRegistry(
            id=row['id'],
            project_id=row['project_id'],
            artifact_id=row['artifact_id'],
            path=row['path'],
            type=row['type'],
            created_by=row['created_by'],
            dependencies=dependencies,
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )


class ArtifactRegistryService:
    """
    Artifact Registry Service - manages artifact registration within Projects

    Provides high-level operations for registering and querying artifacts
    created during flow execution.
    """

    def __init__(self, store: MindscapeStore):
        """
        Initialize Artifact Registry Service

        Args:
            store: MindscapeStore instance
        """
        self.store = store
        self.registry_store = ArtifactRegistryStore(db_path=store.db_path)

    async def register_artifact(
        self,
        project_id: str,
        artifact_id: str,
        path: str,
        artifact_type: str,
        created_by: str,
        dependencies: Optional[List[str]] = None
    ) -> ArtifactRegistry:
        """
        Register an artifact in the project registry

        Args:
            project_id: Project ID
            artifact_id: Artifact identifier
            path: Artifact file path within project sandbox
            artifact_type: Artifact type (markdown, json, html, etc.)
            created_by: Playbook node ID that created this artifact
            dependencies: Optional list of artifact_ids this depends on

        Returns:
            Created ArtifactRegistry entry
        """
        entry_id = f"art_reg_{uuid.uuid4().hex[:12]}"

        entry = ArtifactRegistry(
            id=entry_id,
            project_id=project_id,
            artifact_id=artifact_id,
            path=path,
            type=artifact_type,
            created_by=created_by,
            dependencies=dependencies or [],
            created_at=_utc_now(),
            updated_at=_utc_now()
        )

        self.registry_store.create_registry_entry(entry)
        logger.info(f"Registered artifact {artifact_id} in project {project_id}")

        return entry

    async def get_artifact(
        self,
        project_id: str,
        artifact_id: str
    ) -> Optional[ArtifactRegistry]:
        """
        Get artifact registry entry

        Args:
            project_id: Project ID
            artifact_id: Artifact identifier

        Returns:
            ArtifactRegistry entry or None if not found
        """
        return self.registry_store.get_artifact_entry(project_id, artifact_id)

    async def list_artifacts(
        self,
        project_id: str,
        limit: int = 100
    ) -> List[ArtifactRegistry]:
        """
        List all artifacts for a project

        Args:
            project_id: Project ID
            limit: Maximum number of artifacts to return

        Returns:
            List of ArtifactRegistry entries
        """
        return self.registry_store.list_artifacts_by_project(project_id, limit)

    async def list_artifacts_by_node(
        self,
        project_id: str,
        node_id: str
    ) -> List[ArtifactRegistry]:
        """
        List artifacts created by a specific flow node

        Args:
            project_id: Project ID
            node_id: Flow node ID

        Returns:
            List of ArtifactRegistry entries created by the node
        """
        return self.registry_store.list_artifacts_by_node(project_id, node_id)

    async def get_artifact_dependencies(
        self,
        project_id: str,
        artifact_id: str
    ) -> List[ArtifactRegistry]:
        """
        Get all artifacts that the specified artifact depends on

        Args:
            project_id: Project ID
            artifact_id: Artifact identifier

        Returns:
            List of ArtifactRegistry entries for dependencies
        """
        entry = await self.get_artifact(project_id, artifact_id)
        if not entry or not entry.dependencies:
            return []

        dependencies = []
        for dep_id in entry.dependencies:
            dep_entry = await self.get_artifact(project_id, dep_id)
            if dep_entry:
                dependencies.append(dep_entry)

        return dependencies

