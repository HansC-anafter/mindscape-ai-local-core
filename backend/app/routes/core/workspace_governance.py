"""
Workspace governance API endpoints

Handles workspace-level governance queries:
- Governance decision history
- Cost monitoring
- Governance metrics

Note: These endpoints support both Local-Core (SQLite) and Cloud (PostgreSQL).
If database is not available, endpoints return empty results or zero values.
Local-Core can also fallback to Events API for governance history.
"""
import logging
from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta

from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/governance", tags=["workspace-governance"])


class GovernanceDecision(BaseModel):
    """Governance decision model"""
    decision_id: str
    timestamp: str
    layer: str  # 'cost' | 'node' | 'policy' | 'preflight'
    approved: bool
    reason: Optional[str] = None
    playbook_code: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class GovernanceDecisionsResponse(BaseModel):
    """Response model for governance decisions list"""
    decisions: List[GovernanceDecision]
    total: int
    page: int
    limit: int
    total_pages: int


class CostMonitoringData(BaseModel):
    """Cost monitoring data model"""
    current_usage: float
    quota: float
    usage_percentage: float
    period: str  # 'day' | 'month'
    trend: List[Dict[str, Any]] = Field(default_factory=list)
    breakdown: Dict[str, Any] = Field(default_factory=dict)


class GovernanceMetricsData(BaseModel):
    """Governance metrics data model"""
    period: str  # 'day' | 'month'
    rejection_rate: Dict[str, float]
    cost_trend: List[Dict[str, Any]] = Field(default_factory=list)
    violation_frequency: Dict[str, Any] = Field(default_factory=dict)
    preflight_failure_reasons: Optional[Dict[str, int]] = None


def _is_cloud_environment() -> bool:
    """
    Check if running in Cloud environment

    Returns:
        True if Cloud environment, False for Local-Core
    """
    # Check for Cloud environment indicators
    # In Cloud, there would be database connection or environment variable
    # For now, assume Local-Core if no Cloud indicators found
    import os
    return os.getenv("CLOUD_ENV", "false").lower() == "true"


def _get_db_connection():
    """
    Get database connection (Cloud or Local-Core)

    Returns:
        Database connection object or None if not available
    """
    # Try SQLite for Local-Core first (check if database exists)
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path("./data/mindscape.db")
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            return conn
    except Exception as e:
        logger.warning(f"Failed to connect to SQLite database: {e}")

    # Cloud environment: use PostgreSQL connection pool
    # (This would be implemented for Cloud environment)
    if _is_cloud_environment():
        # TODO: Implement PostgreSQL connection pool for Cloud
        pass

    return None


