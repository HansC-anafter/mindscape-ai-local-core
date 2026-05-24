"""Workspace-scoped external runner observation store."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase

EXTERNAL_RUNNER_SOURCE_KIND = "external_runner"
ACTIVE_RUN_OBSERVATION_STATUSES = {"queued", "pending", "running", "paused"}
TERMINAL_RUN_OBSERVATION_STATUSES = {
    "succeeded",
    "completed",
    "failed",
    "cancelled",
}
RUN_OBSERVATION_STATUSES = (
    ACTIVE_RUN_OBSERVATION_STATUSES | TERMINAL_RUN_OBSERVATION_STATUSES
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_observation_status(
    status: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> str:
    normalized = (status or "").strip().lower()
    payload_map = payload or {}
    stop_reason = str(payload_map.get("stop_reason") or "").strip().lower()
    error_kind = str(payload_map.get("error_kind") or "").strip().lower()
    if stop_reason == "operator_interrupt" or error_kind == "execution_interrupted":
        return "cancelled"
    if stop_reason == "operator_pause":
        return "paused"
    return normalized


def _isoformat(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class RunObservationEvent:
    workspace_id: str
    run_id: str
    source_kind: str
    provider_code: str
    status: str
    stage_code: str
    summary: str
    idempotency_key: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    execution_id: Optional[str] = None
    display_title: Optional[str] = None
    occurred_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RunObservationStore(PostgresStoreBase):
    """Persist and read compact external runner observations."""

    def record_event(self, event: RunObservationEvent) -> dict[str, Any]:
        if event.source_kind != EXTERNAL_RUNNER_SOURCE_KIND:
            raise ValueError("run observations only accept external_runner source_kind")
        if not event.workspace_id:
            raise ValueError("workspace_id is required")

        occurred_at = event.occurred_at or _utc_now()
        payload = dict(event.payload or {})
        payload.setdefault("stage_code", event.stage_code)
        status = normalize_observation_status(event.status, payload)
        if status not in RUN_OBSERVATION_STATUSES:
            raise ValueError(f"unsupported run observation status: {status}")

        execution_id = event.execution_id or event.run_id
        started_at = event.started_at
        if started_at is None and status in ACTIVE_RUN_OBSERVATION_STATUSES:
            started_at = occurred_at
        completed_at = event.completed_at
        if completed_at is None and status in TERMINAL_RUN_OBSERVATION_STATUSES:
            completed_at = occurred_at

        run_params = {
            "run_id": event.run_id,
            "execution_id": execution_id,
            "workspace_id": event.workspace_id,
            "pack_id": event.provider_code,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "updated_at": occurred_at,
            "source_kind": EXTERNAL_RUNNER_SOURCE_KIND,
            "display_title": event.display_title,
            "heartbeat_at": occurred_at,
        }
        feed_params = {
            "feed_id": event.idempotency_key,
            "workspace_id": event.workspace_id,
            "run_id": event.run_id,
            "execution_id": execution_id,
            "pack_id": event.provider_code,
            "status": status,
            "summary": event.summary,
            "occurred_at": occurred_at,
            "source_kind": EXTERNAL_RUNNER_SOURCE_KIND,
            "payload": self.serialize_json(payload),
        }
        upsert_run_query = text(
            """
            INSERT INTO runs (
                run_id,
                execution_id,
                workspace_id,
                task_id,
                pack_id,
                status,
                started_at,
                completed_at,
                updated_at,
                source_kind,
                display_title,
                heartbeat_at
            )
            VALUES (
                :run_id,
                :execution_id,
                :workspace_id,
                NULL,
                :pack_id,
                :status,
                :started_at,
                :completed_at,
                :updated_at,
                :source_kind,
                :display_title,
                :heartbeat_at
            )
            ON CONFLICT (run_id)
            DO UPDATE SET
                execution_id = EXCLUDED.execution_id,
                workspace_id = EXCLUDED.workspace_id,
                task_id = NULL,
                pack_id = EXCLUDED.pack_id,
                status = EXCLUDED.status,
                started_at = COALESCE(runs.started_at, EXCLUDED.started_at),
                completed_at = EXCLUDED.completed_at,
                updated_at = EXCLUDED.updated_at,
                source_kind = EXCLUDED.source_kind,
                display_title = EXCLUDED.display_title,
                heartbeat_at = EXCLUDED.heartbeat_at
            """
        )
        append_feed_query = text(
            """
            INSERT INTO workspace_run_feed (
                feed_id,
                workspace_id,
                run_id,
                task_id,
                execution_id,
                pack_id,
                status,
                summary,
                occurred_at,
                source_kind,
                payload
            )
            VALUES (
                :feed_id,
                :workspace_id,
                :run_id,
                NULL,
                :execution_id,
                :pack_id,
                :status,
                :summary,
                :occurred_at,
                :source_kind,
                CAST(:payload AS JSONB)
            )
            ON CONFLICT (feed_id) DO NOTHING
            """
        )
        with self.transaction() as conn:
            conn.execute(upsert_run_query, run_params)
            conn.execute(append_feed_query, feed_params)

        return {
            "run_id": event.run_id,
            "feed_id": event.idempotency_key,
            "status": status,
            "workspace_id": event.workspace_id,
        }

    def list_summary(
        self,
        workspace_id: str,
        *,
        active_only: bool = True,
        limit: int = 20,
    ) -> dict[str, Any]:
        limit_value = max(1, min(int(limit), 100))
        status_clause = ""
        if active_only:
            status_clause = """
              AND runs.status IN ('queued', 'pending', 'running', 'paused')
            """
        cards_query = text(
            f"""
            WITH latest_feed AS (
                SELECT DISTINCT ON (workspace_run_feed.run_id)
                    workspace_run_feed.run_id,
                    workspace_run_feed.feed_id,
                    workspace_run_feed.summary,
                    workspace_run_feed.payload,
                    workspace_run_feed.occurred_at
                FROM workspace_run_feed
                WHERE workspace_run_feed.workspace_id = :workspace_id
                  AND workspace_run_feed.source_kind = :source_kind
                ORDER BY workspace_run_feed.run_id,
                         workspace_run_feed.occurred_at DESC,
                         workspace_run_feed.feed_id DESC
            )
            SELECT
                runs.run_id,
                runs.execution_id,
                runs.workspace_id,
                runs.pack_id,
                runs.status,
                runs.started_at,
                runs.completed_at,
                runs.created_at,
                runs.updated_at,
                runs.display_title,
                runs.heartbeat_at,
                latest_feed.feed_id,
                latest_feed.summary,
                latest_feed.payload,
                latest_feed.occurred_at
            FROM runs
            LEFT JOIN latest_feed ON latest_feed.run_id = runs.run_id
            WHERE runs.workspace_id = :workspace_id
              AND runs.source_kind = :source_kind
              {status_clause}
            ORDER BY runs.updated_at DESC, runs.run_id DESC
            LIMIT :limit
            """
        )
        counts_query = text(
            """
            SELECT runs.status, COUNT(*) AS count
            FROM runs
            WHERE runs.workspace_id = :workspace_id
              AND runs.source_kind = :source_kind
            GROUP BY runs.status
            """
        )
        params = {
            "workspace_id": workspace_id,
            "source_kind": EXTERNAL_RUNNER_SOURCE_KIND,
            "limit": limit_value,
        }
        with self.get_connection() as conn:
            count_rows = conn.execute(counts_query, params).fetchall()
            card_rows = conn.execute(cards_query, params).fetchall()

        counts = {
            str(row._mapping["status"]): int(row._mapping["count"])
            for row in count_rows
        }
        external_active_count = sum(
            counts.get(status, 0) for status in ACTIVE_RUN_OBSERVATION_STATUSES
        )
        cards = [self._summary_row_to_card(row._mapping) for row in card_rows]
        return {
            "workspace_id": workspace_id,
            "source_kind": EXTERNAL_RUNNER_SOURCE_KIND,
            "external_active_count": external_active_count,
            "counts": counts,
            "cards": cards,
        }

    def list_events(
        self,
        workspace_id: str,
        run_id: str,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        limit_value = max(1, min(int(limit), 200))
        query = text(
            """
            SELECT
                feed_id,
                workspace_id,
                run_id,
                execution_id,
                pack_id,
                status,
                summary,
                occurred_at,
                source_kind,
                payload
            FROM workspace_run_feed
            WHERE workspace_id = :workspace_id
              AND run_id = :run_id
              AND source_kind = :source_kind
            ORDER BY occurred_at DESC, feed_id DESC
            LIMIT :limit
            """
        )
        params = {
            "workspace_id": workspace_id,
            "run_id": run_id,
            "source_kind": EXTERNAL_RUNNER_SOURCE_KIND,
            "limit": limit_value,
        }
        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        events = [self._event_row_to_dict(row._mapping) for row in rows]
        return {
            "workspace_id": workspace_id,
            "run_id": run_id,
            "events": events,
        }

    def _summary_row_to_card(self, row: Mapping[str, Any]) -> dict[str, Any]:
        payload = self.deserialize_json(row.get("payload"), default={})
        return {
            "run_id": row.get("run_id"),
            "execution_id": row.get("execution_id"),
            "workspace_id": row.get("workspace_id"),
            "provider_code": row.get("pack_id"),
            "source_kind": EXTERNAL_RUNNER_SOURCE_KIND,
            "status": row.get("status"),
            "display_title": row.get("display_title"),
            "summary": row.get("summary"),
            "payload": payload,
            "feed_id": row.get("feed_id"),
            "started_at": _isoformat(row.get("started_at")),
            "completed_at": _isoformat(row.get("completed_at")),
            "created_at": _isoformat(row.get("created_at")),
            "updated_at": _isoformat(row.get("updated_at")),
            "heartbeat_at": _isoformat(row.get("heartbeat_at")),
            "occurred_at": _isoformat(row.get("occurred_at")),
        }

    def _event_row_to_dict(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "feed_id": row.get("feed_id"),
            "workspace_id": row.get("workspace_id"),
            "run_id": row.get("run_id"),
            "execution_id": row.get("execution_id"),
            "provider_code": row.get("pack_id"),
            "status": row.get("status"),
            "summary": row.get("summary"),
            "source_kind": row.get("source_kind"),
            "payload": self.deserialize_json(row.get("payload"), default={}),
            "occurred_at": _isoformat(row.get("occurred_at")),
        }
