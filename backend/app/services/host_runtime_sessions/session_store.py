"""Postgres store for host runtime sessions, turns, and persisted events."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

from .artifact_provenance import build_artifact_provenance_ref, requires_artifact_provenance
from .models import (
    CANONICAL_EVENT_TYPES,
    MAX_PERSISTED_EVENT_PAYLOAD_BYTES,
    TOKEN_DELTA_EVENT_TYPES,
    HostRuntimeEvent,
    HostRuntimeSession,
    HostRuntimeTurn,
    utc_now,
)

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS host_runtime_sessions (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    actor_id TEXT NULL,
    runtime_surface TEXT NOT NULL DEFAULT 'codex_cli',
    runtime_id TEXT NOT NULL,
    bridge_id TEXT NULL,
    app_server_thread_id TEXT NULL,
    status TEXT NOT NULL,
    cwd TEXT NOT NULL,
    created_by TEXT NULL,
    active_turn_id TEXT NULL,
    last_event_seq BIGINT NOT NULL DEFAULT 0,
    governance_trace_ref TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    terminal_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS host_runtime_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES host_runtime_sessions(id) ON DELETE CASCADE,
    workspace_id TEXT NOT NULL,
    status TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    compiled_prompt_hash TEXT NULL,
    intent_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    lens_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    context_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    artifact_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    approval_audit_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    governance_trace_ref TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    terminal_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS host_runtime_events (
    id BIGSERIAL PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES host_runtime_sessions(id) ON DELETE CASCADE,
    turn_id TEXT NULL,
    seq BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    item_id TEXT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(session_id, seq)
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_host_runtime_sessions_workspace_updated ON host_runtime_sessions(workspace_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_host_runtime_sessions_workspace_meeting_updated ON host_runtime_sessions(workspace_id, ((metadata->>'meeting_id')), updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_host_runtime_turns_workspace_session_started ON host_runtime_turns(workspace_id, session_id, started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_host_runtime_events_workspace_session_seq ON host_runtime_events(workspace_id, session_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_host_runtime_turns_governance_trace ON host_runtime_turns(workspace_id, governance_trace_ref)",
]


class HostRuntimePayloadBudgetError(ValueError):
    pass


class HostRuntimeSessionStore(PostgresStoreBase):
    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not HostRuntimeSessionStore._table_ensured:
            self.ensure_table()
            HostRuntimeSessionStore._table_ensured = True

    def ensure_table(self) -> None:
        with self.transaction() as conn:
            for statement in [item.strip() for item in TABLE_DDL.split(";") if item.strip()]:
                conn.execute(text(statement))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        logger.info("host_runtime session tables ensured")

    def create_session(self, session: HostRuntimeSession) -> HostRuntimeSession:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO host_runtime_sessions (
                        id, execution_id, workspace_id, actor_id, runtime_surface,
                        runtime_id, bridge_id, app_server_thread_id, status, cwd,
                        created_by, active_turn_id, last_event_seq, governance_trace_ref,
                        metadata, created_at, updated_at, terminal_at
                    ) VALUES (
                        :id, :execution_id, :workspace_id, :actor_id, :runtime_surface,
                        :runtime_id, :bridge_id, :app_server_thread_id, :status, :cwd,
                        :created_by, :active_turn_id, :last_event_seq, :governance_trace_ref,
                        CAST(:metadata AS JSONB), :created_at, :updated_at, :terminal_at
                    )
                    """
                ),
                {
                    **session.model_dump(mode="python"),
                    "metadata": self.serialize_json(session.metadata),
                },
            )
        return session

    def get_session(self, workspace_id: str, session_id: str) -> HostRuntimeSession | None:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM host_runtime_sessions
                    WHERE workspace_id = :workspace_id AND id = :session_id
                    """
                ),
                {"workspace_id": workspace_id, "session_id": session_id},
            ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self, workspace_id: str, limit: int = 20) -> list[HostRuntimeSession]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM host_runtime_sessions
                    WHERE workspace_id = :workspace_id
                    ORDER BY updated_at DESC
                    LIMIT :limit
                    """
                ),
                {"workspace_id": workspace_id, "limit": limit},
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def list_sessions_by_meeting(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        limit: int = 10,
    ) -> list[HostRuntimeSession]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM host_runtime_sessions
                    WHERE workspace_id = :workspace_id
                      AND metadata->>'meeting_id' = :meeting_id
                    ORDER BY updated_at DESC
                    LIMIT :limit
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "meeting_id": meeting_id,
                    "limit": limit,
                },
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def create_turn(self, turn: HostRuntimeTurn) -> HostRuntimeTurn:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO host_runtime_turns (
                        id, session_id, workspace_id, status, prompt_hash,
                        compiled_prompt_hash, intent_ref, lens_ref, policy_ref,
                        context_ref, artifact_ref, approval_audit_ref,
                        governance_trace_ref, started_at, terminal_at
                    ) VALUES (
                        :id, :session_id, :workspace_id, :status, :prompt_hash,
                        :compiled_prompt_hash, CAST(:intent_ref AS JSONB),
                        CAST(:lens_ref AS JSONB), CAST(:policy_ref AS JSONB),
                        CAST(:context_ref AS JSONB), CAST(:artifact_ref AS JSONB),
                        CAST(:approval_audit_ref AS JSONB),
                        :governance_trace_ref, :started_at, :terminal_at
                    )
                    """
                ),
                {
                    **turn.model_dump(mode="python"),
                    "intent_ref": self.serialize_json(turn.intent_ref),
                    "lens_ref": self.serialize_json(turn.lens_ref),
                    "policy_ref": self.serialize_json(turn.policy_ref),
                    "context_ref": self.serialize_json(turn.context_ref),
                    "artifact_ref": self.serialize_json(turn.artifact_ref),
                    "approval_audit_ref": self.serialize_json(turn.approval_audit_ref),
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE host_runtime_sessions
                    SET active_turn_id = :turn_id,
                        status = 'running',
                        updated_at = :updated_at,
                        governance_trace_ref = COALESCE(governance_trace_ref, :governance_trace_ref)
                    WHERE id = :session_id AND workspace_id = :workspace_id
                    """
                ),
                {
                    "turn_id": turn.id,
                    "session_id": turn.session_id,
                    "workspace_id": turn.workspace_id,
                    "updated_at": utc_now(),
                    "governance_trace_ref": turn.governance_trace_ref,
                },
            )
        return turn

    def append_event(self, event: HostRuntimeEvent) -> HostRuntimeEvent:
        if event.event_type not in CANONICAL_EVENT_TYPES:
            raise ValueError(f"Unsupported host runtime event type: {event.event_type}")
        if event.event_type in TOKEN_DELTA_EVENT_TYPES:
            raise HostRuntimePayloadBudgetError(
                f"{event.event_type} is stream-only and must not be persisted"
            )
        self._validate_payload_budget(event.payload)

        with self.transaction() as conn:
            seq_row = conn.execute(
                text(
                    """
                    UPDATE host_runtime_sessions
                    SET last_event_seq = last_event_seq + 1,
                        updated_at = :updated_at
                    WHERE id = :session_id AND workspace_id = :workspace_id
                    RETURNING last_event_seq
                    """
                ),
                {
                    "session_id": event.session_id,
                    "workspace_id": event.workspace_id,
                    "updated_at": utc_now(),
                },
            ).fetchone()
            if not seq_row:
                raise ValueError(f"Unknown host runtime session: {event.session_id}")
            seq = int(seq_row[0])
            row = conn.execute(
                text(
                    """
                    INSERT INTO host_runtime_events (
                        workspace_id, session_id, turn_id, seq, event_type,
                        item_id, payload, created_at
                    ) VALUES (
                        :workspace_id, :session_id, :turn_id, :seq, :event_type,
                        :item_id, CAST(:payload AS JSONB), :created_at
                    )
                    RETURNING id
                    """
                ),
                {
                    "workspace_id": event.workspace_id,
                    "session_id": event.session_id,
                    "turn_id": event.turn_id,
                    "seq": seq,
                    "event_type": event.event_type,
                    "item_id": event.item_id,
                    "payload": self.serialize_json(event.payload),
                    "created_at": event.created_at,
                },
            ).fetchone()
            event.seq = seq
            event.id = int(row[0]) if row else None
            self._apply_terminal_updates(conn, event)
        return event

    def list_events(
        self,
        *,
        workspace_id: str,
        session_id: str,
        after_seq: int = 0,
        limit: int = 500,
    ) -> list[HostRuntimeEvent]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM host_runtime_events
                    WHERE workspace_id = :workspace_id
                      AND session_id = :session_id
                      AND seq > :after_seq
                    ORDER BY seq ASC
                    LIMIT :limit
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "session_id": session_id,
                    "after_seq": after_seq,
                    "limit": limit,
                },
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def mark_bridge_unavailable(
        self,
        *,
        workspace_id: str,
        session_id: str,
        turn_id: str,
    ) -> None:
        now = utc_now()
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE host_runtime_turns
                    SET status = 'bridge_unavailable', terminal_at = :now
                    WHERE id = :turn_id AND session_id = :session_id AND workspace_id = :workspace_id
                    """
                ),
                {"now": now, "turn_id": turn_id, "session_id": session_id, "workspace_id": workspace_id},
            )
            conn.execute(
                text(
                    """
                    UPDATE host_runtime_sessions
                    SET status = 'bridge_unavailable',
                        active_turn_id = NULL,
                        updated_at = :now
                    WHERE id = :session_id AND workspace_id = :workspace_id
                    """
                ),
                {"now": now, "session_id": session_id, "workspace_id": workspace_id},
            )

    def _apply_terminal_updates(self, conn: Any, event: HostRuntimeEvent) -> None:
        if not event.turn_id:
            return
        now = utc_now()
        if requires_artifact_provenance(event.event_type, event.payload):
            provenance = build_artifact_provenance_ref(
                workspace_id=event.workspace_id,
                session_id=event.session_id,
                turn_id=event.turn_id,
                artifact_ref=event.payload.get("artifact_ref"),
            )
            conn.execute(
                text(
                    """
                    UPDATE host_runtime_turns
                    SET artifact_ref = CAST(:artifact_ref AS JSONB)
                    WHERE id = :turn_id AND session_id = :session_id
                    """
                ),
                {
                    "artifact_ref": self.serialize_json(provenance),
                    "turn_id": event.turn_id,
                    "session_id": event.session_id,
                },
            )
        if event.event_type == "turn.completed":
            self._mark_turn_terminal(conn, event, "completed", now)
        elif event.event_type == "turn.failed":
            self._mark_turn_terminal(conn, event, "failed", now)
        elif event.event_type == "session.interrupted":
            self._mark_turn_terminal(conn, event, "interrupted", now, session_status="interrupted")
        elif event.event_type == "approval.requested":
            conn.execute(
                text(
                    """
                    UPDATE host_runtime_turns
                    SET status = 'approval_required'
                    WHERE id = :turn_id AND session_id = :session_id
                    """
                ),
                {"turn_id": event.turn_id, "session_id": event.session_id},
            )

    def _mark_turn_terminal(
        self,
        conn: Any,
        event: HostRuntimeEvent,
        turn_status: str,
        now: Any,
        *,
        session_status: str = "ready",
    ) -> None:
        conn.execute(
            text(
                """
                UPDATE host_runtime_turns
                SET status = :turn_status,
                    terminal_at = :now
                WHERE id = :turn_id AND session_id = :session_id
                """
            ),
            {
                "turn_status": turn_status,
                "now": now,
                "turn_id": event.turn_id,
                "session_id": event.session_id,
            },
        )
        conn.execute(
            text(
                """
                UPDATE host_runtime_sessions
                SET status = :session_status,
                    active_turn_id = NULL,
                    updated_at = :now
                WHERE id = :session_id AND workspace_id = :workspace_id
                """
            ),
            {
                "session_status": session_status,
                "now": now,
                "session_id": event.session_id,
                "workspace_id": event.workspace_id,
            },
        )

    def _validate_payload_budget(self, payload: dict[str, Any]) -> None:
        payload_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if payload_bytes > MAX_PERSISTED_EVENT_PAYLOAD_BYTES:
            raise HostRuntimePayloadBudgetError(
                f"host runtime event payload exceeds {MAX_PERSISTED_EVENT_PAYLOAD_BYTES} bytes"
            )

    def _row_to_session(self, row: Any) -> HostRuntimeSession:
        data = dict(row._mapping)
        data["metadata"] = self.deserialize_json(data.get("metadata"), {})
        return HostRuntimeSession(**data)

    def _row_to_event(self, row: Any) -> HostRuntimeEvent:
        data = dict(row._mapping)
        data["payload"] = self.deserialize_json(data.get("payload"), {})
        return HostRuntimeEvent(**data)
