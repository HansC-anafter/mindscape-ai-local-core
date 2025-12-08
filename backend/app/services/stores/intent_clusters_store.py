"""
Intent Clusters Store Service

Handles storage and retrieval of IntentCluster records.
"""

import json
import sqlite3
import logging
from typing import List, Optional
from datetime import datetime

from ...models.mindscape import IntentCluster
from ...services.stores.base import StoreBase

logger = logging.getLogger(__name__)


class IntentClustersStore(StoreBase):
    """Store for IntentCluster records"""

    def create_cluster(self, cluster: IntentCluster) -> IntentCluster:
        """
        Create a new IntentCluster

        Args:
            cluster: IntentCluster model instance

        Returns:
            Created IntentCluster
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS intent_clusters (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    embedding TEXT,
                    workspace_id TEXT,
                    profile_id TEXT,
                    intent_card_ids TEXT,
                    metadata TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')

            cursor.execute('''
                INSERT INTO intent_clusters (
                    id, label, embedding, workspace_id, profile_id,
                    intent_card_ids, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                cluster.id,
                cluster.label,
                json.dumps(cluster.embedding) if cluster.embedding else None,
                cluster.workspace_id,
                cluster.profile_id,
                json.dumps(cluster.intent_card_ids),
                json.dumps(cluster.metadata),
                self.to_isoformat(cluster.created_at),
                self.to_isoformat(cluster.updated_at)
            ))
            conn.commit()
            return cluster

    def get_cluster(self, cluster_id: str) -> Optional[IntentCluster]:
        """
        Get IntentCluster by ID

        Args:
            cluster_id: Cluster ID

        Returns:
            IntentCluster or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM intent_clusters WHERE id = ?', (cluster_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_cluster(row)

    def list_clusters(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        limit: int = 100
    ) -> List[IntentCluster]:
        """
        List IntentClusters with filters

        Args:
            workspace_id: Filter by workspace ID
            profile_id: Filter by profile ID
            limit: Maximum number of results

        Returns:
            List of IntentClusters
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM intent_clusters WHERE 1=1'
            params = []

            if workspace_id:
                query += ' AND workspace_id = ?'
                params.append(workspace_id)
            if profile_id:
                query += ' AND profile_id = ?'
                params.append(profile_id)

            query += ' ORDER BY updated_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_cluster(row) for row in rows]

    def update_cluster(self, cluster: IntentCluster) -> Optional[IntentCluster]:
        """
        Update an existing IntentCluster

        Args:
            cluster: IntentCluster with updated data

        Returns:
            Updated IntentCluster or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE intent_clusters SET
                    label = ?, embedding = ?, intent_card_ids = ?,
                    metadata = ?, updated_at = ?
                WHERE id = ?
            ''', (
                cluster.label,
                json.dumps(cluster.embedding) if cluster.embedding else None,
                json.dumps(cluster.intent_card_ids),
                json.dumps(cluster.metadata),
                self.to_isoformat(cluster.updated_at),
                cluster.id
            ))
            conn.commit()

            if cursor.rowcount > 0:
                return cluster
            return None

    def delete_cluster(self, cluster_id: str) -> bool:
        """
        Delete an IntentCluster

        Args:
            cluster_id: Cluster ID

        Returns:
            True if deletion succeeded
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM intent_clusters WHERE id = ?', (cluster_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_cluster(self, row) -> IntentCluster:
        """Convert database row to IntentCluster"""
        embedding = None
        if row['embedding']:
            try:
                embedding = json.loads(row['embedding'])
            except Exception:
                pass

        return IntentCluster(
            id=row['id'],
            label=row['label'],
            embedding=embedding,
            workspace_id=row['workspace_id'],
            profile_id=row['profile_id'],
            intent_card_ids=self.deserialize_json(row['intent_card_ids'], []),
            metadata=self.deserialize_json(row['metadata'], {}),
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )

