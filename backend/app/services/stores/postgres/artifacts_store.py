"""Postgres adaptation of ArtifactsStore."""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import List, Optional
from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from ..artifacts_store import ArtifactsStore

logger = logging.getLogger(__name__)


class PostgresArtifactsStore(PostgresStoreBase):
    """Postgres implementation of ArtifactsStore."""

    def create_artifact(self, artifact: Artifact) -> Artifact:
        """Create a new artifact record."""
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO artifacts (
                    id, workspace_id, intent_id, task_id, execution_id, thread_id,
                    playbook_code, artifact_type, title, summary, content,
                    storage_ref, sync_state, primary_action_type, metadata,
                    created_at, updated_at
                ) VALUES (
                    :id, :workspace_id, :intent_id, :task_id, :execution_id, :thread_id,
                    :playbook_code, :artifact_type, :title, :summary, :content,
                    :storage_ref, :sync_state, :primary_action_type, :metadata,
                    :created_at, :updated_at
                )
            """
            )
            params = {
                "id": artifact.id,
                "workspace_id": artifact.workspace_id,
                "intent_id": artifact.intent_id,
                "task_id": artifact.task_id,
                "execution_id": artifact.execution_id,
                "thread_id": artifact.thread_id,
                "playbook_code": artifact.playbook_code,
                "artifact_type": artifact.artifact_type.value,
                "title": artifact.title,
                "summary": artifact.summary,
                "content": self.serialize_json(artifact.content),
                "storage_ref": artifact.storage_ref,
                "sync_state": artifact.sync_state,
                "primary_action_type": artifact.primary_action_type.value,
                "metadata": self.serialize_json(artifact.metadata),
                "created_at": artifact.created_at,
                "updated_at": artifact.updated_at,
            }
            conn.execute(query, params)
            logger.info(
                f"Created artifact: {artifact.id} (workspace: {artifact.workspace_id}, type: {artifact.artifact_type.value})"
            )
            return artifact

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """Get artifact by ID."""
        with self.get_connection() as conn:
            query = text("SELECT * FROM artifacts WHERE id = :id")
            result = conn.execute(query, {"id": artifact_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_artifact(row)

    def get_by_execution_id(self, execution_id: str) -> Optional[Artifact]:
        """Get artifact by execution_id (returns most recent if multiple)."""
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM artifacts WHERE execution_id = :execution_id "
                "ORDER BY updated_at DESC LIMIT 1"
            )
            result = conn.execute(query, {"execution_id": execution_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_artifact(row)

    def list_artifacts_by_workspace(
        self, workspace_id: str, limit: Optional[int] = None, offset: int = 0
    ) -> List[Artifact]:
        """List artifacts for a workspace."""
        with self.get_connection() as conn:
            query_str = "SELECT * FROM artifacts WHERE workspace_id = :workspace_id ORDER BY updated_at DESC"
            params = {"workspace_id": workspace_id}

            if limit:
                query_str += " LIMIT :limit OFFSET :offset"
                params["limit"] = limit
                params["offset"] = offset
            elif offset > 0:
                query_str += " OFFSET :offset"
                params["offset"] = offset

            result = conn.execute(text(query_str), params)
            rows = result.fetchall()
            return [self._row_to_artifact(row) for row in rows]

    def list_artifacts_by_task(self, task_id: str) -> List[Artifact]:
        """List artifacts for a specific task."""
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM artifacts WHERE task_id = :task_id ORDER BY updated_at DESC"
            )
            result = conn.execute(query, {"task_id": task_id})
            rows = result.fetchall()
            return [self._row_to_artifact(row) for row in rows]

    def list_artifacts_by_playbook(
        self, workspace_id: str, playbook_code: str
    ) -> List[Artifact]:
        """List artifacts for a specific playbook."""
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM artifacts WHERE workspace_id = :workspace_id AND playbook_code = :playbook_code ORDER BY updated_at DESC"
            )
            result = conn.execute(
                query, {"workspace_id": workspace_id, "playbook_code": playbook_code}
            )
            rows = result.fetchall()
            return [self._row_to_artifact(row) for row in rows]

    def update_artifact(self, artifact_id: str, **kwargs) -> bool:
        """Update artifact fields."""
        try:
            with self.transaction() as conn:
                set_clauses = []
                params = {"id": artifact_id}

                # Handle enum fields
                if "artifact_type" in kwargs:
                    set_clauses.append("artifact_type = :artifact_type")
                    if hasattr(kwargs["artifact_type"], "value"):
                        params["artifact_type"] = kwargs["artifact_type"].value
                    else:
                        params["artifact_type"] = kwargs["artifact_type"]

                if "primary_action_type" in kwargs:
                    set_clauses.append("primary_action_type = :primary_action_type")
                    if hasattr(kwargs["primary_action_type"], "value"):
                        params["primary_action_type"] = kwargs[
                            "primary_action_type"
                        ].value
                    else:
                        params["primary_action_type"] = kwargs["primary_action_type"]

                # Handle JSON fields
                if "content" in kwargs:
                    set_clauses.append("content = :content")
                    params["content"] = self.serialize_json(kwargs["content"])
                if "metadata" in kwargs:
                    set_clauses.append("metadata = :metadata")
                    params["metadata"] = self.serialize_json(kwargs["metadata"])

                # Handle datetime fields
                if "updated_at" in kwargs:
                    set_clauses.append("updated_at = :updated_at")
                    params["updated_at"] = kwargs["updated_at"]
                elif set_clauses:  # Auto-update updated_at if any field is updated
                    set_clauses.append("updated_at = :updated_at")
                    params["updated_at"] = _utc_now()

                # Handle other fields
                for key, value in kwargs.items():
                    if key not in [
                        "artifact_type",
                        "primary_action_type",
                        "content",
                        "metadata",
                        "updated_at",
                    ]:
                        set_clauses.append(f"{key} = :{key}")
                        params[key] = value

                if set_clauses:
                    query = text(
                        f'UPDATE artifacts SET {", ".join(set_clauses)} WHERE id = :id'
                    )
                    result = conn.execute(query, params)
                    return result.rowcount > 0
                return False
        except Exception as e:
            logger.error(f"Failed to update artifact {artifact_id}: {e}")
            return False

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete artifact by ID."""
        try:
            with self.transaction() as conn:
                query = text("DELETE FROM artifacts WHERE id = :id")
                result = conn.execute(query, {"id": artifact_id})
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete artifact {artifact_id}: {e}")
            return False

    def get_by_thread(
        self, workspace_id: str, thread_id: str, limit: Optional[int] = 100
    ) -> List[Artifact]:
        """Get artifacts for a specific conversation thread."""
        with self.get_connection() as conn:
            query_str = "SELECT * FROM artifacts WHERE workspace_id = :workspace_id AND thread_id = :thread_id ORDER BY updated_at DESC"
            params = {"workspace_id": workspace_id, "thread_id": thread_id}

            if limit:
                query_str += " LIMIT :limit"
                params["limit"] = limit

            result = conn.execute(text(query_str), params)
            rows = result.fetchall()
            return [self._row_to_artifact(row) for row in rows]

    def _row_to_artifact(self, row) -> Artifact:
        """Convert database row to Artifact model."""
        return Artifact(
            id=row.id,
            workspace_id=row.workspace_id,
            intent_id=row.intent_id,
            task_id=row.task_id,
            execution_id=row.execution_id,
            thread_id=row.thread_id,
            playbook_code=row.playbook_code,
            artifact_type=ArtifactType(row.artifact_type),
            title=row.title,
            summary=row.summary if row.summary else "",
            content=self.deserialize_json(row.content, {}),
            storage_ref=row.storage_ref,
            sync_state=row.sync_state,
            primary_action_type=PrimaryActionType(row.primary_action_type),
            metadata=self.deserialize_json(row.metadata, {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
