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

        start_dt = self._parse_iso_datetime(start_date)
        end_dt = self._parse_iso_datetime(end_date)

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

        decisions: List[Dict[str, Any]] = []
        for row in rows:
            data = row._mapping
            metadata_payload = self.deserialize_json(data.get("metadata"), default={})
            timestamp_val = data.get("timestamp")
            timestamp_str = (
                timestamp_val.isoformat() if hasattr(timestamp_val, "isoformat") else str(timestamp_val)
            )

            decisions.append(
                {
                    "decision_id": data.get("decision_id"),
                    "timestamp": timestamp_str,
                    "layer": data.get("layer"),
                    "approved": bool(data.get("approved")),
                    "reason": data.get("reason"),
                    "playbook_code": data.get("playbook_code"),
                    "metadata": metadata_payload or {},
                }
            )

        return decisions, total

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

        trend = [
            {"date": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]), "cost": float(row[1])}
            for row in trend_rows
        ]
        breakdown_by_playbook = {row[0]: float(row[1]) for row in breakdown_playbook_rows}
        breakdown_by_model = {row[0]: float(row[1]) for row in breakdown_model_rows}

        breakdown = {
            "by_playbook": breakdown_by_playbook,
            "by_model": breakdown_by_model,
        }

        return float(current_usage), trend, breakdown

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

            layer_totals: Dict[str, int] = {}
            layer_rejected: Dict[str, int] = {}
            for row in rejection_rows:
                layer_totals[row[0]] = int(row[1] or 0)
                layer_rejected[row[0]] = int(row[2] or 0)

            rejection_rate = {
                "cost": self._calculate_rate(layer_rejected.get("cost"), layer_totals.get("cost")),
                "node": self._calculate_rate(layer_rejected.get("node"), layer_totals.get("node")),
                "policy": self._calculate_rate(layer_rejected.get("policy"), layer_totals.get("policy")),
                "preflight": self._calculate_rate(layer_rejected.get("preflight"), layer_totals.get("preflight")),
                "overall": 0.0,
            }
            total_all = sum(layer_totals.values())
            rejected_all = sum(layer_rejected.values())
            rejection_rate["overall"] = self._calculate_rate(rejected_all, total_all)

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

        cost_trend = [
            {"date": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]), "cost": float(row[1])}
            for row in cost_trend_rows
        ]

        violation_frequency = {
            "policy": {
                "role_violation": 0,
                "data_domain_violation": 0,
                "pii_violation": 0,
            },
            "node": {
                "blacklist": 0,
                "risk_label": 0,
                "throttle": 0,
            },
        }

        for row in violation_rows:
            layer = row[0]
            reason = (row[1] or "").lower()
            count = int(row[2] or 0)

            if layer == "policy":
                if "role" in reason:
                    violation_frequency["policy"]["role_violation"] += count
                elif "domain" in reason:
                    violation_frequency["policy"]["data_domain_violation"] += count
                elif "pii" in reason:
                    violation_frequency["policy"]["pii_violation"] += count
            elif layer == "node":
                if "blacklist" in reason:
                    violation_frequency["node"]["blacklist"] += count
                elif "risk" in reason:
                    violation_frequency["node"]["risk_label"] += count
                elif "throttle" in reason or "limit" in reason:
                    violation_frequency["node"]["throttle"] += count

        preflight_failure_reasons = {
            "missing_inputs": 0,
            "missing_credentials": 0,
            "environment_issues": 0,
        }
        for row in preflight_rows:
            metadata_payload = self.deserialize_json(row[0], default={})
            count = int(row[1] or 0)
            if metadata_payload.get("missing_inputs"):
                preflight_failure_reasons["missing_inputs"] += count
            if metadata_payload.get("missing_credentials"):
                preflight_failure_reasons["missing_credentials"] += count
            if metadata_payload.get("environment_issues"):
                preflight_failure_reasons["environment_issues"] += count

        return rejection_rate, cost_trend, violation_frequency, preflight_failure_reasons

    @staticmethod
    def _calculate_rate(rejected: Optional[int], total: Optional[int]) -> float:
        if not total:
            return 0.0
        return (float(rejected or 0) / float(total)) * 100.0

    @staticmethod
    def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            logger.warning(f"Invalid datetime filter: {value} ({exc})")
            return None
