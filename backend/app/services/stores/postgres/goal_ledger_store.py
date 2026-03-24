"""
GoalLedgerStore — CRUD for goal_ledger table (mindscape_core DB).

Part of ADR-001 v2 Phase 0 Foundation. L3 goal tracking with transaction-log semantics.
Enforces writeback policy cooldown rules.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.models.personal_governance.goal_ledger import GoalLedgerEntry
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class GoalLedgerStore(PostgresStoreBase):
    """PostgreSQL store for goal ledger entries (L3)."""

    def create(self, entry: GoalLedgerEntry) -> GoalLedgerEntry:
        """Persist a new goal ledger entry."""
        query = text(
            """
            INSERT INTO goal_ledger (
                id, owner_profile_id, title, description, status, horizon,
                source_digest_ids, source_session_ids, related_knowledge_ids,
                last_updated_at, update_count, created_at,
                last_mentioned_at, confirmed_at, metadata
            ) VALUES (
                :id, :owner_profile_id, :title, :description, :status, :horizon,
                :source_digest_ids, :source_session_ids, :related_knowledge_ids,
                :last_updated_at, :update_count, :created_at,
                :last_mentioned_at, :confirmed_at, :metadata
            )
        """
        )
        params = {
            "id": entry.id,
            "owner_profile_id": entry.owner_profile_id,
            "title": entry.title,
            "description": entry.description,
            "status": entry.status,
            "horizon": entry.horizon,
            "source_digest_ids": self.serialize_json(entry.source_digest_ids),
            "source_session_ids": self.serialize_json(entry.source_session_ids),
            "related_knowledge_ids": self.serialize_json(entry.related_knowledge_ids),
            "last_updated_at": entry.last_updated_at,
            "update_count": entry.update_count,
            "created_at": entry.created_at,
            "last_mentioned_at": entry.last_mentioned_at,
            "confirmed_at": entry.confirmed_at,
            "metadata": self.serialize_json(entry.metadata),
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        return entry

    def get(self, entry_id: str) -> Optional[GoalLedgerEntry]:
        """Get a single goal by ID."""
        query = text("SELECT * FROM goal_ledger WHERE id = :id")
        with self.get_connection() as conn:
            row = conn.execute(query, {"id": entry_id}).fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    def list_by_owner(
        self,
        owner_profile_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[GoalLedgerEntry]:
        """List goals for an owner, optionally filtered by status."""
        base = "SELECT * FROM goal_ledger WHERE owner_profile_id = :owner"
        params: Dict[str, Any] = {"owner": owner_profile_id}

        if status:
            base += " AND status = :status"
            params["status"] = status

        base += " ORDER BY last_updated_at DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(base), params).fetchall()
            return [self._row_to_entry(r) for r in rows]

    def list_active(self, owner_profile_id: str) -> List[GoalLedgerEntry]:
        """List only active goals (for prompt injection / anchored extraction)."""
        return self.list_by_owner(owner_profile_id, status="active")

    def list_by_canonical_memory_item(
        self, source_memory_item_id: str, *, limit: int = 50
    ) -> List[GoalLedgerEntry]:
        """List goal entries projected from a canonical memory item."""
        query = text(
            """
            SELECT * FROM goal_ledger
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

    def update(self, entry: GoalLedgerEntry) -> bool:
        """Full update of a goal entry (after transition_to)."""
        query = text(
            """
            UPDATE goal_ledger SET
                title = :title, description = :description,
                status = :status, horizon = :horizon,
                source_digest_ids = :source_digest_ids,
                source_session_ids = :source_session_ids,
                related_knowledge_ids = :related_knowledge_ids,
                last_updated_at = :last_updated_at,
                update_count = :update_count,
                last_mentioned_at = :last_mentioned_at,
                confirmed_at = :confirmed_at,
                metadata = :metadata
            WHERE id = :id
        """
        )
        params = {
            "id": entry.id,
            "title": entry.title,
            "description": entry.description,
            "status": entry.status,
            "horizon": entry.horizon,
            "source_digest_ids": self.serialize_json(entry.source_digest_ids),
            "source_session_ids": self.serialize_json(entry.source_session_ids),
            "related_knowledge_ids": self.serialize_json(entry.related_knowledge_ids),
            "last_updated_at": entry.last_updated_at,
            "update_count": entry.update_count,
            "last_mentioned_at": entry.last_mentioned_at,
            "confirmed_at": entry.confirmed_at,
            "metadata": self.serialize_json(entry.metadata),
        }
        with self.transaction() as conn:
            result = conn.execute(query, params)
            return result.rowcount > 0

    def count_active(self, owner_profile_id: str) -> int:
        """Count active goals (for max-per-session checks)."""
        query = text(
            """
            SELECT COUNT(*) as cnt FROM goal_ledger
            WHERE owner_profile_id = :owner AND status = 'active'
        """
        )
        with self.get_connection() as conn:
            row = conn.execute(query, {"owner": owner_profile_id}).fetchone()
            return row.cnt if row else 0

    def _row_to_entry(self, row) -> GoalLedgerEntry:
        return GoalLedgerEntry(
            id=row.id,
            owner_profile_id=row.owner_profile_id,
            title=row.title,
            description=row.description,
            status=row.status,
            horizon=row.horizon,
            source_digest_ids=self.deserialize_json(row.source_digest_ids, default=[]),
            source_session_ids=self.deserialize_json(
                row.source_session_ids, default=[]
            ),
            related_knowledge_ids=self.deserialize_json(
                row.related_knowledge_ids, default=[]
            ),
            last_updated_at=row.last_updated_at,
            update_count=row.update_count,
            created_at=row.created_at,
            last_mentioned_at=row.last_mentioned_at,
            confirmed_at=row.confirmed_at,
            metadata=self.deserialize_json(row.metadata, default={}),
        )