def _query_governance_decisions_from_db(
    workspace_id: str,
    layer: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    page: int,
    limit: int
) -> tuple[List[Dict[str, Any]], int]:
    """
    Query governance decisions from database (SQLite for Local-Core or PostgreSQL for Cloud)

    Args:
        workspace_id: Workspace ID
        layer: Filter by governance layer
        start_date: Start date filter
        end_date: End date filter
        page: Page number
        limit: Items per page

    Returns:
        Tuple of (decisions list, total count)
    """
    conn = _get_db_connection()
    if not conn:
        # Database not available, return empty
        return [], 0

    try:
        # Build query (support both SQLite and PostgreSQL)
        # SQLite uses ? placeholders, PostgreSQL uses :name
        if hasattr(conn, 'execute') and 'sqlite' in str(type(conn)).lower():
            # SQLite
            query = """
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
                WHERE workspace_id = ?
            """
            params = [workspace_id]
        else:
            # PostgreSQL
            query = """
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
            params = {"workspace_id": workspace_id}

        # Add filters (handle both SQLite and PostgreSQL)
        is_sqlite = isinstance(params, list)

        if layer:
            if is_sqlite:
                query += " AND layer = ?"
                params.append(layer)
            else:
                query += " AND layer = :layer"
                params["layer"] = layer

        if start_date:
            if is_sqlite:
                query += " AND timestamp >= ?"
                params.append(start_date)
            else:
                query += " AND timestamp >= :start_date"
                params["start_date"] = start_date

        if end_date:
            if is_sqlite:
                query += " AND timestamp <= ?"
                params.append(end_date)
            else:
                query += " AND timestamp <= :end_date"
                params["end_date"] = end_date

        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM ({query}) AS filtered"
        cursor = conn.cursor()
        if is_sqlite:
            cursor.execute(count_query, params)
        else:
            cursor.execute(count_query, params)
        count_row = cursor.fetchone()
        total = count_row[0] if count_row else 0

        # Add pagination
        offset = (page - 1) * limit
        if is_sqlite:
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.append(limit)
            params.append(offset)
        else:
            query += " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
            params["limit"] = limit
            params["offset"] = offset

        # Execute query
        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Parse results
        decisions = []
        for row in rows:
            # Handle both SQLite Row and tuple
            if hasattr(row, 'keys'):
                decision_id = row['decision_id']
                timestamp = row['timestamp']
                layer = row['layer']
                approved = bool(row['approved'])
                reason = row.get('reason')
                playbook_code = row.get('playbook_code')
                metadata_str = row.get('metadata')
            else:
                decision_id = row[0]
                timestamp = row[3]
                layer = row[4]
                approved = bool(row[5])
                reason = row[6] if len(row) > 6 else None
                playbook_code = row[7] if len(row) > 7 else None
                metadata_str = row[8] if len(row) > 8 else None

            # Parse metadata
            metadata = {}
            if metadata_str:
                try:
                    import json
                    metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
                except Exception:
                    pass

            decisions.append({
                "decision_id": decision_id,
                "timestamp": timestamp,
                "layer": layer,
                "approved": approved,
                "reason": reason,
                "playbook_code": playbook_code,
                "metadata": metadata,
            })

        return decisions, total

    except Exception as e:
        logger.error(f"Failed to query governance decisions from database: {e}", exc_info=True)
        return [], 0


@router.get("/decisions", response_model=GovernanceDecisionsResponse)
async def get_governance_decisions(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    layer: Optional[str] = Query(None, description="Filter by governance layer"),
    start_date: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[str] = Query(None, description="End date (ISO 8601)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
):
    """
    Get governance decision history for a workspace

    Supports both Cloud (PostgreSQL) and Local-Core (SQLite) environments.
    If database is not available, returns empty results (use Events API for history).
    """
    try:
        # Try to query from database (SQLite for Local-Core or PostgreSQL for Cloud)
        conn = _get_db_connection()
        if conn:
            # Database available: Query from database
            decisions_data, total = _query_governance_decisions_from_db(
                workspace_id, layer, start_date, end_date, page, limit
            )
            decisions = [
                GovernanceDecision(**decision_data) for decision_data in decisions_data
            ]
        else:
            # No database available: Return empty
            # Users should use Events API to filter governance events
            decisions = []
            total = 0

        return GovernanceDecisionsResponse(
            decisions=decisions,
            total=total,
            page=page,
            limit=limit,
            total_pages=0 if total == 0 else (total + limit - 1) // limit,
        )
    except Exception as e:
        logger.error(f"Failed to get governance decisions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get governance decisions: {str(e)}")


def _query_cost_usage_from_db(
    workspace_id: str,
    period: str
) -> tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Query cost usage from database (SQLite for Local-Core or PostgreSQL for Cloud)

    Args:
        workspace_id: Workspace ID
        period: Period ('day' or 'month')

    Returns:
        Tuple of (current_usage, trend, breakdown)
    """
    conn = _get_db_connection()
    if not conn:
        # Database not available, return zero usage
        return 0.0, [], {"by_playbook": {}, "by_model": {}}

    try:
        # Determine date range
        if period == "day":
            date_filter = "date = CURRENT_DATE"
            trend_days = 7  # Last 7 days
        else:
            date_filter = "date >= DATE_TRUNC('month', CURRENT_DATE)"
            trend_days = 30  # Last 30 days

        # Query current usage
        if period == "day":
            date_filter_sql = "date = date('now')"
        else:
            date_filter_sql = "date >= date('now', 'start of month')"

        usage_query = f"""
            SELECT COALESCE(SUM(cost), 0.0) as total_cost
            FROM cost_usage
            WHERE workspace_id = ? AND {date_filter_sql}
        """
        cursor = conn.cursor()
        cursor.execute(usage_query, (workspace_id,))
        usage_row = cursor.fetchone()
        current_usage = float(usage_row[0]) if usage_row else 0.0

        # Query trend data (last N days)
        trend_query = f"""
            SELECT date, SUM(cost) as daily_cost
            FROM cost_usage
            WHERE workspace_id = ?
            AND date >= date('now', '-{trend_days} days')
            GROUP BY date
            ORDER BY date ASC
        """
        cursor.execute(trend_query, (workspace_id,))
        trend_rows = cursor.fetchall()
        trend = [
            {
                "date": row[0],
                "cost": float(row[1])
            }
            for row in trend_rows
        ]

        # Query breakdown by playbook
        breakdown_playbook_query = f"""
            SELECT playbook_code, SUM(cost) as total_cost
            FROM cost_usage
            WHERE workspace_id = ? AND {date_filter_sql}
            AND playbook_code IS NOT NULL
            GROUP BY playbook_code
        """
        cursor.execute(breakdown_playbook_query, (workspace_id,))
        breakdown_rows = cursor.fetchall()
        breakdown_by_playbook = {
            row[0]: float(row[1])
            for row in breakdown_rows
        }

        # Query breakdown by model
        breakdown_model_query = f"""
            SELECT model_name, SUM(cost) as total_cost
            FROM cost_usage
            WHERE workspace_id = ? AND {date_filter_sql}
            AND model_name IS NOT NULL
            GROUP BY model_name
        """
        cursor.execute(breakdown_model_query, (workspace_id,))
        breakdown_model_rows = cursor.fetchall()
        breakdown_by_model = {
            row[0]: float(row[1])
            for row in breakdown_model_rows
        }

        breakdown = {
            "by_playbook": breakdown_by_playbook,
            "by_model": breakdown_by_model,
        }

        return current_usage, trend, breakdown

    except Exception as e:
        logger.error(f"Failed to query cost usage from database: {e}", exc_info=True)
        return 0.0, [], {"by_playbook": {}, "by_model": {}}


