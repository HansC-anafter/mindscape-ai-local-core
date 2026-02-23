"""
Reasoning traces store for SGR (Self-Graph Reasoning) integration.

PostgreSQL store for persisting and querying reasoning graphs.
This store is the single source of truth for reasoning graph data.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from app.models.reasoning_trace import ReasoningTrace

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS reasoning_traces (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL,
    execution_id       TEXT,
    assistant_event_id TEXT,
    graph_json         JSONB NOT NULL,
    schema_version     INTEGER NOT NULL DEFAULT 1,
    sgr_mode           VARCHAR(20) NOT NULL DEFAULT 'inline',
    model              VARCHAR(100),
    token_count        INTEGER,
    latency_ms         INTEGER,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    parent_trace_id    TEXT,
    supersedes         TEXT,
    meeting_session_id TEXT,
    device_id          TEXT,
    remote_parent_trace_id TEXT
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_workspace ON reasoning_traces(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_exec ON reasoning_traces(execution_id)",
    "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_event ON reasoning_traces(assistant_event_id)",
    "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_created ON reasoning_traces(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_parent ON reasoning_traces(parent_trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_session ON reasoning_traces(meeting_session_id)",
    "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_device ON reasoning_traces(device_id)",
    "CREATE INDEX IF NOT EXISTS idx_reasoning_traces_remote_parent ON reasoning_traces(remote_parent_trace_id)",
]


class ReasoningTracesStore(PostgresStoreBase):
    """Store for SGR reasoning trace persistence (Postgres)."""

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)

    def ensure_table(self) -> None:
        """Create the reasoning_traces table if it does not exist."""
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        logger.info("reasoning_traces table ensured")

    # ============== Write ==============

    def create(self, trace: ReasoningTrace) -> ReasoningTrace:
        """Insert a new reasoning trace."""
        import json as _json

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO reasoning_traces (
                        id, workspace_id, execution_id, assistant_event_id,
                        graph_json, schema_version, sgr_mode, model,
                        token_count, latency_ms, created_at,
                        parent_trace_id, supersedes, meeting_session_id,
                        device_id, remote_parent_trace_id
                    ) VALUES (
                        :id, :workspace_id, :execution_id, :assistant_event_id,
                        :graph_json, :schema_version, :sgr_mode, :model,
                        :token_count, :latency_ms, :created_at,
                        :parent_trace_id, :supersedes, :meeting_session_id,
                        :device_id, :remote_parent_trace_id
                    )
                """
                ),
                {
                    "id": trace.id,
                    "workspace_id": trace.workspace_id,
                    "execution_id": trace.execution_id,
                    "assistant_event_id": trace.assistant_event_id,
                    "graph_json": self.serialize_json(trace.graph_json),
                    "schema_version": trace.schema_version,
                    "sgr_mode": trace.sgr_mode,
                    "model": trace.model,
                    "token_count": trace.token_count,
                    "latency_ms": trace.latency_ms,
                    "created_at": trace.created_at,
                    "parent_trace_id": trace.parent_trace_id,
                    "supersedes": (
                        _json.dumps(trace.supersedes) if trace.supersedes else None
                    ),
                    "meeting_session_id": trace.meeting_session_id,
                    "device_id": trace.device_id,
                    "remote_parent_trace_id": trace.remote_parent_trace_id,
                },
            )
        return trace

    # ============== Read ==============

    def get_by_id(self, trace_id: str) -> Optional[ReasoningTrace]:
        """Get a reasoning trace by ID."""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM reasoning_traces WHERE id = :id"),
                {"id": trace_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_trace(row)

    def get_by_execution_id(self, execution_id: str) -> Optional[ReasoningTrace]:
        """Get the most recent reasoning trace for an execution.

        Returns the latest trace if multiple exist for the same execution.
        """
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM reasoning_traces
                    WHERE execution_id = :execution_id
                    ORDER BY created_at DESC LIMIT 1
                """
                ),
                {"execution_id": execution_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_trace(row)

    def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReasoningTrace]:
        """List reasoning traces for a workspace, newest first."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM reasoning_traces
                    WHERE workspace_id = :workspace_id
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """
                ),
                {"workspace_id": workspace_id, "limit": limit, "offset": offset},
            ).fetchall()
            return [self._row_to_trace(r) for r in rows]

    def update_field(self, trace_id: str, field: str, value: Any) -> None:
        """Update a single field on a reasoning trace (used for backfill)."""
        allowed_fields = {"assistant_event_id", "execution_id", "meeting_session_id"}
        if field not in allowed_fields:
            raise ValueError(f"Field '{field}' is not allowed for update")
        with self.transaction() as conn:
            conn.execute(
                text(f"UPDATE reasoning_traces SET {field} = :value WHERE id = :id"),
                {"id": trace_id, "value": value},
            )

    def get_by_execution_id_and_workspace(
        self, execution_id: str, workspace_id: str
    ) -> Optional[ReasoningTrace]:
        """Get trace by execution_id scoped to workspace (prevents cross-workspace access)."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM reasoning_traces
                    WHERE execution_id = :execution_id AND workspace_id = :workspace_id
                    ORDER BY created_at DESC LIMIT 1
                """
                ),
                {"execution_id": execution_id, "workspace_id": workspace_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_trace(row)

    # ============== Internal ==============

    @staticmethod
    def _row_data(row) -> Dict[str, Any]:
        return row._mapping if hasattr(row, "_mapping") else row

    def _row_to_trace(self, row) -> ReasoningTrace:
        """Convert a database row to a ReasoningTrace."""
        import json as _json

        data = self._row_data(row)
        # Parse supersedes from JSON string
        supersedes_raw = data.get("supersedes")
        supersedes = None
        if supersedes_raw:
            try:
                supersedes = (
                    _json.loads(supersedes_raw)
                    if isinstance(supersedes_raw, str)
                    else supersedes_raw
                )
            except (ValueError, TypeError):
                supersedes = None

        return ReasoningTrace(
            id=data["id"],
            workspace_id=data["workspace_id"],
            execution_id=data.get("execution_id"),
            assistant_event_id=data.get("assistant_event_id"),
            graph_json=self.deserialize_json(data["graph_json"], {}),
            schema_version=data.get("schema_version", 1),
            sgr_mode=data.get("sgr_mode", "inline"),
            model=data.get("model"),
            token_count=data.get("token_count"),
            latency_ms=data.get("latency_ms"),
            created_at=(
                data["created_at"]
                if isinstance(data["created_at"], datetime)
                else datetime.fromisoformat(str(data["created_at"]))
            ),
            parent_trace_id=data.get("parent_trace_id"),
            supersedes=supersedes,
            meeting_session_id=data.get("meeting_session_id"),
            device_id=data.get("device_id"),
            remote_parent_trace_id=data.get("remote_parent_trace_id"),
        )

    # ============== G4: Trace Versioning ==============

    def get_trace_chain(self, trace_id: str) -> List[ReasoningTrace]:
        """Get the full parent chain for a trace (newest first)."""
        chain = []
        current_id = trace_id
        seen = set()
        while current_id and current_id not in seen:
            seen.add(current_id)
            trace = self.get_by_id(current_id)
            if not trace:
                break
            chain.append(trace)
            current_id = trace.parent_trace_id
        return chain

    def get_by_session(self, meeting_session_id: str) -> List[ReasoningTrace]:
        """Get all traces for a meeting session."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM reasoning_traces
                    WHERE meeting_session_id = :session_id
                    ORDER BY created_at ASC
                """
                ),
                {"session_id": meeting_session_id},
            ).fetchall()
            return [self._row_to_trace(r) for r in rows]
