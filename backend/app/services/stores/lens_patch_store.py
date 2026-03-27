"""
LensPatch store for L2 Bridge versioned persona updates.

PostgreSQL store for persisting LensPatch records, supporting
version chain queries for L3 Drift(P_t, P_{t-1}) computation.

Matches LensPatch model fields:
  id, lens_id, meeting_session_id, delta, evidence_refs, confidence,
  status, rollback_to, lens_version_before, lens_version_after,
  approved_by, rejection_reason, metadata, created_at, resolved_at
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.lens_patch import LensPatch, PatchStatus

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS lens_patches (
    id                   TEXT PRIMARY KEY,
    lens_id              TEXT NOT NULL,
    meeting_session_id   TEXT NOT NULL,
    delta                JSONB NOT NULL DEFAULT '{}',
    evidence_refs        JSONB DEFAULT '[]',
    confidence           FLOAT NOT NULL DEFAULT 0.0,
    status               TEXT NOT NULL DEFAULT 'proposed',
    rollback_to          TEXT,
    lens_version_before  INTEGER NOT NULL DEFAULT 0,
    lens_version_after   INTEGER,
    approved_by          TEXT,
    rejection_reason     TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at          TIMESTAMPTZ,
    metadata             JSONB DEFAULT '{}'
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_lens_patches_lens ON lens_patches(lens_id)",
    "CREATE INDEX IF NOT EXISTS idx_lens_patches_session ON lens_patches(meeting_session_id)",
    "CREATE INDEX IF NOT EXISTS idx_lens_patches_chain ON lens_patches(lens_id, lens_version_before)",
]

ALTER_DDL = [
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS delta JSONB NOT NULL DEFAULT '{}'",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS evidence_refs JSONB DEFAULT '[]'",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS confidence FLOAT NOT NULL DEFAULT 0.0",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'proposed'",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS rollback_to TEXT",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS lens_version_before INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS lens_version_after INTEGER",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS approved_by TEXT",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS rejection_reason TEXT",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ",
    "ALTER TABLE lens_patches ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'",
]


class LensPatchStore(PostgresStoreBase):
    """Store for LensPatch persistence with version chain support (Postgres)."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not LensPatchStore._table_ensured:
            self.ensure_table()
            LensPatchStore._table_ensured = True

    def ensure_table(self) -> None:
        """Create table if it does not exist."""
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for ddl in ALTER_DDL:
                conn.execute(text(ddl))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        logger.info("lens_patches table ensured")

    # ============== Write ==============

    def create(self, patch: LensPatch) -> LensPatch:
        """Insert a new LensPatch."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO lens_patches (
                        id, lens_id, meeting_session_id,
                        delta, evidence_refs, confidence, status,
                        rollback_to, lens_version_before, lens_version_after,
                        approved_by, rejection_reason,
                        created_at, resolved_at, metadata
                    ) VALUES (
                        :id, :lens_id, :meeting_session_id,
                        :delta, :evidence_refs, :confidence, :status,
                        :rollback_to, :lens_version_before, :lens_version_after,
                        :approved_by, :rejection_reason,
                        :created_at, :resolved_at, :metadata
                    )
                """
                ),
                self._patch_to_params(patch),
            )
        return patch

    def update_status(
        self,
        patch_id: str,
        status: PatchStatus,
        approved_by: Optional[str] = None,
        rejection_reason: Optional[str] = None,
    ) -> Optional[LensPatch]:
        """Update patch status (approve/reject/rollback)."""
        from datetime import timezone

        now = datetime.now(tz=timezone.utc)
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE lens_patches SET
                        status = :status,
                        approved_by = :approved_by,
                        rejection_reason = :rejection_reason,
                        resolved_at = :resolved_at
                    WHERE id = :id
                """
                ),
                {
                    "id": patch_id,
                    "status": status.value,
                    "approved_by": approved_by,
                    "rejection_reason": rejection_reason,
                    "resolved_at": now,
                },
            )
        return self.get_by_id(patch_id)

    # ============== Read ==============

    def get_by_id(self, patch_id: str) -> Optional[LensPatch]:
        """Get a LensPatch by ID."""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM lens_patches WHERE id = :id"),
                {"id": patch_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_patch(row)

    def get_version_chain(self, lens_id: str, limit: int = 20) -> List[LensPatch]:
        """Get the version chain for a lens, ordered by version descending."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM lens_patches
                    WHERE lens_id = :lid
                    ORDER BY lens_version_before DESC LIMIT :lim
                """
                ),
                {"lid": lens_id, "lim": limit},
            ).fetchall()
            return [self._row_to_patch(r) for r in rows]

    def get_by_session(self, meeting_session_id: str) -> List[LensPatch]:
        """Get all patches created during a meeting session."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM lens_patches
                    WHERE meeting_session_id = :sid
                    ORDER BY lens_version_before ASC
                """
                ),
                {"sid": meeting_session_id},
            ).fetchall()
            return [self._row_to_patch(r) for r in rows]

    def get_latest_for_lens(self, lens_id: str) -> Optional[LensPatch]:
        """Get the most recent patch for a lens."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM lens_patches
                    WHERE lens_id = :lid
                    ORDER BY lens_version_before DESC LIMIT 1
                """
                ),
                {"lid": lens_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_patch(row)

    # ============== Internal ==============

    def _patch_to_params(self, patch: LensPatch) -> Dict[str, Any]:
        """Convert LensPatch to parameter dict."""
        return {
            "id": patch.id,
            "lens_id": patch.lens_id,
            "meeting_session_id": patch.meeting_session_id,
            "delta": self.serialize_json(patch.delta),
            "evidence_refs": self.serialize_json(patch.evidence_refs),
            "confidence": patch.confidence,
            "status": (
                patch.status.value
                if hasattr(patch.status, "value")
                else str(patch.status)
            ),
            "rollback_to": patch.rollback_to,
            "lens_version_before": patch.lens_version_before,
            "lens_version_after": patch.lens_version_after,
            "approved_by": patch.approved_by,
            "rejection_reason": patch.rejection_reason,
            "created_at": patch.created_at,
            "resolved_at": patch.resolved_at,
            "metadata": self.serialize_json(patch.metadata),
        }

    def _row_to_patch(self, row) -> LensPatch:
        """Convert a database row to LensPatch."""
        data = row._mapping if hasattr(row, "_mapping") else row

        status_raw = data.get("status", PatchStatus.PROPOSED.value)
        try:
            status = PatchStatus(status_raw)
        except Exception:
            status = PatchStatus.PROPOSED

        created_at = data["created_at"]
        if not isinstance(created_at, datetime):
            created_at = datetime.fromisoformat(str(created_at))

        resolved_at = data.get("resolved_at")
        if resolved_at and not isinstance(resolved_at, datetime):
            resolved_at = datetime.fromisoformat(str(resolved_at))

        return LensPatch(
            id=data["id"],
            lens_id=data["lens_id"],
            meeting_session_id=data["meeting_session_id"],
            delta=self.deserialize_json(data.get("delta"), {}),
            evidence_refs=self.deserialize_json(data.get("evidence_refs"), []),
            confidence=data.get("confidence", 0.0),
            status=status,
            rollback_to=data.get("rollback_to"),
            lens_version_before=data.get("lens_version_before", 0),
            lens_version_after=data.get("lens_version_after"),
            approved_by=data.get("approved_by"),
            rejection_reason=data.get("rejection_reason"),
            metadata=self.deserialize_json(data.get("metadata"), {}),
            created_at=created_at,
            resolved_at=resolved_at,
        )
