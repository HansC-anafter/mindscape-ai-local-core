"""
Artifacts store for managing playbook output artifacts

Artifacts are automatically created when playbooks complete execution.
All artifact writes go through the /chat flow, ensuring single source of truth.
"""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional, Dict, Any
from backend.app.services.stores.base import StoreBase, StoreNotFoundError
from ...models.workspace import Artifact, ArtifactType, PrimaryActionType

logger = logging.getLogger(__name__)


class ArtifactsStore(StoreBase):
    """Store for managing artifact records"""

    def create_artifact(self, artifact: Artifact) -> Artifact:
        """
        Create a new artifact record

        Args:
            artifact: Artifact model instance

        Returns:
            Created artifact
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO artifacts (
                    id, workspace_id, intent_id, task_id, execution_id, thread_id,
                    playbook_code, artifact_type, title, summary, content,
                    storage_ref, sync_state, primary_action_type, metadata,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    artifact.id,
                    artifact.workspace_id,
                    artifact.intent_id,
                    artifact.task_id,
                    artifact.execution_id,
                    artifact.thread_id,
                    artifact.playbook_code,
                    artifact.artifact_type.value,
                    artifact.title,
                    artifact.summary,
                    self.serialize_json(artifact.content),
                    artifact.storage_ref,
                    artifact.sync_state,
                    artifact.primary_action_type.value,
                    self.serialize_json(artifact.metadata),
                    self.to_isoformat(artifact.created_at),
                    self.to_isoformat(artifact.updated_at),
                ),
            )
            logger.info(
                f"Created artifact: {artifact.id} (workspace: {artifact.workspace_id}, type: {artifact.artifact_type.value})"
            )
            return artifact

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """
        Get artifact by ID

        Args:
            artifact_id: Artifact ID

        Returns:
            Artifact model or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_artifact(row)

    def list_artifacts_by_workspace(
        self, workspace_id: str, limit: Optional[int] = None, offset: int = 0
    ) -> List[Artifact]:
        """
        List artifacts for a workspace

        Args:
            workspace_id: Workspace ID
            limit: Maximum number of items to return (optional)
            offset: Offset for pagination (default: 0)

        Returns:
            List of artifacts, ordered by created_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM artifacts WHERE workspace_id = ? ORDER BY updated_at DESC"
            params = [workspace_id]

            if limit:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            else:
                if offset > 0:
                    query += " OFFSET ?"
                    params.append(offset)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_artifact(row) for row in rows]

    def list_artifacts_by_task(self, task_id: str) -> List[Artifact]:
        """
        List artifacts for a specific task

        Args:
            task_id: Task ID

        Returns:
            List of artifacts for the task
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at DESC",
                (task_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_artifact(row) for row in rows]

    def list_artifacts_by_playbook(
        self, workspace_id: str, playbook_code: str
    ) -> List[Artifact]:
        """
        List artifacts for a specific playbook in a workspace

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code

        Returns:
            List of artifacts for the playbook
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM artifacts WHERE workspace_id = ? AND playbook_code = ? ORDER BY created_at DESC",
                (workspace_id, playbook_code),
            )
            rows = cursor.fetchall()
            return [self._row_to_artifact(row) for row in rows]

    def update_artifact(self, artifact_id: str, **kwargs) -> bool:
        """
        Update artifact fields

        Args:
            artifact_id: Artifact ID
            **kwargs: Fields to update (sync_state, storage_ref, metadata, etc.)

        Returns:
            True if update successful, False otherwise
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                updates = []
                params = []

                # Handle enum fields
                if "artifact_type" in kwargs:
                    updates.append("artifact_type = ?")
                    params.append(
                        kwargs["artifact_type"].value
                        if isinstance(kwargs["artifact_type"], ArtifactType)
                        else kwargs["artifact_type"]
                    )
                if "primary_action_type" in kwargs:
                    updates.append("primary_action_type = ?")
                    params.append(
                        kwargs["primary_action_type"].value
                        if isinstance(kwargs["primary_action_type"], PrimaryActionType)
                        else kwargs["primary_action_type"]
                    )

                # Handle JSON fields
                if "content" in kwargs:
                    updates.append("content = ?")
                    params.append(self.serialize_json(kwargs["content"]))
                if "metadata" in kwargs:
                    updates.append("metadata = ?")
                    params.append(self.serialize_json(kwargs["metadata"]))

                # Handle datetime fields
                if "updated_at" in kwargs:
                    updates.append("updated_at = ?")
                    params.append(self.to_isoformat(kwargs["updated_at"]))
                elif updates:  # Auto-update updated_at if any field is updated
                    updates.append("updated_at = ?")
                    params.append(self.to_isoformat(_utc_now()))

                # Handle other fields
                for key, value in kwargs.items():
                    if key not in [
                        "artifact_type",
                        "primary_action_type",
                        "content",
                        "metadata",
                        "updated_at",
                    ]:
                        updates.append(f"{key} = ?")
                        params.append(value)

                if updates:
                    params.append(artifact_id)
                    query = f'UPDATE artifacts SET {", ".join(updates)} WHERE id = ?'
                    cursor.execute(query, params)
                    return cursor.rowcount > 0
                return False
        except Exception as e:
            logger.error(f"Failed to update artifact {artifact_id}: {e}")
            return False

    def delete_artifact(self, artifact_id: str) -> bool:
        """
        Delete artifact by ID

        Args:
            artifact_id: Artifact ID

        Returns:
            True if deletion successful, False otherwise
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete artifact {artifact_id}: {e}")
            return False

    def get_by_thread(
        self, workspace_id: str, thread_id: str, limit: Optional[int] = 100
    ) -> List[Artifact]:
        """
        Get artifacts for a specific conversation thread

        Args:
            workspace_id: Workspace ID
            thread_id: Thread ID
            limit: Maximum number of artifacts to return (default: 100)

        Returns:
            List of artifacts for the thread, ordered by created_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM artifacts WHERE workspace_id = ? AND thread_id = ? ORDER BY created_at DESC"
            params = [workspace_id, thread_id]

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_artifact(row) for row in rows]

    def _row_to_artifact(self, row) -> Artifact:
        """Convert database row to Artifact model"""
        return Artifact(
            id=row["id"],
            workspace_id=row["workspace_id"],
            intent_id=row["intent_id"] if row["intent_id"] else None,
            task_id=row["task_id"] if row["task_id"] else None,
            execution_id=row["execution_id"] if row["execution_id"] else None,
            thread_id=(
                str(row["thread_id"])
                if "thread_id" in row.keys() and row["thread_id"]
                else None
            ),
            playbook_code=row["playbook_code"],
            artifact_type=ArtifactType(row["artifact_type"]),
            title=row["title"],
            summary=row["summary"] if row["summary"] else "",
            content=self.deserialize_json(row["content"], {}),
            storage_ref=row["storage_ref"] if row["storage_ref"] else None,
            sync_state=row["sync_state"] if row["sync_state"] else None,
            primary_action_type=PrimaryActionType(row["primary_action_type"]),
            metadata=self.deserialize_json(row["metadata"], {}),
            created_at=self.from_isoformat(row["created_at"]),
            updated_at=self.from_isoformat(row["updated_at"]),
        )