@router.get("/cost/monitoring", response_model=CostMonitoringData)
async def get_cost_monitoring(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    period: str = Query("day", description="Period: 'day' or 'month'"),
):
    """
    Get cost monitoring data for a workspace

    Supports both Cloud (PostgreSQL) and Local-Core (SQLite) environments.
    If database is not available, returns zero usage (no cost tracking).
    """
    try:
        settings_store = SystemSettingsStore()

        # Get quota from settings
        if period == "day":
            quota = settings_store.get("governance.cost.quota.daily", 10.0)
        else:
            quota = settings_store.get("governance.cost.quota.monthly", 100.0)

        # Try to query from database (SQLite for Local-Core or PostgreSQL for Cloud)
        conn = _get_db_connection()
        if conn:
            # Database available: Query from database
            current_usage, trend, breakdown = _query_cost_usage_from_db(workspace_id, period)
        else:
            # No database available: Return zero usage (no cost tracking)
            current_usage = 0.0
            trend = []
            breakdown = {"by_playbook": {}, "by_model": {}}

        return CostMonitoringData(
            current_usage=current_usage,
            quota=quota,
            usage_percentage=(current_usage / quota * 100) if quota > 0 else 0,
            period=period,
            trend=trend,
            breakdown=breakdown,
        )
    except Exception as e:
        logger.error(f"Failed to get cost monitoring data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get cost monitoring data: {str(e)}")


