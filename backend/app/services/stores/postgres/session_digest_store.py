"""
SessionDigestStore — CRUD for session_digests table (mindscape_core DB).

Part of ADR-001 v2 Phase 0 Foundation.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.models.personal_governance.session_digest import SessionDigest
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class SessionDigestStore(PostgresStoreBase):
    """PostgreSQL store for session digests (L1→L2 bridge)."""

    def create(self, digest: SessionDigest) -> SessionDigest:
        """Persist a new session digest."""
        query = text(
            """
            INSERT INTO session_digests (
                id, source_type, source_id, source_time_start, source_time_end,
                digest_version, owner_profile_id, workspace_refs, project_refs,
                participants, summary_md, claims, actions, decisions,
                embedding_text, provenance_refs, sensitivity, created_at, metadata
            ) VALUES (
                :id, :source_type, :source_id, :source_time_start, :source_time_end,
                :digest_version, :owner_profile_id, :workspace_refs, :project_refs,
                :participants, :summary_md, :claims, :actions, :decisions,
                :embedding_text, :provenance_refs, :sensitivity, :created_at, :metadata
            )
        """
        )
        params = {
            "id": digest.id,
            "source_type": digest.source_type,
            "source_id": digest.source_id,
            "source_time_start": digest.source_time_start,
            "source_time_end": digest.source_time_end,
            "digest_version": digest.digest_version,
            "owner_profile_id": digest.owner_profile_id,
            "workspace_refs": self.serialize_json(digest.workspace_refs),
            "project_refs": self.serialize_json(digest.project_refs),
            "participants": self.serialize_json(digest.participants),
            "summary_md": digest.summary_md,
            "claims": self.serialize_json(digest.claims),
            "actions": self.serialize_json(digest.actions),
            "decisions": self.serialize_json(digest.decisions),
            "embedding_text": digest.embedding_text,
            "provenance_refs": self.serialize_json(digest.provenance_refs),
            "sensitivity": digest.sensitivity,
            "created_at": digest.created_at,
            "metadata": self.serialize_json(digest.metadata),
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        return digest

    def get(self, digest_id: str) -> Optional[SessionDigest]:
        """Get a single digest by ID."""
        query = text("SELECT * FROM session_digests WHERE id = :id")
        with self.get_connection() as conn:
            row = conn.execute(query, {"id": digest_id}).fetchone()
            if not row:
                return None
            return self._row_to_digest(row)

    def list_by_owner(
        self,
        owner_profile_id: str,
        source_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[SessionDigest]:
        """List digests for an owner, optionally filtered."""
        base = "SELECT * FROM session_digests WHERE owner_profile_id = :owner"
        params: Dict[str, Any] = {"owner": owner_profile_id}

        if source_type:
            base += " AND source_type = :source_type"
            params["source_type"] = source_type

        if since:
            base += " AND created_at >= :since"
            params["since"] = since

        base += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(base), params).fetchall()
            return [self._row_to_digest(r) for r in rows]

    def list_by_ids(self, digest_ids: List[str]) -> List[SessionDigest]:
        """Fetch multiple digests by ID list."""
        if not digest_ids:
            return []
        placeholders = ", ".join(f":id{i}" for i in range(len(digest_ids)))
        query = text(f"SELECT * FROM session_digests WHERE id IN ({placeholders})")
        params = {f"id{i}": did for i, did in enumerate(digest_ids)}
        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_digest(r) for r in rows]

    def get_by_source(self, source_type: str, source_id: str) -> Optional[SessionDigest]:
        """Get the latest digest for a given source identity."""
        query = text(
            """
            SELECT * FROM session_digests
            WHERE source_type = :source_type AND source_id = :source_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        with self.get_connection() as conn:
            row = conn.execute(
                query,
                {"source_type": source_type, "source_id": source_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_digest(row)

    def count_since(self, owner_profile_id: str, since: datetime) -> int:
        """Count digests since a given time (for cooldown checks)."""
        query = text(
            """
            SELECT COUNT(*) as cnt FROM session_digests
            WHERE owner_profile_id = :owner AND created_at >= :since
        """
        )
        with self.get_connection() as conn:
            row = conn.execute(
                query, {"owner": owner_profile_id, "since": since}
            ).fetchone()
            return row.cnt if row else 0

    def _row_to_digest(self, row) -> SessionDigest:
        return SessionDigest(
            id=row.id,
            source_type=row.source_type,
            source_id=row.source_id,
            source_time_start=row.source_time_start,
            source_time_end=row.source_time_end,
            digest_version=row.digest_version,
            owner_profile_id=row.owner_profile_id,
            workspace_refs=self.deserialize_json(row.workspace_refs, default=[]),
            project_refs=self.deserialize_json(row.project_refs, default=[]),
            participants=self.deserialize_json(row.participants, default=[]),
            summary_md=row.summary_md,
            claims=self.deserialize_json(row.claims, default=[]),
            actions=self.deserialize_json(row.actions, default=[]),
            decisions=self.deserialize_json(row.decisions, default=[]),
            embedding_text=row.embedding_text,
            provenance_refs=self.deserialize_json(row.provenance_refs, default=[]),
            sensitivity=row.sensitivity,
            created_at=row.created_at,
            metadata=self.deserialize_json(row.metadata, default={}),
        )
