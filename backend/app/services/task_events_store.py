"""Task event ledger and transactional outbox storage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskEventsStore(PostgresStoreBase):
    """Persist append-only task events and outbox records."""

    def append_task_event(
        self,
        *,
        task_id: str,
        workspace_id: str,
        event_type: str,
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
        run_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        summary: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        conn=None,
    ) -> str:
        event_id = f"task_evt_{uuid4().hex}"
        event_payload = self.serialize_json(payload or {})
        resolved_idempotency_key = idempotency_key or event_id
        params = {
            "event_id": event_id,
            "task_id": task_id,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "workspace_id": workspace_id,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "summary": summary,
            "payload": event_payload,
            "idempotency_key": resolved_idempotency_key,
            "occurred_at": occurred_at or _utc_now(),
        }
        query = text(
            """
            INSERT INTO task_events (
                event_id,
                task_id,
                run_id,
                attempt_id,
                workspace_id,
                event_type,
                from_status,
                to_status,
                summary,
                payload,
                idempotency_key,
                occurred_at
            )
            VALUES (
                :event_id,
                :task_id,
                :run_id,
                :attempt_id,
                :workspace_id,
                :event_type,
                :from_status,
                :to_status,
                :summary,
                CAST(:payload AS JSONB),
                :idempotency_key,
                :occurred_at
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING event_id
            """
        )
        active_conn = conn
        if active_conn is not None:
            row = active_conn.execute(query, params).fetchone()
            if row:
                return row[0]
            return self._event_id_for_idempotency_key(
                resolved_idempotency_key,
                conn=active_conn,
            )
        with self.transaction() as owned_conn:
            row = owned_conn.execute(query, params).fetchone()
            if row:
                return row[0]
            return self._event_id_for_idempotency_key(
                resolved_idempotency_key,
                conn=owned_conn,
            )

    def append_outbox_event(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        available_at: Optional[datetime] = None,
        conn=None,
    ) -> str:
        outbox_id = f"outbox_{uuid4().hex}"
        event_payload = self.serialize_json(payload or {})
        resolved_idempotency_key = idempotency_key or outbox_id
        params = {
            "outbox_id": outbox_id,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "payload": event_payload,
            "available_at": available_at or _utc_now(),
            "idempotency_key": resolved_idempotency_key,
        }
        query = text(
            """
            INSERT INTO outbox_events (
                outbox_id,
                aggregate_type,
                aggregate_id,
                event_type,
                payload,
                available_at,
                idempotency_key
            )
            VALUES (
                :outbox_id,
                :aggregate_type,
                :aggregate_id,
                :event_type,
                CAST(:payload AS JSONB),
                :available_at,
                :idempotency_key
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING outbox_id
            """
        )
        active_conn = conn
        if active_conn is not None:
            row = active_conn.execute(query, params).fetchone()
            if row:
                return row[0]
            return self._outbox_id_for_idempotency_key(
                resolved_idempotency_key,
                conn=active_conn,
            )
        with self.transaction() as owned_conn:
            row = owned_conn.execute(query, params).fetchone()
            if row:
                return row[0]
            return self._outbox_id_for_idempotency_key(
                resolved_idempotency_key,
                conn=owned_conn,
            )

    def record_task_event(
        self,
        *,
        task_id: str,
        workspace_id: str,
        event_type: str,
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
        run_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        summary: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        conn=None,
    ) -> str:
        event_id = self.append_task_event(
            task_id=task_id,
            workspace_id=workspace_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            run_id=run_id,
            attempt_id=attempt_id,
            summary=summary,
            payload=payload,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
            conn=conn,
        )
        self.append_outbox_event(
            aggregate_type="task",
            aggregate_id=task_id,
            event_type="task.projection.refresh_requested",
            payload={
                "event_id": event_id,
                "task_id": task_id,
                "workspace_id": workspace_id,
            },
            idempotency_key=f"outbox:{idempotency_key or event_id}",
            available_at=occurred_at,
            conn=conn,
        )
        return event_id

    def _event_id_for_idempotency_key(self, idempotency_key: str, *, conn) -> str:
        row = conn.execute(
            text(
                """
                SELECT event_id
                FROM task_events
                WHERE idempotency_key = :idempotency_key
                """
            ),
            {"idempotency_key": idempotency_key},
        ).fetchone()
        if row:
            return row[0]
        raise RuntimeError("Task event idempotency lookup failed")

    def _outbox_id_for_idempotency_key(self, idempotency_key: str, *, conn) -> str:
        row = conn.execute(
            text(
                """
                SELECT outbox_id
                FROM outbox_events
                WHERE idempotency_key = :idempotency_key
                """
            ),
            {"idempotency_key": idempotency_key},
        ).fetchone()
        if row:
            return row[0]
        raise RuntimeError("Outbox idempotency lookup failed")
