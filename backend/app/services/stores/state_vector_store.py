"""
StateVectorStore — persistence for L3 state vectors.

PostgreSQL store using TEXT IDs aligned with meeting_sessions.id.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.state_vector import StateVector

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS state_vectors (
    id                  TEXT PRIMARY KEY,
    meeting_session_id  TEXT NOT NULL,
    workspace_id        TEXT NOT NULL,
    project_id          TEXT,
    progress            REAL NOT NULL DEFAULT 0,
    evidence            REAL NOT NULL DEFAULT 0,
    risk                REAL NOT NULL DEFAULT 0,
    drift               REAL NOT NULL DEFAULT 0,
    lyapunov_v          REAL NOT NULL DEFAULT 0,
    mode                TEXT NOT NULL DEFAULT 'explore',
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_sv_ws_created ON state_vectors(workspace_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sv_session ON state_vectors(meeting_session_id)",
]


class StateVectorStore(PostgresStoreBase):
    """Postgres store for L3 state vectors."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not StateVectorStore._table_ensured:
            self.ensure_table()
            StateVectorStore._table_ensured = True

    def ensure_table(self) -> None:
        """Create the state_vectors table if needed."""
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        logger.info("state_vectors table ensured")

    # ============== Write ==============

    def create(self, sv: StateVector) -> StateVector:
        """Insert a new state vector."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO state_vectors (
                        id, meeting_session_id, workspace_id, project_id,
                        progress, evidence, risk, drift,
                        lyapunov_v, mode, metadata, created_at
                    ) VALUES (
                        :id, :meeting_session_id, :workspace_id, :project_id,
                        :progress, :evidence, :risk, :drift,
                        :lyapunov_v, :mode, :metadata, :created_at
                    )
                """
                ),
                {
                    "id": sv.id,
                    "meeting_session_id": sv.meeting_session_id,
                    "workspace_id": sv.workspace_id,
                    "project_id": sv.project_id,
                    "progress": sv.progress,
                    "evidence": sv.evidence,
                    "risk": sv.risk,
                    "drift": sv.drift,
                    "lyapunov_v": sv.lyapunov_v,
                    "mode": sv.mode,
                    "metadata": self.serialize_json(sv.metadata),
                    "created_at": sv.created_at,
                },
            )
        return sv

    # ============== Read ==============

    def get_by_session(self, meeting_session_id: str) -> Optional[StateVector]:
        """Get the latest state vector for a meeting session."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM state_vectors
                    WHERE meeting_session_id = :sid
                    ORDER BY created_at DESC LIMIT 1
                """
                ),
                {"sid": meeting_session_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_sv(row)

    def get_latest_by_workspace(
        self,
        workspace_id: str,
        limit: int = 10,
    ) -> List[StateVector]:
        """Get latest state vectors for a workspace."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM state_vectors
                    WHERE workspace_id = :ws
                    ORDER BY created_at DESC LIMIT :limit
                """
                ),
                {"ws": workspace_id, "limit": limit},
            ).fetchall()
            return [self._row_to_sv(r) for r in rows]

    def get_previous(
        self,
        workspace_id: str,
        before: datetime,
    ) -> Optional[StateVector]:
        """Get the state vector immediately before a timestamp."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM state_vectors
                    WHERE workspace_id = :ws AND created_at < :before
                    ORDER BY created_at DESC LIMIT 1
                """
                ),
                {"ws": workspace_id, "before": before},
            ).fetchone()
            if not row:
                return None
            return self._row_to_sv(row)

    # ============== Internal ==============

    @staticmethod
    def _row_data(row) -> Dict[str, Any]:
        return row._mapping if hasattr(row, "_mapping") else row

    def _row_to_sv(self, row) -> StateVector:
        """Convert a database row to StateVector."""
        data = self._row_data(row)
        created = data.get("created_at")
        if created and not isinstance(created, datetime):
            created = datetime.fromisoformat(str(created))
        return StateVector(
            id=data["id"],
            meeting_session_id=data["meeting_session_id"],
            workspace_id=data["workspace_id"],
            project_id=data.get("project_id"),
            timestamp=created or datetime.now(timezone.utc),
            progress=float(data.get("progress", 0)),
            evidence=float(data.get("evidence", 0)),
            risk=float(data.get("risk", 0)),
            drift=float(data.get("drift", 0)),
            lyapunov_v=float(data.get("lyapunov_v", 0)),
            mode=data.get("mode", "explore"),
            metadata=self.deserialize_json(data.get("metadata"), {}),
            created_at=created or datetime.now(timezone.utc),
        )
