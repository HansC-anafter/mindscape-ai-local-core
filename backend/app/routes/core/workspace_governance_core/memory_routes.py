import asyncio
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam

from backend.app.services.governance.memory_impact_graph_contract import (
    MemoryImpactGraphResponse,
)

from .schemas import (
    MemoryTransitionRequest,
    MemoryTransitionResponse,
    WorkflowEvidenceHealthSummaryResponse,
    WorkspaceMemoryDetailResponse,
    WorkspaceMemoryListResponse,
)
from .serializers import (
    _build_evidence_coverage,
    _select_primary_evidence,
    _serialize_goal_projection,
    _serialize_memory_edge,
    _serialize_memory_evidence,
    _serialize_memory_version,
    _serialize_personal_knowledge_projection,
    _serialize_workspace_memory_item,
)
from .stores import (
    _get_goal_ledger_store,
    _get_meeting_session_store,
    _get_memory_edge_store,
    _get_memory_evidence_link_store,
    _get_memory_impact_graph_read_model,
    _get_memory_item_store,
    _get_memory_promotion_service,
    _get_memory_version_store,
    _get_personal_knowledge_store,
    _load_workspace_memory_item,
)
from .transition_suggestions import (
    _build_successor_draft_suggestion,
    _build_transition_cues,
    _build_transition_reason_suggestions,
)
from .workflow_health import _serialize_workflow_evidence_health_session

router = APIRouter()


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
    serialized_item = _serialize_workspace_memory_item(memory_item)
    serialized_evidence = [_serialize_memory_evidence(link) for link in evidence_links]
    evidence_coverage = _build_evidence_coverage(serialized_evidence)
    primary_evidence = _select_primary_evidence(serialized_evidence)
    transition_cues = _build_transition_cues(
        serialized_item,
        serialized_evidence,
        evidence_coverage,
    )
    successor_draft_suggestion = _build_successor_draft_suggestion(
        serialized_item,
        serialized_evidence,
        evidence_coverage,
    )
    transition_reason_suggestions = _build_transition_reason_suggestions(
        serialized_item,
        primary_evidence,
        evidence_coverage,
    )

    return WorkspaceMemoryDetailResponse(
        workspace_id=workspace_id,
        memory_item=serialized_item,
        versions=[_serialize_memory_version(version) for version in versions],
        evidence=serialized_evidence,
        outgoing_edges=[_serialize_memory_edge(edge) for edge in outgoing_edges],
        personal_knowledge_projections=[
            _serialize_personal_knowledge_projection(entry)
            for entry in knowledge_projections
        ],
        goal_projections=[
            _serialize_goal_projection(entry) for entry in goal_projections
        ],
        evidence_coverage=evidence_coverage,
        transition_cues=transition_cues,
        successor_draft_suggestion=successor_draft_suggestion,
        transition_reason_suggestions=transition_reason_suggestions,
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


@router.get("/memory-health", response_model=WorkflowEvidenceHealthSummaryResponse)
async def get_workspace_memory_health(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    project_id: Optional[str] = Query(None, description="Project scope"),
    thread_id: Optional[str] = Query(None, description="Thread scope"),
    limit: int = Query(5, ge=1, le=20, description="Recent meeting sessions to inspect"),
):
    """Aggregate recent workflow evidence diagnostics for operator-facing memory health."""
    session_store = _get_meeting_session_store()
    sessions = await asyncio.to_thread(
        session_store.list_by_workspace,
        workspace_id,
        project_id,
        max(limit * 3, limit),
        0,
    )

    filtered_sessions = [
        session
        for session in sessions
        if not thread_id or getattr(session, "thread_id", None) == thread_id
    ]
    serialized_sessions = [
        summary
        for summary in (
            _serialize_workflow_evidence_health_session(session)
            for session in filtered_sessions
        )
        if summary is not None
    ][:limit]

    sampled_sessions = len(serialized_sessions)
    if sampled_sessions == 0:
        return WorkflowEvidenceHealthSummaryResponse(
            workspace_id=workspace_id,
            project_id=project_id,
            thread_id=thread_id,
            sampled_sessions=0,
            average_utilization_ratio=0.0,
            average_selected_line_count=0.0,
            average_total_dropped_count=0.0,
            balanced_count=0,
            tight_count=0,
            sparse_count=0,
            underused_count=0,
            narrow_count=0,
            empty_count=0,
            latest=None,
            sessions=[],
        )

    counts = {
        "balanced": 0,
        "tight": 0,
        "sparse": 0,
        "underused": 0,
        "narrow": 0,
        "empty": 0,
    }
    for session in serialized_sessions:
        counts[session.classification] += 1

    average_utilization_ratio = round(
        sum(session.budget_utilization_ratio for session in serialized_sessions)
        / sampled_sessions,
        3,
    )
    average_selected_line_count = round(
        sum(session.selected_line_count for session in serialized_sessions)
        / sampled_sessions,
        2,
    )
    average_total_dropped_count = round(
        sum(session.total_dropped_count for session in serialized_sessions)
        / sampled_sessions,
        2,
    )

    return WorkflowEvidenceHealthSummaryResponse(
        workspace_id=workspace_id,
        project_id=project_id,
        thread_id=thread_id,
        sampled_sessions=sampled_sessions,
        average_utilization_ratio=average_utilization_ratio,
        average_selected_line_count=average_selected_line_count,
        average_total_dropped_count=average_total_dropped_count,
        balanced_count=counts["balanced"],
        tight_count=counts["tight"],
        sparse_count=counts["sparse"],
        underused_count=counts["underused"],
        narrow_count=counts["narrow"],
        empty_count=counts["empty"],
        latest=serialized_sessions[0],
        sessions=serialized_sessions,
    )


@router.get("/memory-impact-graph", response_model=MemoryImpactGraphResponse)
async def get_workspace_memory_impact_graph(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    session_id: Optional[str] = Query(None, description="Meeting session ID"),
    execution_id: Optional[str] = Query(None, description="Execution ID"),
    thread_id: Optional[str] = Query(None, description="Thread ID"),
):
    """Return the task-centered selected memory subgraph for a workspace session."""
    read_model = _get_memory_impact_graph_read_model()
    try:
        return await asyncio.to_thread(
            read_model.build_for_workspace,
            workspace_id,
            session_id=session_id,
            execution_id=execution_id,
            thread_id=thread_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
