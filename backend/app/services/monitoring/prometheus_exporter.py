"""
Prometheus Exporter for Runtime Profile Events

Exports Workspace Runtime Profile events (PolicyGuard, LoopBudget, QualityGates)
as Prometheus metrics for monitoring with Grafana.

All data is read from local SQLite database (no GCP dependencies).
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from fastapi import FastAPI, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from backend.app.models.mindscape import EventType
from backend.app.services.stores.events_store import EventsStore
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)

# Prometheus metrics
policy_check_total = Counter(
    'runtime_profile_policy_check_total',
    'Total number of policy checks',
    ['workspace_id', 'tool_id', 'capability_code', 'risk_class', 'allowed', 'requires_approval']
)

policy_check_denial_reasons = Counter(
    'runtime_profile_policy_check_denial_reasons_total',
    'Total number of policy check denials by reason',
    ['workspace_id', 'reason']
)

budget_exhausted_total = Counter(
    'runtime_profile_budget_exhausted_total',
    'Total number of budget exhaustion events',
    ['workspace_id', 'exhausted_limit']
)

budget_usage_percentage = Gauge(
    'runtime_profile_budget_usage_percentage',
    'Budget usage percentage',
    ['workspace_id', 'metric_type']
)

quality_gate_check_total = Counter(
    'runtime_profile_quality_gate_check_total',
    'Total number of quality gate checks',
    ['workspace_id', 'passed', 'failed_gate']
)

quality_gate_check_duration = Histogram(
    'runtime_profile_quality_gate_check_duration_seconds',
    'Quality gate check duration in seconds',
    ['workspace_id']
)


class PrometheusExporter:
    """Prometheus exporter for Runtime Profile events"""

    def __init__(self):
        self.settings_store = SystemSettingsStore()
        self.db_path = self.settings_store.get_database_path()
        self.events_store = EventsStore(self.db_path)
        self.last_update_time: Dict[str, datetime] = {}
        self.update_interval_seconds = 30  # Update metrics every 30 seconds

    def update_metrics(self, workspace_id: Optional[str] = None, hours: int = 24):
        """
        Update Prometheus metrics from event store

        Args:
            workspace_id: Optional workspace ID to filter (if None, updates all workspaces)
            hours: Time range in hours to query events
        """
        try:
            end_time = _utc_now()
            start_time = end_time - timedelta(hours=hours)

            # Get all workspaces if not specified
            if workspace_id:
                workspace_ids = [workspace_id]
            else:
                # Query all unique workspace_ids from events
                with self.events_store.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT DISTINCT workspace_id
                        FROM mind_events
                        WHERE workspace_id IS NOT NULL
                        AND timestamp >= ?
                        AND timestamp <= ?
                    ''', (start_time.isoformat(), end_time.isoformat()))
                    workspace_ids = [row[0] for row in cursor.fetchall() if row[0]]

            for ws_id in workspace_ids:
                # Check if we need to update (throttle updates)
                cache_key = f"{ws_id}_{hours}"
                last_update = self.last_update_time.get(cache_key)
                if last_update and (_utc_now() - last_update).total_seconds() < self.update_interval_seconds:
                    continue

                self._update_workspace_metrics(ws_id, start_time, end_time)
                self.last_update_time[cache_key] = _utc_now()

        except Exception as e:
            logger.error(f"Failed to update Prometheus metrics: {e}", exc_info=True)

    def _update_workspace_metrics(self, workspace_id: str, start_time: datetime, end_time: datetime):
        """Update metrics for a specific workspace"""
        try:
            # Get events
            events = self.events_store.get_events_by_workspace(
                workspace_id=workspace_id,
                start_time=start_time,
                end_time=end_time,
                limit=10000
            )

            # Process PolicyGuard events
            policy_events = [e for e in events if e.event_type == EventType.POLICY_CHECK]
            for event in policy_events:
                payload = event.payload or {}
                tool_id = payload.get("tool_id", "unknown")
                capability_code = payload.get("capability_code", "unknown")
                risk_class = payload.get("risk_class", "unknown")
                allowed = "true" if payload.get("allowed") else "false"
                requires_approval = "true" if payload.get("requires_approval") else "false"

                policy_check_total.labels(
                    workspace_id=workspace_id,
                    tool_id=tool_id,
                    capability_code=capability_code,
                    risk_class=risk_class,
                    allowed=allowed,
                    requires_approval=requires_approval
                ).inc()

                if not payload.get("allowed"):
                    reason = payload.get("reason", "unknown")
                    policy_check_denial_reasons.labels(
                        workspace_id=workspace_id,
                        reason=reason
                    ).inc()

            # Process LoopBudget events
            budget_events = [e for e in events if e.event_type == EventType.LOOP_BUDGET_EXHAUSTED]
            for event in budget_events:
                payload = event.payload or {}

                # Exhaustion events
                if "exhausted_limits" in payload:
                    exhausted_limits = payload.get("exhausted_limits", [])
                    for limit in exhausted_limits:
                        budget_exhausted_total.labels(
                            workspace_id=workspace_id,
                            exhausted_limit=limit
                        ).inc()

                # Usage percentage events
                usage_percentages = payload.get("usage_percentages", {})
                for metric_type, percentage in usage_percentages.items():
                    budget_usage_percentage.labels(
                        workspace_id=workspace_id,
                        metric_type=metric_type
                    ).set(percentage)

            # Process QualityGates events
            quality_events = [e for e in events if e.event_type == EventType.QUALITY_GATE_CHECK]
            for event in quality_events:
                payload = event.payload or {}
                passed = "true" if payload.get("passed") else "false"
                failed_gates = payload.get("failed_gates", [])

                if failed_gates:
                    for gate in failed_gates:
                        quality_gate_check_total.labels(
                            workspace_id=workspace_id,
                            passed=passed,
                            failed_gate=gate
                        ).inc()
                else:
                    quality_gate_check_total.labels(
                        workspace_id=workspace_id,
                        passed=passed,
                        failed_gate="none"
                    ).inc()

        except Exception as e:
            logger.error(f"Failed to update metrics for workspace {workspace_id}: {e}", exc_info=True)


# Global exporter instance
_exporter = PrometheusExporter()


def get_metrics_endpoint(app: FastAPI):
    """Register Prometheus metrics endpoint"""

    @app.get("/metrics")
    async def metrics():
        """
        Prometheus metrics endpoint

        Returns metrics in Prometheus format.
        Updates metrics from event store before returning.
        """
        try:
            # Update metrics from event store
            _exporter.update_metrics()

            # Return metrics in Prometheus format
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST
            )
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}", exc_info=True)
            return Response(
                content="# Error generating metrics\n",
                media_type=CONTENT_TYPE_LATEST,
                status_code=500
            )

