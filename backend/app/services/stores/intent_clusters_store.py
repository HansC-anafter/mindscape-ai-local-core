"""
Intent Clusters Store Service

Handles storage and retrieval of IntentCluster records.
"""

import logging
from typing import List, Optional
from datetime import datetime

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from ...models.mindscape import IntentCluster

logger = logging.getLogger(__name__)


class IntentClustersStore(PostgresStoreBase):
    """Store for IntentCluster records (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def create_cluster(self, cluster: IntentCluster) -> IntentCluster:
        """Create a new IntentCluster"""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO intent_clusters (
                        id, label, embedding, workspace_id, profile_id,
                        intent_card_ids, metadata, created_at, updated_at
                    ) VALUES (
                        :id, :label, :embedding, :workspace_id, :profile_id,
                        :intent_card_ids, :metadata, :created_at, :updated_at
                    )
                """
                ),
                {
                    "id": cluster.id,
                    "label": cluster.label,
                    "embedding": self.serialize_json(cluster.embedding)
                    if cluster.embedding
                    else None,
                    "workspace_id": cluster.workspace_id,
                    "profile_id": cluster.profile_id,
                    "intent_card_ids": self.serialize_json(cluster.intent_card_ids),
                    "metadata": self.serialize_json(cluster.metadata),
                    "created_at": cluster.created_at,
                    "updated_at": cluster.updated_at,
                },
            )
            return cluster

    def get_cluster(self, cluster_id: str) -> Optional[IntentCluster]:
        """Get IntentCluster by ID"""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM intent_clusters WHERE id = :id"),
                {"id": cluster_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_cluster(row)

    def list_clusters(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[IntentCluster]:
        """List IntentClusters with filters"""
        with self.get_connection() as conn:
            query = "SELECT * FROM intent_clusters WHERE 1=1"
            params = {"limit": limit}

            if workspace_id:
                query += " AND workspace_id = :workspace_id"
                params["workspace_id"] = workspace_id
            if profile_id:
                query += " AND profile_id = :profile_id"
                params["profile_id"] = profile_id

            query += " ORDER BY updated_at DESC LIMIT :limit"

            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_cluster(row) for row in rows]

    def update_cluster(self, cluster: IntentCluster) -> Optional[IntentCluster]:
        """Update an existing IntentCluster"""
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE intent_clusters SET
                        label = :label, embedding = :embedding, intent_card_ids = :intent_card_ids,
                        metadata = :metadata, updated_at = :updated_at
                    WHERE id = :id
                """
                ),
                {
                    "label": cluster.label,
                    "embedding": self.serialize_json(cluster.embedding)
                    if cluster.embedding
                    else None,
                    "intent_card_ids": self.serialize_json(cluster.intent_card_ids),
                    "metadata": self.serialize_json(cluster.metadata),
                    "updated_at": cluster.updated_at,
                    "id": cluster.id,
                },
            )

            if result.rowcount > 0:
                return cluster
            return None

    def delete_cluster(self, cluster_id: str) -> bool:
        """Delete an IntentCluster"""
        with self.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM intent_clusters WHERE id = :id"),
                {"id": cluster_id},
            )
            return result.rowcount > 0

    def _row_to_cluster(self, row) -> IntentCluster:
        """Convert database row to IntentCluster"""
        data = row._mapping if hasattr(row, "_mapping") else row

        embedding = None
        if data["embedding"] is not None:
            embedding = self.deserialize_json(data["embedding"], None)

        return IntentCluster(
            id=data["id"],
            label=data["label"],
            embedding=embedding,
            workspace_id=data["workspace_id"],
            profile_id=data["profile_id"],
            intent_card_ids=self.deserialize_json(data["intent_card_ids"], []),
            metadata=self.deserialize_json(data["metadata"], {}),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
