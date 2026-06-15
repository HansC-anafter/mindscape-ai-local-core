"""
Governance Store (PostgreSQL)

Provides storage and query helpers for governance decisions and cost usage.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, date, timedelta, time, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from backend.app.services.governance.governance_projection import (
    build_cost_usage_summary,
    build_governance_metrics,
    map_decision_row,
    map_execution_decision_row,
    parse_iso_datetime,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class GovernanceStore(PostgresStoreBase):
    """Postgres-backed governance store."""

    def record_decision(
        self,
        workspace_id: str,
        execution_id: Optional[str],
        layer: str,
        approved: bool,
        reason: Optional[str] = None,
        playbook_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        decision_id = str(uuid.uuid4())
        now = _utc_now()
        metadata_payload = self.serialize_json(metadata) if metadata else None

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO governance_decisions (
                        decision_id, workspace_id, execution_id, timestamp,
                        layer, approved, reason, playbook_code, metadata,
                        created_at, updated_at
                    ) VALUES (
                        :decision_id, :workspace_id, :execution_id, :timestamp,
                        :layer, :approved, :reason, :playbook_code, CAST(:metadata AS JSONB),
                        :created_at, :updated_at
                    )
                    """
                ),
                {
                    "decision_id": decision_id,
                    "workspace_id": workspace_id,
                    "execution_id": execution_id,
                    "timestamp": now,
                    "layer": layer,
                    "approved": approved,
                    "reason": reason,
                    "playbook_code": playbook_code,
                    "metadata": metadata_payload,
                    "created_at": now,
                    "updated_at": now,
                },
            )

        return decision_id

    def record_cost_usage(
        self,
        workspace_id: str,
        execution_id: Optional[str],
        cost: float,
        playbook_code: Optional[str] = None,
        model_name: Optional[str] = None,
        token_count: Optional[int] = None,
    ) -> str:
        usage_id = str(uuid.uuid4())
        today = date.today()
        now = _utc_now()

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO cost_usage (
                        id, workspace_id, execution_id, date, cost,
                        playbook_code, model_name, token_count,
                        created_at, updated_at
                    ) VALUES (
                        :id, :workspace_id, :execution_id, :date, :cost,
                        :playbook_code, :model_name, :token_count,
                        :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": usage_id,
                    "workspace_id": workspace_id,
                    "execution_id": execution_id,
                    "date": today,
                    "cost": cost,
                    "playbook_code": playbook_code,
                    "model_name": model_name,
                    "token_count": token_count,
                    "created_at": now,
                    "updated_at": now,
                },
            )

        return usage_id

    def list_decisions(
        self,
        workspace_id: str,
        layer: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
        page: int,
        limit: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        base_query = """
            SELECT
                decision_id,
                workspace_id,
                execution_id,
                timestamp,
                layer,
                approved,
                reason,
                playbook_code,
                metadata
            FROM governance_decisions
            WHERE workspace_id = :workspace_id
        """
        params: Dict[str, Any] = {"workspace_id": workspace_id}

        start_dt = parse_iso_datetime(start_date, logger=logger)
        end_dt = parse_iso_datetime(end_date, logger=logger)

        if layer:
            base_query += " AND layer = :layer"
            params["layer"] = layer
        if start_dt:
            base_query += " AND timestamp >= :start_date"
            params["start_date"] = start_dt
        if end_dt:
            base_query += " AND timestamp <= :end_date"
            params["end_date"] = end_dt

        count_query = f"SELECT COUNT(*) AS total FROM ({base_query}) AS filtered"
        paged_query = (
            base_query
            + " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
        )

        offset = (page - 1) * limit
        params.update({"limit": limit, "offset": offset})

        with self.get_connection() as conn:
            total = conn.execute(text(count_query), params).scalar() or 0
            rows = conn.execute(text(paged_query), params).fetchall()

        return [
            map_decision_row(row, deserialize_json=self.deserialize_json)
            for row in rows
        ], total

    def list_decisions_for_execution(
        self,
        *,
        workspace_id: str,
        execution_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        decision_id,
                        workspace_id,
                        execution_id,
                        timestamp,
                        layer,
                        approved,
                        reason,
                        playbook_code,
                        metadata
                    FROM governance_decisions
                    WHERE workspace_id = :workspace_id
                      AND execution_id = :execution_id
                    ORDER BY timestamp DESC
                    LIMIT :limit
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "execution_id": execution_id,
                    "limit": limit,
                },
            ).fetchall()

        return [
            map_execution_decision_row(row, deserialize_json=self.deserialize_json)
            for row in rows
        ]

    def get_today_usage(self, workspace_id: str) -> float:
        with self.get_connection() as conn:
            total = conn.execute(
                text(
                    """
                    SELECT COALESCE(SUM(cost), 0.0) AS total_cost
                    FROM cost_usage
                    WHERE workspace_id = :workspace_id AND date = :today
                    """
                ),
                {"workspace_id": workspace_id, "today": date.today()},
            ).scalar()
        return float(total or 0.0)

    def get_cost_usage_summary(
        self,
        workspace_id: str,
        period: str,
    ) -> Tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
        today = date.today()
        if period == "day":
            start_date = today
            end_date = today
            trend_days = 7
        else:
            start_date = today.replace(day=1)
            end_date = today
            trend_days = 30

        with self.get_connection() as conn:
            current_usage = conn.execute(
                text(
                    """
                    SELECT COALESCE(SUM(cost), 0.0) AS total_cost
                    FROM cost_usage
                    WHERE workspace_id = :workspace_id
                      AND date >= :start_date
                      AND date <= :end_date
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            ).scalar() or 0.0

            trend_start = today - timedelta(days=trend_days - 1)
            trend_rows = conn.execute(
                text(
                    """
                    SELECT date, SUM(cost) AS daily_cost
                    FROM cost_usage
                    WHERE workspace_id = :workspace_id
                      AND date >= :trend_start
                    GROUP BY date
                    ORDER BY date ASC
                    """
                ),
                {"workspace_id": workspace_id, "trend_start": trend_start},
            ).fetchall()

            breakdown_playbook_rows = conn.execute(
                text(
                    """
                    SELECT playbook_code, SUM(cost) AS total_cost
                    FROM cost_usage
                    WHERE workspace_id = :workspace_id
                      AND date >= :start_date
                      AND date <= :end_date
                      AND playbook_code IS NOT NULL
                    GROUP BY playbook_code
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            ).fetchall()

            breakdown_model_rows = conn.execute(
                text(
                    """
                    SELECT model_name, SUM(cost) AS total_cost
                    FROM cost_usage
                    WHERE workspace_id = :workspace_id
                      AND date >= :start_date
                      AND date <= :end_date
                      AND model_name IS NOT NULL
                    GROUP BY model_name
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            ).fetchall()

        return build_cost_usage_summary(
            current_usage,
            trend_rows,
            breakdown_playbook_rows,
            breakdown_model_rows,
        )

    def get_governance_metrics(
        self,
        workspace_id: str,
        period: str,
    ) -> Tuple[Dict[str, float], List[Dict[str, Any]], Dict[str, Any], Dict[str, int]]:
        today = date.today()
        if period == "day":
            start_timestamp = datetime.combine(today, time.min)
        else:
            start_timestamp = datetime.combine(today.replace(day=1), time.min)

        with self.get_connection() as conn:
            rejection_rows = conn.execute(
                text(
                    """
                    SELECT
                        layer,
                        COUNT(*) AS total,
                        SUM(CASE WHEN approved = false THEN 1 ELSE 0 END) AS rejected
                    FROM governance_decisions
                    WHERE workspace_id = :workspace_id
                      AND timestamp >= :start_timestamp
                    GROUP BY layer
                    """
                ),
                {"workspace_id": workspace_id, "start_timestamp": start_timestamp},
            ).fetchall()

            cost_trend_rows = conn.execute(
                text(
                    """
                    SELECT date, SUM(cost) AS daily_cost
                    FROM cost_usage
                    WHERE workspace_id = :workspace_id
                      AND date >= :trend_start
                    GROUP BY date
                    ORDER BY date ASC
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "trend_start": today - timedelta(days=30),
                },
            ).fetchall()

            violation_rows = conn.execute(
                text(
                    """
                    SELECT layer, reason, COUNT(*) AS count
                    FROM governance_decisions
                    WHERE workspace_id = :workspace_id
                      AND approved = false
                      AND timestamp >= :start_timestamp
                    GROUP BY layer, reason
                    """
                ),
                {"workspace_id": workspace_id, "start_timestamp": start_timestamp},
            ).fetchall()

            preflight_rows = conn.execute(
                text(
                    """
                    SELECT metadata, COUNT(*) AS count
                    FROM governance_decisions
                    WHERE workspace_id = :workspace_id
                      AND layer = 'preflight'
                      AND approved = false
                      AND timestamp >= :start_timestamp
                    GROUP BY metadata
                    """
                ),
                {"workspace_id": workspace_id, "start_timestamp": start_timestamp},
            ).fetchall()

        return build_governance_metrics(
            rejection_rows,
            cost_trend_rows,
            violation_rows,
            preflight_rows,
            deserialize_json=self.deserialize_json,
        )
