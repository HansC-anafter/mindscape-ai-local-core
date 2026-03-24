"""
Workspace governance API endpoints

Handles workspace-level governance queries:
- Governance decision history
- Cost monitoring
- Governance metrics

Note: These endpoints rely on PostgreSQL as the primary governance store.
If governance tables are unavailable, endpoints return empty results or zero values.
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta

from backend.app.services.system_settings_store import SystemSettingsStore
from backend.app.services.governance.governance_store import GovernanceStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/governance", tags=["workspace-governance"]
)


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


class MemoryTransitionRequest(BaseModel):
    """Workspace-scoped canonical memory transition request."""

    action: Literal["verify", "stale", "supersede"]
    reason: str = ""
    idempotency_key: Optional[str] = None
    successor_memory_item_id: Optional[str] = None
    successor_title: Optional[str] = None
    successor_claim: Optional[str] = None
    successor_summary: Optional[str] = None


class MemoryTransitionResponse(BaseModel):
    """Response from a canonical memory transition."""

    workspace_id: str
    memory_item_id: str
    transition: str
    noop: bool
    lifecycle_status: str
    verification_status: str
    run_id: str
    successor_memory_item_id: Optional[str] = None


class WorkspaceMemoryItemSummary(BaseModel):
    """Workspace-scoped canonical memory summary."""

    id: str
    kind: str
    layer: str
    title: str
    claim: str
    summary: str
    lifecycle_status: str
    verification_status: str
    salience: float
    confidence: float
    subject_type: str
    subject_id: str
    supersedes_memory_id: Optional[str] = None
    observed_at: datetime
    last_confirmed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WorkspaceMemoryListResponse(BaseModel):
    """Response model for workspace canonical memory list."""

    workspace_id: str
    items: List[WorkspaceMemoryItemSummary]
    total: int
    limit: int


class MemoryVersionSummary(BaseModel):
    id: str
    version_no: int
    update_mode: str
    claim_snapshot: str
    summary_snapshot: Optional[str] = None
    metadata_snapshot: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    created_from_run_id: Optional[str] = None


class MemoryEvidenceSummary(BaseModel):
    id: str
    evidence_type: str
    evidence_id: str
    link_role: str
    excerpt: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MemoryEdgeSummary(BaseModel):
    id: str
    from_memory_id: str
    to_memory_id: str
    edge_type: str
    weight: Optional[float] = None
    valid_from: datetime
    valid_to: Optional[datetime] = None
    evidence_strength: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class PersonalKnowledgeProjectionSummary(BaseModel):
    id: str
    knowledge_type: str
    content: str
    status: str
    confidence: float
    created_at: datetime
    last_verified_at: Optional[datetime] = None


class GoalLedgerProjectionSummary(BaseModel):
    id: str
    title: str
    description: str
    status: str
    horizon: str
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class WorkspaceMemoryDetailResponse(BaseModel):
    workspace_id: str
    memory_item: WorkspaceMemoryItemSummary
    versions: List[MemoryVersionSummary]
    evidence: List[MemoryEvidenceSummary]
    outgoing_edges: List[MemoryEdgeSummary]
    personal_knowledge_projections: List[PersonalKnowledgeProjectionSummary]
    goal_projections: List[GoalLedgerProjectionSummary]


def _get_memory_item_store():
    from backend.app.services.stores.postgres.memory_item_store import MemoryItemStore

    return MemoryItemStore()


def _get_memory_version_store():
    from backend.app.services.stores.postgres.memory_version_store import (
        MemoryVersionStore,
    )

    return MemoryVersionStore()


def _get_memory_evidence_link_store():
    from backend.app.services.stores.postgres.memory_evidence_link_store import (
        MemoryEvidenceLinkStore,
    )

    return MemoryEvidenceLinkStore()


def _get_memory_edge_store():
    from backend.app.services.stores.postgres.memory_edge_store import MemoryEdgeStore

    return MemoryEdgeStore()


def _get_memory_promotion_service():
    from backend.app.services.memory.promotion_service import MemoryPromotionService

    return MemoryPromotionService()


def _get_personal_knowledge_store():
    from backend.app.services.stores.postgres.personal_knowledge_store import (
        PersonalKnowledgeStore,
    )

    return PersonalKnowledgeStore()


def _get_goal_ledger_store():
    from backend.app.services.stores.postgres.goal_ledger_store import GoalLedgerStore

    return GoalLedgerStore()


async def _load_workspace_memory_item(workspace_id: str, memory_item_id: str):
    store = _get_memory_item_store()
    item = await asyncio.to_thread(store.get, memory_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    if item.context_type != "workspace" or item.context_id != workspace_id:
        raise HTTPException(status_code=404, detail="Memory item not found in workspace")
    return item


def _get_store() -> GovernanceStore:
    return GovernanceStore()


def _serialize_workspace_memory_item(item) -> WorkspaceMemoryItemSummary:
    return WorkspaceMemoryItemSummary(
        id=item.id,
        kind=item.kind,
        layer=item.layer,
        title=item.title,
        claim=item.claim,
        summary=item.summary,
        lifecycle_status=item.lifecycle_status,
        verification_status=item.verification_status,
        salience=item.salience,
        confidence=item.confidence,
        subject_type=item.subject_type,
        subject_id=item.subject_id,
        supersedes_memory_id=getattr(item, "supersedes_memory_id", None),
        observed_at=item.observed_at,
        last_confirmed_at=getattr(item, "last_confirmed_at", None),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _serialize_memory_version(version) -> MemoryVersionSummary:
    return MemoryVersionSummary(
        id=version.id,
        version_no=version.version_no,
        update_mode=version.update_mode,
        claim_snapshot=version.claim_snapshot,
        summary_snapshot=version.summary_snapshot,
        metadata_snapshot=dict(getattr(version, "metadata_snapshot", {}) or {}),
        created_at=version.created_at,
        created_from_run_id=getattr(version, "created_from_run_id", None),
    )


def _serialize_memory_evidence(link) -> MemoryEvidenceSummary:
    return MemoryEvidenceSummary(
        id=link.id,
        evidence_type=link.evidence_type,
        evidence_id=link.evidence_id,
        link_role=link.link_role,
        excerpt=getattr(link, "excerpt", None),
        confidence=getattr(link, "confidence", None),
        metadata=dict(getattr(link, "metadata", {}) or {}),
        created_at=link.created_at,
    )


def _serialize_memory_edge(edge) -> MemoryEdgeSummary:
    return MemoryEdgeSummary(
        id=edge.id,
        from_memory_id=edge.from_memory_id,
        to_memory_id=edge.to_memory_id,
        edge_type=edge.edge_type,
        weight=getattr(edge, "weight", None),
        valid_from=edge.valid_from,
        valid_to=getattr(edge, "valid_to", None),
        evidence_strength=getattr(edge, "evidence_strength", None),
        metadata=dict(getattr(edge, "metadata", {}) or {}),
        created_at=edge.created_at,
    )


def _serialize_personal_knowledge_projection(entry) -> PersonalKnowledgeProjectionSummary:
    return PersonalKnowledgeProjectionSummary(
        id=entry.id,
        knowledge_type=entry.knowledge_type,
        content=entry.content,
        status=entry.status,
        confidence=entry.confidence,
        created_at=entry.created_at,
        last_verified_at=getattr(entry, "last_verified_at", None),
    )


def _serialize_goal_projection(entry) -> GoalLedgerProjectionSummary:
    return GoalLedgerProjectionSummary(
        id=entry.id,
        title=entry.title,
        description=entry.description,
        status=entry.status,
        horizon=entry.horizon,
        created_at=entry.created_at,
        confirmed_at=getattr(entry, "confirmed_at", None),
    )


@router.get("/memory", response_model=WorkspaceMemoryListResponse)
async def list_workspace_memory_items(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    kind: Optional[str] = Query(None, description="Filter by memory kind"),
    layer: Optional[str] = Query(None, description="Filter by memory layer"),
    lifecycle_status: Optional[List[str]] = Query(
        None,
        description="Filter by lifecycle status",
    ),
    verification_status: Optional[List[str]] = Query(
        None,
        description="Filter by verification status",
    ),
    limit: int = Query(20, ge=1, le=100, description="Items to return"),
):
    """List canonical memory items for a workspace."""
    item_store = _get_memory_item_store()
    items = await asyncio.to_thread(
        item_store.list_for_context,
        context_type="workspace",
        context_id=workspace_id,
        layer=layer,
        kind=kind,
        lifecycle_statuses=lifecycle_status,
        verification_statuses=verification_status,
        limit=limit,
    )
    return WorkspaceMemoryListResponse(
        workspace_id=workspace_id,
        items=[_serialize_workspace_memory_item(item) for item in items],
        total=len(items),
        limit=limit,
    )


@router.get("/memory/{memory_item_id}", response_model=WorkspaceMemoryDetailResponse)
async def get_workspace_memory_item_detail(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    memory_item_id: str = PathParam(..., description="Canonical memory item ID"),
):
    """Get a canonical memory item with versions, evidence, and legacy projections."""
    memory_item = await _load_workspace_memory_item(workspace_id, memory_item_id)
    version_store = _get_memory_version_store()
    evidence_store = _get_memory_evidence_link_store()
    edge_store = _get_memory_edge_store()
    personal_knowledge_store = _get_personal_knowledge_store()
    goal_ledger_store = _get_goal_ledger_store()

    versions = await asyncio.to_thread(version_store.list_by_memory_item, memory_item_id)
    evidence_links = await asyncio.to_thread(
        evidence_store.list_by_memory_item, memory_item_id
    )
    outgoing_edges = await asyncio.to_thread(edge_store.list_from_memory, memory_item_id)
    knowledge_projections = await asyncio.to_thread(
        personal_knowledge_store.list_by_canonical_memory_item,
        memory_item_id,
    )
    goal_projections = await asyncio.to_thread(
        goal_ledger_store.list_by_canonical_memory_item,
        memory_item_id,
    )

    return WorkspaceMemoryDetailResponse(
        workspace_id=workspace_id,
        memory_item=_serialize_workspace_memory_item(memory_item),
        versions=[_serialize_memory_version(version) for version in versions],
        evidence=[_serialize_memory_evidence(link) for link in evidence_links],
        outgoing_edges=[_serialize_memory_edge(edge) for edge in outgoing_edges],
        personal_knowledge_projections=[
            _serialize_personal_knowledge_projection(entry)
            for entry in knowledge_projections
        ],
        goal_projections=[
            _serialize_goal_projection(entry) for entry in goal_projections
        ],
    )


@router.post(
    "/memory/{memory_item_id}/transition",
    response_model=MemoryTransitionResponse,
)
async def transition_workspace_memory_item(
    request: MemoryTransitionRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
    memory_item_id: str = PathParam(..., description="Canonical memory item ID"),
):
    """Apply a deterministic lifecycle transition to a workspace memory item."""
    await _load_workspace_memory_item(workspace_id, memory_item_id)
    promotion_service = _get_memory_promotion_service()

    try:
        if request.action == "verify":
            result = await asyncio.to_thread(
                promotion_service.verify_candidate,
                memory_item_id,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
            )
        elif request.action == "stale":
            result = await asyncio.to_thread(
                promotion_service.mark_stale,
                memory_item_id,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
            )
        else:
            result = await asyncio.to_thread(
                promotion_service.supersede_memory,
                memory_item_id,
                successor_memory_item_id=request.successor_memory_item_id,
                successor_title=request.successor_title,
                successor_claim=request.successor_claim,
                successor_summary=request.successor_summary,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    memory_item = result["memory_item"]
    successor_item = result.get("successor_memory_item")
    run = result["run"]
    return MemoryTransitionResponse(
        workspace_id=workspace_id,
        memory_item_id=memory_item.id,
        transition=request.action,
        noop=bool(result.get("noop")),
        lifecycle_status=memory_item.lifecycle_status,
        verification_status=memory_item.verification_status,
        run_id=run.id,
        successor_memory_item_id=getattr(successor_item, "id", None),
    )


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
