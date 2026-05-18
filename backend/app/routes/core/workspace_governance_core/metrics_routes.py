import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam

from backend.app.services.system_settings_store import SystemSettingsStore

from .schemas import (
    CostMonitoringData,
    GovernanceDecision,
    GovernanceDecisionsResponse,
    GovernanceMetricsData,
)
from .stores import _get_store

logger = logging.getLogger(__name__)
router = APIRouter()


async def _query_governance_decisions_from_db(
    workspace_id: str,
    layer: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    page: int,
    limit: int,
) -> tuple[List[Dict[str, Any]], int]:
    """
    Query governance decisions from PostgreSQL store
    """
    try:
        store = _get_store()
        return await asyncio.to_thread(
            store.list_decisions,
            workspace_id=workspace_id,
            layer=layer,
            start_date=start_date,
            end_date=end_date,
            page=page,
            limit=limit,
        )

    except Exception as e:
        logger.error(
            f"Failed to query governance decisions from database: {e}", exc_info=True
        )
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

    Uses PostgreSQL governance tables. If unavailable, returns empty results.
    """
    try:
        decisions_data, total = await _query_governance_decisions_from_db(
            workspace_id, layer, start_date, end_date, page, limit
        )
        decisions = [
            GovernanceDecision(**decision_data) for decision_data in decisions_data
        ]

        return GovernanceDecisionsResponse(
            decisions=decisions,
            total=total,
            page=page,
            limit=limit,
            total_pages=0 if total == 0 else (total + limit - 1) // limit,
        )
    except Exception as e:
        logger.error(f"Failed to get governance decisions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get governance decisions: {str(e)}"
        )


async def _query_cost_usage_from_db(
    workspace_id: str, period: str
) -> tuple[float, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Query cost usage from PostgreSQL store
    """
    try:
        store = _get_store()
        return await asyncio.to_thread(
            store.get_cost_usage_summary, workspace_id, period
        )

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

    Uses PostgreSQL cost usage tables. If unavailable, returns zero usage.
    """
    try:
        settings_store = SystemSettingsStore()

        # Get quota from settings
        if period == "day":
            quota = await asyncio.to_thread(
                settings_store.get, "governance.cost.quota.daily", 10.0
            )
        else:
            quota = await asyncio.to_thread(
                settings_store.get, "governance.cost.quota.monthly", 100.0
            )

        current_usage, trend, breakdown = await _query_cost_usage_from_db(
            workspace_id, period
        )

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
        raise HTTPException(
            status_code=500, detail=f"Failed to get cost monitoring data: {str(e)}"
        )


async def _query_governance_metrics_from_db(
    workspace_id: str, period: str
) -> tuple[
    Dict[str, float], List[Dict[str, Any]], Dict[str, Any], Optional[Dict[str, int]]
]:
    """
    Query governance metrics from PostgreSQL store
    """
    try:
        store = _get_store()
        return await asyncio.to_thread(
            store.get_governance_metrics, workspace_id, period
        )

    except Exception as e:
        logger.error(
            f"Failed to query governance metrics from database: {e}", exc_info=True
        )
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

    Uses PostgreSQL governance tables. If unavailable, returns zero metrics.
    """
    try:
        rejection_rate, cost_trend, violation_frequency, preflight_failure_reasons = (
            await _query_governance_metrics_from_db(workspace_id, period)
        )

        return GovernanceMetricsData(
            period=period,
            rejection_rate=rejection_rate,
            cost_trend=cost_trend,
            violation_frequency=violation_frequency,
            preflight_failure_reasons=preflight_failure_reasons,
        )
    except Exception as e:
        logger.error(f"Failed to get governance metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get governance metrics: {str(e)}"
        )
