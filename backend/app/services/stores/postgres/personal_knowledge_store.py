"""
PersonalKnowledgeStore — CRUD for personal_knowledge table (mindscape_core DB).

Part of ADR-001 v2 Phase 0 Foundation. L3 self-model storage.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.models.personal_governance.personal_knowledge import (
    PersonalKnowledge,
    KnowledgeStatus,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class PersonalKnowledgeStore(PostgresStoreBase):
    """PostgreSQL store for personal knowledge entries (L3 self-model)."""

    def create(self, entry: PersonalKnowledge) -> PersonalKnowledge:
        """Persist a new personal knowledge entry."""
        query = text(
            """
            INSERT INTO personal_knowledge (
                id, owner_profile_id, knowledge_type, content, status,
                confidence, source_evidence, source_workspace_ids,
                created_at, last_verified_at, expires_at, valid_scope, metadata
            ) VALUES (
                :id, :owner_profile_id, :knowledge_type, :content, :status,
                :confidence, :source_evidence, :source_workspace_ids,
                :created_at, :last_verified_at, :expires_at, :valid_scope, :metadata
            )
        """
        )
        params = {
            "id": entry.id,
            "owner_profile_id": entry.owner_profile_id,
            "knowledge_type": entry.knowledge_type,
            "content": entry.content,
            "status": entry.status,
            "confidence": entry.confidence,
            "source_evidence": self.serialize_json(entry.source_evidence),
            "source_workspace_ids": self.serialize_json(entry.source_workspace_ids),
            "created_at": entry.created_at,
            "last_verified_at": entry.last_verified_at,
            "expires_at": entry.expires_at,
            "valid_scope": entry.valid_scope,
            "metadata": self.serialize_json(entry.metadata),
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        return entry

    def get(self, entry_id: str) -> Optional[PersonalKnowledge]:
        """Get a single entry by ID."""
        query = text("SELECT * FROM personal_knowledge WHERE id = :id")
        with self.get_connection() as conn:
            row = conn.execute(query, {"id": entry_id}).fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    def list_by_owner(
        self,
        owner_profile_id: str,
        knowledge_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[PersonalKnowledge]:
        """List entries for an owner, optionally filtered by type and status."""
        base = "SELECT * FROM personal_knowledge WHERE owner_profile_id = :owner"
        params: Dict[str, Any] = {"owner": owner_profile_id}

        if knowledge_type:
            base += " AND knowledge_type = :ktype"
            params["ktype"] = knowledge_type

        if status:
            base += " AND status = :status"
            params["status"] = status

        base += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(base), params).fetchall()
            return [self._row_to_entry(r) for r in rows]

    def list_active(self, owner_profile_id: str) -> List[PersonalKnowledge]:
        """List only verified/active entries for prompt injection."""
        return self.list_by_owner(
            owner_profile_id, status=KnowledgeStatus.VERIFIED.value
        )

    def list_by_canonical_memory_item(
        self, source_memory_item_id: str, *, limit: int = 50
    ) -> List[PersonalKnowledge]:
        """List entries projected from a canonical memory item."""
        query = text(
            """
            SELECT * FROM personal_knowledge
            WHERE metadata::jsonb -> 'canonical_projection' ->> 'source_memory_item_id' = :source_memory_item_id
            ORDER BY created_at DESC
            LIMIT :limit
            """
        )
        with self.get_connection() as conn:
            rows = conn.execute(
                query,
                {
                    "source_memory_item_id": source_memory_item_id,
                    "limit": limit,
                },
            ).fetchall()
            return [self._row_to_entry(r) for r in rows]

    def update_status(
        self,
        entry_id: str,
        new_status: str,
        last_verified_at: Optional[datetime] = None,
    ) -> bool:
        """Update status of an entry (used for verification, deprecation)."""
        updates = ["status = :status"]
        params: Dict[str, Any] = {"id": entry_id, "status": new_status}

        if last_verified_at:
            updates.append("last_verified_at = :verified_at")
            params["verified_at"] = last_verified_at

        query = text(
            f"UPDATE personal_knowledge SET {', '.join(updates)} WHERE id = :id"
        )
        with self.transaction() as conn:
            result = conn.execute(query, params)
            return result.rowcount > 0

    def update(self, entry: PersonalKnowledge) -> bool:
        query = text(
            """
            UPDATE personal_knowledge SET
                knowledge_type = :knowledge_type,
                content = :content,
                status = :status,
                confidence = :confidence,
                source_evidence = :source_evidence,
                source_workspace_ids = :source_workspace_ids,
                last_verified_at = :last_verified_at,
                expires_at = :expires_at,
                valid_scope = :valid_scope,
                metadata = :metadata
            WHERE id = :id
            """
        )
        params = {
            "id": entry.id,
            "knowledge_type": entry.knowledge_type,
            "content": entry.content,
            "status": entry.status,
            "confidence": entry.confidence,
            "source_evidence": self.serialize_json(entry.source_evidence),
            "source_workspace_ids": self.serialize_json(entry.source_workspace_ids),
            "last_verified_at": entry.last_verified_at,
            "expires_at": entry.expires_at,
            "valid_scope": entry.valid_scope,
            "metadata": self.serialize_json(entry.metadata),
        }
        with self.transaction() as conn:
            result = conn.execute(query, params)
            return result.rowcount > 0

    def find_similar_content(
        self, owner_profile_id: str, content: str, threshold: float = 0.85
    ) -> Optional[PersonalKnowledge]:
        """Check for duplicate content (basic text match, not vector similarity)."""
        # Note: Vector-based similarity will be done in vectors DB.
        # This is a fast pre-check using trigram or exact substring.
        query = text(
            """
            SELECT * FROM personal_knowledge
            WHERE owner_profile_id = :owner
              AND status NOT IN ('deprecated')
              AND content = :content
            LIMIT 1
        """
        )
        with self.get_connection() as conn:
            row = conn.execute(
                query, {"owner": owner_profile_id, "content": content}
            ).fetchone()
            if row:
                return self._row_to_entry(row)
            return None

    def count_candidates_since(
        self, owner_profile_id: str, workspace_id: str, since: datetime
    ) -> int:
        """Count candidates from a workspace since a date (for throttling)."""
        query = text(
            """
            SELECT COUNT(*) as cnt FROM personal_knowledge
            WHERE owner_profile_id = :owner
              AND status = 'candidate'
              AND source_workspace_ids::jsonb @> :ws_json::jsonb
              AND created_at >= :since
        """
        )
        with self.get_connection() as conn:
            row = conn.execute(
                query,
                {
                    "owner": owner_profile_id,
                    "ws_json": f'["{workspace_id}"]',
                    "since": since,
                },
            ).fetchone()
            return row.cnt if row else 0

    def expire_stale_candidates(
        self, owner_profile_id: str, stale_days: int = 30
    ) -> int:
        """Mark candidates older than stale_days as stale."""
        query = text(
            """
            UPDATE personal_knowledge
            SET status = 'stale'
            WHERE owner_profile_id = :owner
              AND status = 'candidate'
              AND created_at < now() - :interval::interval
        """
        )
        with self.transaction() as conn:
            result = conn.execute(
                query,
                {
                    "owner": owner_profile_id,
                    "interval": f"{stale_days} days",
                },
            )
            return result.rowcount

    def _row_to_entry(self, row) -> PersonalKnowledge:
        return PersonalKnowledge(
            id=row.id,
            owner_profile_id=row.owner_profile_id,
            knowledge_type=row.knowledge_type,
            content=row.content,
            status=row.status,
            confidence=row.confidence,
            source_evidence=self.deserialize_json(row.source_evidence, default=[]),
            source_workspace_ids=self.deserialize_json(
                row.source_workspace_ids, default=[]
            ),
            created_at=row.created_at,
            last_verified_at=row.last_verified_at,
            expires_at=row.expires_at,
            valid_scope=row.valid_scope,
            metadata=self.deserialize_json(row.metadata, default={}),
        )
