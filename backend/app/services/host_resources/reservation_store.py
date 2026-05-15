"""PostgreSQL durable ledger for host resource reservations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase


ACTIVE_STATES = ("reserved_waiting", "permitted")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _row_mapping(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row or {})


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class HostResourceReservationStore(PostgresStoreBase):
    """Durable reservation/event store.

    The worker hot path should continue reading Redis projections. This store is
    for API lifecycle writes, restart reconciliation, and dashboard history.
    """

    def save_reservation(self, reservation: dict[str, Any]) -> dict[str, Any]:
        params = self._reservation_params(reservation)
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO host_resource_reservations (
                        reservation_id, state, target_lane, priority_class,
                        drain_policy, preemption_policy, resume_policy,
                        requested_by, route_request, metadata,
                        created_at, updated_at, expires_at, cancelled_at,
                        completed_at
                    ) VALUES (
                        :reservation_id, :state, :target_lane, :priority_class,
                        :drain_policy, :preemption_policy, :resume_policy,
                        :requested_by, :route_request, :metadata,
                        :created_at, :updated_at, :expires_at, :cancelled_at,
                        :completed_at
                    )
                    ON CONFLICT (reservation_id) DO UPDATE SET
                        state = EXCLUDED.state,
                        target_lane = EXCLUDED.target_lane,
                        priority_class = EXCLUDED.priority_class,
                        drain_policy = EXCLUDED.drain_policy,
                        preemption_policy = EXCLUDED.preemption_policy,
                        resume_policy = EXCLUDED.resume_policy,
                        requested_by = EXCLUDED.requested_by,
                        route_request = EXCLUDED.route_request,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at,
                        expires_at = EXCLUDED.expires_at,
                        cancelled_at = EXCLUDED.cancelled_at,
                        completed_at = EXCLUDED.completed_at
                    RETURNING *
                    """
                ),
                params,
            ).fetchone()
        return self._row_to_reservation(row) if row else dict(reservation)

    def append_event(
        self,
        event_type: str,
        *,
        reservation_id: str | None = None,
        payload: dict[str, Any] | None = None,
        source: str | None = None,
        actor: str | None = None,
        task_id: str | None = None,
        runner_id: str | None = None,
        lane_id: str | None = None,
        occurred_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": f"hostres_evt_{uuid.uuid4().hex}",
            "reservation_id": _clean_string(reservation_id),
            "event_type": str(event_type or "").strip(),
            "occurred_at": _parse_datetime(occurred_at) or _utc_now(),
            "source": _clean_string(source),
            "actor": _clean_string(actor),
            "task_id": _clean_string(task_id),
            "runner_id": _clean_string(runner_id),
            "lane_id": _clean_string(lane_id),
            "payload": payload if isinstance(payload, dict) else {},
        }
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO host_resource_events (
                        event_id, reservation_id, event_type, occurred_at,
                        source, actor, task_id, runner_id, lane_id, payload
                    ) VALUES (
                        :event_id, :reservation_id, :event_type, :occurred_at,
                        :source, :actor, :task_id, :runner_id, :lane_id, :payload
                    )
                    RETURNING *
                    """
                ),
                {**event, "payload": self.serialize_json(event["payload"])},
            ).fetchone()
        return self._row_to_event(row) if row else event

    def cancel_reservation(
        self,
        reservation_id: str,
        *,
        cancelled_at: datetime | str | None = None,
    ) -> dict[str, Any] | None:
        cancelled_time = _parse_datetime(cancelled_at) or _utc_now()
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE host_resource_reservations
                    SET state = 'cancelled',
                        cancelled_at = :cancelled_at,
                        updated_at = :cancelled_at
                    WHERE reservation_id = :reservation_id
                    RETURNING *
                    """
                ),
                {
                    "reservation_id": reservation_id,
                    "cancelled_at": cancelled_time,
                },
            ).fetchone()
        return self._row_to_reservation(row) if row else None

    def expire_stale_reservations(
        self,
        *,
        now: datetime | str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        now_dt = _parse_datetime(now) or _utc_now()
        with self.transaction() as conn:
            rows = conn.execute(
                text(
                    """
                    WITH stale AS (
                        SELECT reservation_id
                        FROM host_resource_reservations
                        WHERE state IN ('reserved_waiting', 'permitted')
                          AND expires_at IS NOT NULL
                          AND expires_at <= :now
                        ORDER BY expires_at ASC, created_at ASC
                        LIMIT :limit
                    )
                    UPDATE host_resource_reservations reservation
                    SET state = 'expired',
                        updated_at = :now
                    FROM stale
                    WHERE reservation.reservation_id = stale.reservation_id
                    RETURNING reservation.*
                    """
                ),
                {"now": now_dt, "limit": max(1, int(limit or 100))},
            ).fetchall()
        return [self._row_to_reservation(row) for row in rows]

    def list_active_reservations(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM host_resource_reservations
                    WHERE state IN ('reserved_waiting', 'permitted')
                      AND (expires_at IS NULL OR expires_at > now())
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, int(limit or 100))},
            ).fetchall()
        return [self._row_to_reservation(row) for row in rows]

    def list_reservations(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM host_resource_reservations
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, int(limit or 100))},
            ).fetchall()
        return [self._row_to_reservation(row) for row in rows]

    def list_events(
        self,
        *,
        reservation_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params = {"limit": max(1, int(limit or 100))}
        where_clause = ""
        if reservation_id:
            where_clause = "WHERE reservation_id = :reservation_id"
            params["reservation_id"] = reservation_id
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT *
                    FROM host_resource_events
                    {where_clause}
                    ORDER BY occurred_at DESC, event_id DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def _reservation_params(self, reservation: dict[str, Any]) -> dict[str, Any]:
        route_request = reservation.get("route_request")
        if not isinstance(route_request, dict):
            route_request = {}
        metadata = reservation.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        created_at = _parse_datetime(reservation.get("created_at")) or _utc_now()
        updated_at = _parse_datetime(reservation.get("updated_at")) or _utc_now()
        return {
            "reservation_id": str(reservation.get("reservation_id") or "").strip(),
            "state": str(reservation.get("state") or "reserved_waiting"),
            "target_lane": _clean_string(route_request.get("target_lane")),
            "priority_class": _clean_string(route_request.get("priority_class")),
            "drain_policy": _clean_string(route_request.get("drain_policy")),
            "preemption_policy": _clean_string(route_request.get("preemption_policy")),
            "resume_policy": _clean_string(route_request.get("resume_policy")),
            "requested_by": _clean_string(route_request.get("requested_by")),
            "route_request": self.serialize_json(route_request),
            "metadata": self.serialize_json(metadata),
            "created_at": created_at,
            "updated_at": updated_at,
            "expires_at": _parse_datetime(reservation.get("expires_at")),
            "cancelled_at": _parse_datetime(reservation.get("cancelled_at")),
            "completed_at": _parse_datetime(reservation.get("completed_at")),
        }

    def _row_to_reservation(self, row: Any) -> dict[str, Any]:
        data = _row_mapping(row)
        route_request = self.deserialize_json(data.get("route_request"), {})
        reservation = {
            "reservation_id": data.get("reservation_id"),
            "state": data.get("state"),
            "created_at": self.to_isoformat(data.get("created_at")),
            "updated_at": self.to_isoformat(data.get("updated_at")),
            "expires_at": self.to_isoformat(data.get("expires_at")),
            "route_request": route_request,
        }
        for key in ("cancelled_at", "completed_at"):
            value = self.to_isoformat(data.get(key))
            if value:
                reservation[key] = value
        metadata = self.deserialize_json(data.get("metadata"), {})
        if metadata:
            reservation["metadata"] = metadata
        return reservation

    def _row_to_event(self, row: Any) -> dict[str, Any]:
        data = _row_mapping(row)
        return {
            "event_id": data.get("event_id"),
            "reservation_id": data.get("reservation_id"),
            "event_type": data.get("event_type"),
            "occurred_at": self.to_isoformat(data.get("occurred_at")),
            "source": data.get("source"),
            "actor": data.get("actor"),
            "task_id": data.get("task_id"),
            "runner_id": data.get("runner_id"),
            "lane_id": data.get("lane_id"),
            "payload": self.deserialize_json(data.get("payload"), {}),
        }
