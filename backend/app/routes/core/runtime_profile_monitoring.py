"""
Runtime Profile Monitoring API endpoints

Provides monitoring and observability for Workspace Runtime Profile events:
- PolicyGuard events (policy_check)
- LoopBudget events (loop_budget_exhausted)
- QualityGates events (quality_gate_check)

All data is read from local SQLite database (no GCP dependencies).
"""

import logging
from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from backend.app.models.mindscape import EventType
from backend.app.services.stores.events_store import EventsStore
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/monitoring/runtime-profile",
    tags=["runtime-profile-monitoring"]
)


class PolicyCheckStats(BaseModel):
    """PolicyGuard statistics"""
    total: int = 0
    allowed: int = 0
    denied: int = 0
    requires_approval: int = 0
    denial_reasons: Dict[str, int] = Field(default_factory=dict)
    tool_usage: Dict[str, int] = Field(default_factory=dict)


class BudgetUsageStats(BaseModel):
    """LoopBudget usage statistics"""
    exhausted_count: int = 0
    average_usage_percentages: Dict[str, float] = Field(default_factory=dict)
    max_usage_percentages: Dict[str, float] = Field(default_factory=dict)
    exhausted_limits: Dict[str, int] = Field(default_factory=dict)


class QualityGateStats(BaseModel):
    """QualityGates statistics"""
    total: int = 0
    passed: int = 0
    failed: int = 0
    failed_gates: Dict[str, int] = Field(default_factory=dict)


class MonitoringOverview(BaseModel):
    """Monitoring overview data"""
    policy_checks: PolicyCheckStats
    budget_usage: BudgetUsageStats
    quality_gates: QualityGateStats
    time_range: Dict[str, str]


@router.get("/overview", response_model=MonitoringOverview)
async def get_monitoring_overview(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    hours: int = Query(24, ge=1, le=168, description="Time range in hours (1-168)")
):
    """
    Get monitoring overview for a workspace

    Returns aggregated statistics for PolicyGuard, LoopBudget, and QualityGates events
    within the specified time range.
    """
    try:
        settings_store = SystemSettingsStore()
        db_path = settings_store.get_database_path()
        events_store = EventsStore(db_path)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        # Get PolicyGuard events
        policy_events = events_store.get_events_by_workspace(
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )
        policy_events = [e for e in policy_events if e.event_type == EventType.POLICY_CHECK]

        # Get LoopBudget events
        budget_events = events_store.get_events_by_workspace(
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )
        budget_events = [e for e in budget_events if e.event_type == EventType.LOOP_BUDGET_EXHAUSTED]

        # Get QualityGates events
        quality_events = events_store.get_events_by_workspace(
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )
        quality_events = [e for e in quality_events if e.event_type == EventType.QUALITY_GATE_CHECK]

        # Aggregate PolicyGuard stats
        policy_stats = PolicyCheckStats(total=len(policy_events))
        for event in policy_events:
            payload = event.payload or {}
            if payload.get("allowed"):
                policy_stats.allowed += 1
            else:
                policy_stats.denied += 1

            if payload.get("requires_approval"):
                policy_stats.requires_approval += 1

            reason = payload.get("reason", "unknown")
            if reason:
                policy_stats.denial_reasons[reason] = policy_stats.denial_reasons.get(reason, 0) + 1

            tool_id = payload.get("tool_id", "unknown")
            if tool_id:
                policy_stats.tool_usage[tool_id] = policy_stats.tool_usage.get(tool_id, 0) + 1

        # Aggregate LoopBudget stats
        budget_stats = BudgetUsageStats()
        usage_percentages_list = []

        for event in budget_events:
            payload = event.payload or {}

            # Check if this is an exhaustion event
            if "exhausted_limits" in payload:
                budget_stats.exhausted_count += 1
                exhausted_limits = payload.get("exhausted_limits", [])
                for limit in exhausted_limits:
                    budget_stats.exhausted_limits[limit] = budget_stats.exhausted_limits.get(limit, 0) + 1

            # Collect usage percentages
            usage_percentages = payload.get("usage_percentages", {})
            if usage_percentages:
                usage_percentages_list.append(usage_percentages)

        # Calculate average and max usage percentages
        if usage_percentages_list:
            all_keys = set()
            for up in usage_percentages_list:
                all_keys.update(up.keys())

            for key in all_keys:
                values = [up.get(key, 0) for up in usage_percentages_list if key in up]
                if values:
                    budget_stats.average_usage_percentages[key] = sum(values) / len(values)
                    budget_stats.max_usage_percentages[key] = max(values)

        # Aggregate QualityGates stats
        quality_stats = QualityGateStats(total=len(quality_events))
        for event in quality_events:
            payload = event.payload or {}
            if payload.get("passed"):
                quality_stats.passed += 1
            else:
                quality_stats.failed += 1
                failed_gates = payload.get("failed_gates", [])
                for gate in failed_gates:
                    quality_stats.failed_gates[gate] = quality_stats.failed_gates.get(gate, 0) + 1

        return MonitoringOverview(
            policy_checks=policy_stats,
            budget_usage=budget_stats,
            quality_gates=quality_stats,
            time_range={
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "hours": hours
            }
        )

    except Exception as e:
        logger.error(f"Failed to get monitoring overview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get monitoring overview: {str(e)}")