def _query_governance_metrics_from_db(
    workspace_id: str,
    period: str
) -> tuple[Dict[str, float], List[Dict[str, Any]], Dict[str, Any], Optional[Dict[str, int]]]:
    """
    Query governance metrics from database (SQLite for Local-Core or PostgreSQL for Cloud)

    Args:
        workspace_id: Workspace ID
        period: Period ('day' or 'month')

    Returns:
        Tuple of (rejection_rate, cost_trend, violation_frequency, preflight_failure_reasons)
    """
    conn = _get_db_connection()
    if not conn:
        # Database not available, return zero metrics
        return (
            {
                "cost": 0.0,
                "node": 0.0,
                "policy": 0.0,
                "preflight": 0.0,
                "overall": 0.0,
            },
            [],
            {
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
            },
            {
                "missing_inputs": 0,
                "missing_credentials": 0,
                "environment_issues": 0,
            },
        )

    try:
        # Determine date range
        if period == "day":
            date_filter_sql = "timestamp >= date('now')"
        else:
            date_filter_sql = "timestamp >= date('now', 'start of month')"

        # Calculate rejection rate by layer
        rejection_rate_query = f"""
            SELECT
                layer,
                COUNT(*) as total,
                SUM(CASE WHEN approved = 0 THEN 1 ELSE 0 END) as rejected
            FROM governance_decisions
            WHERE workspace_id = ? AND {date_filter_sql}
            GROUP BY layer
        """
        cursor = conn.cursor()
        cursor.execute(rejection_rate_query, (workspace_id,))
        rejection_rows = cursor.fetchall()

        # Calculate rejection rates
        layer_totals = {}
        layer_rejected = {}
        for row in rejection_rows:
            layer = row[0]
            total = row[1]
            rejected = row[2]
            layer_totals[layer] = total
            layer_rejected[layer] = rejected

        rejection_rate = {
            "cost": (layer_rejected.get("cost", 0) / layer_totals.get("cost", 1)) * 100 if layer_totals.get("cost", 0) > 0 else 0.0,
            "node": (layer_rejected.get("node", 0) / layer_totals.get("node", 1)) * 100 if layer_totals.get("node", 0) > 0 else 0.0,
            "policy": (layer_rejected.get("policy", 0) / layer_totals.get("policy", 1)) * 100 if layer_totals.get("policy", 0) > 0 else 0.0,
            "preflight": (layer_rejected.get("preflight", 0) / layer_totals.get("preflight", 1)) * 100 if layer_totals.get("preflight", 0) > 0 else 0.0,
            "overall": 0.0,
        }
        # Calculate overall rejection rate
        total_all = sum(layer_totals.values())
        rejected_all = sum(layer_rejected.values())
        rejection_rate["overall"] = (rejected_all / total_all * 100) if total_all > 0 else 0.0

        # Query cost trend
        cost_trend_query = """
            SELECT date, SUM(cost) as daily_cost
            FROM cost_usage
            WHERE workspace_id = ?
            AND date >= date('now', '-30 days')
            GROUP BY date
            ORDER BY date ASC
        """
        cursor.execute(cost_trend_query, (workspace_id,))
        cost_trend_rows = cursor.fetchall()
        cost_trend = [
            {
                "date": row[0],
                "cost": float(row[1])
            }
            for row in cost_trend_rows
        ]

        # Query violation frequency
        violation_frequency_query = f"""
            SELECT
                layer,
                reason,
                COUNT(*) as count
            FROM governance_decisions
            WHERE workspace_id = ?
            AND approved = 0
            AND {date_filter_sql}
            GROUP BY layer, reason
        """
        cursor.execute(violation_frequency_query, (workspace_id,))
        violation_rows = cursor.fetchall()

        # Categorize violations
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
            count = row[2]

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

        # Query preflight failure reasons
        preflight_failure_query = f"""
            SELECT
                metadata,
                COUNT(*) as count
            FROM governance_decisions
            WHERE workspace_id = ?
            AND layer = 'preflight'
            AND approved = 0
            AND {date_filter_sql}
        """
        cursor.execute(preflight_failure_query, (workspace_id,))
        preflight_rows = cursor.fetchall()

        preflight_failure_reasons = {
            "missing_inputs": 0,
            "missing_credentials": 0,
            "environment_issues": 0,
        }

        for row in preflight_rows:
            metadata_str = row[0]
            count = row[1]
            if metadata_str:
                try:
                    import json
                    metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
                    if metadata.get("missing_inputs"):
                        preflight_failure_reasons["missing_inputs"] += count
                    if metadata.get("missing_credentials"):
                        preflight_failure_reasons["missing_credentials"] += count
                    if metadata.get("environment_issues"):
                        preflight_failure_reasons["environment_issues"] += count
                except Exception:
                    pass

        return (
            rejection_rate,
            cost_trend,
            violation_frequency,
            preflight_failure_reasons,
        )

    except Exception as e:
        logger.error(f"Failed to query governance metrics from database: {e}", exc_info=True)
        return (
            {
                "cost": 0.0,
                "node": 0.0,
                "policy": 0.0,
                "preflight": 0.0,
                "overall": 0.0,
            },
            [],
            {
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
            },
            {
                "missing_inputs": 0,
                "missing_credentials": 0,
                "environment_issues": 0,
            },
        )


@router.get("/metrics", response_model=GovernanceMetricsData)
async def get_governance_metrics(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    period: str = Query("day", description="Period: 'day' or 'month'"),
):
    """
    Get governance metrics for a workspace

    Supports both Cloud (PostgreSQL) and Local-Core (SQLite) environments.
    If database is not available, returns zero metrics (no historical data).
    """
    try:
        # Try to query from database (SQLite for Local-Core or PostgreSQL for Cloud)
        conn = _get_db_connection()
        if conn:
            # Database available: Query from database
            rejection_rate, cost_trend, violation_frequency, preflight_failure_reasons = (
                _query_governance_metrics_from_db(workspace_id, period)
            )
        else:
            # Local-Core: Return zero metrics (no historical data tracking)
            rejection_rate = {
                "cost": 0.0,
                "node": 0.0,
                "policy": 0.0,
                "preflight": 0.0,
                "overall": 0.0,
            }
            cost_trend = []
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
            preflight_failure_reasons = {
                "missing_inputs": 0,
                "missing_credentials": 0,
                "environment_issues": 0,
            }

        return GovernanceMetricsData(
            period=period,
            rejection_rate=rejection_rate,
            cost_trend=cost_trend,
            violation_frequency=violation_frequency,
            preflight_failure_reasons=preflight_failure_reasons,
        )
    except Exception as e:
        logger.error(f"Failed to get governance metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get governance metrics: {str(e)}")