@router.get("/policy-checks", response_model=List[Dict[str, Any]])
async def get_policy_checks(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    hours: int = Query(24, ge=1, le=168, description="Time range in hours (1-168)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return")
):
    """
    Get PolicyGuard events for a workspace

    Returns list of policy check events with details.
    """
    try:
        settings_store = SystemSettingsStore()
        db_path = settings_store.get_database_path()
        events_store = EventsStore(db_path)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        events = events_store.get_events_by_workspace(
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        policy_events = [e for e in events if e.event_type == EventType.POLICY_CHECK]

        return [
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat(),
                "execution_id": event.payload.get("execution_id") if event.payload else None,
                "tool_id": event.payload.get("tool_id") if event.payload else None,
                "capability_code": event.payload.get("capability_code") if event.payload else None,
                "risk_class": event.payload.get("risk_class") if event.payload else None,
                "allowed": event.payload.get("allowed") if event.payload else None,
                "requires_approval": event.payload.get("requires_approval") if event.payload else None,
                "reason": event.payload.get("reason") if event.payload else None,
            }
            for event in policy_events
        ]

    except Exception as e:
        logger.error(f"Failed to get policy checks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get policy checks: {str(e)}")


@router.get("/budget-usage", response_model=List[Dict[str, Any]])
async def get_budget_usage(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    hours: int = Query(24, ge=1, le=168, description="Time range in hours (1-168)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return")
):
    """
    Get LoopBudget usage events for a workspace

    Returns list of budget usage and exhaustion events.
    """
    try:
        settings_store = SystemSettingsStore()
        db_path = settings_store.get_database_path()
        events_store = EventsStore(db_path)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        events = events_store.get_events_by_workspace(
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        budget_events = [e for e in events if e.event_type == EventType.LOOP_BUDGET_EXHAUSTED]

        return [
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat(),
                "execution_id": event.payload.get("execution_id") if event.payload else None,
                "metric_type": event.payload.get("metric_type") if event.payload else None,
                "current_value": event.payload.get("current_value") if event.payload else None,
                "usage_percentages": event.payload.get("usage_percentages") if event.payload else None,
                "exhausted_limits": event.payload.get("exhausted_limits") if event.payload else None,
                "current_state": event.payload.get("current_state") if event.payload else None,
                "budget_limits": event.payload.get("budget_limits") if event.payload else None,
            }
            for event in budget_events
        ]

    except Exception as e:
        logger.error(f"Failed to get budget usage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get budget usage: {str(e)}")


@router.get("/quality-gates", response_model=List[Dict[str, Any]])
async def get_quality_gates(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    hours: int = Query(24, ge=1, le=168, description="Time range in hours (1-168)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return")
):
    """
    Get QualityGates events for a workspace

    Returns list of quality gate check events.
    """
    try:
        settings_store = SystemSettingsStore()
        db_path = settings_store.get_database_path()
        events_store = EventsStore(db_path)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        events = events_store.get_events_by_workspace(
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        quality_events = [e for e in events if e.event_type == EventType.QUALITY_GATE_CHECK]

        return [
            {
                "id": event.id,
                "timestamp": event.timestamp.isoformat(),
                "execution_id": event.payload.get("execution_id") if event.payload else None,
                "passed": event.payload.get("passed") if event.payload else None,
                "failed_gates": event.payload.get("failed_gates") if event.payload else None,
                "details": event.payload.get("details") if event.payload else None,
                "enabled_gates": event.payload.get("enabled_gates") if event.payload else None,
            }
            for event in quality_events
        ]

    except Exception as e:
        logger.error(f"Failed to get quality gates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get quality gates: {str(e)}")

