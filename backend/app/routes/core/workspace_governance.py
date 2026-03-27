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
from pathlib import Path
from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta

from backend.app.services.governance.memory_impact_graph_contract import (
    MemoryImpactGraphResponse,
)
from backend.app.services.governance.memory_impact_graph_read_model import (
    MemoryImpactGraphReadModel,
)
from backend.app.services.system_settings_store import SystemSettingsStore
from backend.app.services.governance.governance_store import GovernanceStore

logger = logging.getLogger(__name__)

# Mounted beneath the parent workspace router at /api/v1/workspaces.
router = APIRouter(prefix="/{workspace_id}/governance", tags=["workspace-governance"])


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
    artifact_landing: Optional["ArtifactLandingDrilldownSummary"] = None
    execution_trace_drilldown: Optional["ExecutionTraceDrilldownSummary"] = None


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


class EvidenceCoverageSummary(BaseModel):
    deliberation: int
    execution: int
    governance: int
    support: int
    derived: int


class TransitionCueSummary(BaseModel):
    id: str
    tone: Literal["positive", "neutral", "caution"]
    title: str
    body: str


class SuccessorDraftSuggestionSummary(BaseModel):
    title: str
    claim: str
    summary: str
    primary_evidence_id: Optional[str] = None
    primary_evidence_type: Optional[str] = None


class TransitionReasonSuggestions(BaseModel):
    verify: str
    stale: str
    supersede: str


class ArtifactLandingDrilldownSummary(BaseModel):
    artifact_dir: Optional[str] = None
    result_json_path: Optional[str] = None
    summary_md_path: Optional[str] = None
    attachments_count: int = 0
    attachments: List[str] = Field(default_factory=list)
    landed_at: Optional[str] = None
    artifact_dir_exists: bool = False
    result_json_exists: bool = False
    summary_md_exists: bool = False


class ExecutionTraceDrilldownSummary(BaseModel):
    trace_source: Optional[str] = None
    trace_file_path: Optional[str] = None
    trace_file_exists: bool = False
    sandbox_path: Optional[str] = None
    tool_call_count: int = 0
    file_change_count: int = 0
    files_created_count: int = 0
    files_modified_count: int = 0
    success: Optional[bool] = None
    duration_seconds: Optional[float] = None
    task_description: Optional[str] = None
    output_summary: Optional[str] = None


MemoryEvidenceSummary.model_rebuild()


class WorkspaceMemoryDetailResponse(BaseModel):
    workspace_id: str
    memory_item: WorkspaceMemoryItemSummary
    versions: List[MemoryVersionSummary]
    evidence: List[MemoryEvidenceSummary]
    outgoing_edges: List[MemoryEdgeSummary]
    personal_knowledge_projections: List[PersonalKnowledgeProjectionSummary]
    goal_projections: List[GoalLedgerProjectionSummary]
    evidence_coverage: EvidenceCoverageSummary
    transition_cues: List[TransitionCueSummary]
    successor_draft_suggestion: Optional[SuccessorDraftSuggestionSummary] = None
    transition_reason_suggestions: TransitionReasonSuggestions


class WorkflowEvidenceHealthSessionSummary(BaseModel):
    session_id: str
    project_id: Optional[str] = None
    thread_id: Optional[str] = None
    meeting_type: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    profile: str
    scope: str
    total_candidate_count: int
    selected_line_count: int
    total_line_budget: int
    total_dropped_count: int
    rendered_section_count: int
    budget_utilization_ratio: float
    classification: Literal[
        "balanced", "tight", "sparse", "underused", "narrow", "empty"
    ]


class WorkflowEvidenceHealthSummaryResponse(BaseModel):
    workspace_id: str
    project_id: Optional[str] = None
    thread_id: Optional[str] = None
    sampled_sessions: int
    average_utilization_ratio: float
    average_selected_line_count: float
    average_total_dropped_count: float
    balanced_count: int
    tight_count: int
    sparse_count: int
    underused_count: int
    narrow_count: int
    empty_count: int
    latest: Optional[WorkflowEvidenceHealthSessionSummary] = None
    sessions: List[WorkflowEvidenceHealthSessionSummary]


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


def _get_meeting_session_store():
    from backend.app.services.stores.meeting_session_store import MeetingSessionStore

    return MeetingSessionStore()


def _get_memory_impact_graph_read_model():
    return MemoryImpactGraphReadModel(
        meeting_session_store=_get_meeting_session_store(),
        memory_item_store=_get_memory_item_store(),
    )


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


def _path_exists(path_value: Any) -> bool:
    if not isinstance(path_value, str) or not path_value.strip():
        return False
    try:
        return Path(path_value).exists()
    except Exception:
        return False


def _build_artifact_landing_drilldown(
    metadata: Dict[str, Any],
) -> Optional[ArtifactLandingDrilldownSummary]:
    artifact_dir = metadata.get("landing_artifact_dir")
    result_json_path = metadata.get("landing_result_json_path")
    summary_md_path = metadata.get("landing_summary_md_path")
    attachments_count = metadata.get("landing_attachments_count")
    attachments = metadata.get("landing_attachments")
    landed_at = metadata.get("landing_landed_at")
    if not any(
        [
            artifact_dir,
            result_json_path,
            summary_md_path,
            attachments_count,
            attachments,
            landed_at,
        ]
    ):
        return None

    normalized_attachments = [
        value.strip()
        for value in attachments or []
        if isinstance(value, str) and value.strip()
    ]
    return ArtifactLandingDrilldownSummary(
        artifact_dir=artifact_dir if isinstance(artifact_dir, str) else None,
        result_json_path=result_json_path
        if isinstance(result_json_path, str)
        else None,
        summary_md_path=summary_md_path if isinstance(summary_md_path, str) else None,
        attachments_count=attachments_count if isinstance(attachments_count, int) else 0,
        attachments=normalized_attachments,
        landed_at=landed_at if isinstance(landed_at, str) else None,
        artifact_dir_exists=_path_exists(artifact_dir),
        result_json_exists=_path_exists(result_json_path),
        summary_md_exists=_path_exists(summary_md_path),
    )


def _build_execution_trace_drilldown(
    metadata: Dict[str, Any],
) -> Optional[ExecutionTraceDrilldownSummary]:
    trace_source = metadata.get("trace_source")
    trace_file_path = metadata.get("trace_file_path")
    sandbox_path = metadata.get("sandbox_path")
    if not any([trace_source, trace_file_path, sandbox_path]):
        return None
    return ExecutionTraceDrilldownSummary(
        trace_source=trace_source if isinstance(trace_source, str) else None,
        trace_file_path=trace_file_path if isinstance(trace_file_path, str) else None,
        trace_file_exists=_path_exists(trace_file_path),
        sandbox_path=sandbox_path if isinstance(sandbox_path, str) else None,
        tool_call_count=metadata.get("tool_call_count")
        if isinstance(metadata.get("tool_call_count"), int)
        else 0,
        file_change_count=metadata.get("file_change_count")
        if isinstance(metadata.get("file_change_count"), int)
        else 0,
        files_created_count=metadata.get("files_created_count")
        if isinstance(metadata.get("files_created_count"), int)
        else 0,
        files_modified_count=metadata.get("files_modified_count")
        if isinstance(metadata.get("files_modified_count"), int)
        else 0,
        success=metadata.get("success")
        if isinstance(metadata.get("success"), bool)
        else None,
        duration_seconds=float(metadata.get("duration_seconds"))
        if isinstance(metadata.get("duration_seconds"), (int, float))
        else None,
        task_description=metadata.get("task_description")
        if isinstance(metadata.get("task_description"), str)
        else None,
        output_summary=metadata.get("output_summary")
        if isinstance(metadata.get("output_summary"), str)
        else None,
    )


def _serialize_memory_evidence(link) -> MemoryEvidenceSummary:
    metadata = dict(getattr(link, "metadata", {}) or {})
    return MemoryEvidenceSummary(
        id=link.id,
        evidence_type=link.evidence_type,
        evidence_id=link.evidence_id,
        link_role=link.link_role,
        excerpt=getattr(link, "excerpt", None),
        confidence=getattr(link, "confidence", None),
        metadata=metadata,
        created_at=link.created_at,
        artifact_landing=_build_artifact_landing_drilldown(metadata)
        if link.evidence_type == "artifact_result"
        else None,
        execution_trace_drilldown=_build_execution_trace_drilldown(metadata)
        if link.evidence_type == "execution_trace"
        else None,
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


def _evidence_display_name(evidence_type: str) -> str:
    if evidence_type == "session_digest":
        return "Session Digest"
    if evidence_type == "meeting_decision":
        return "Meeting Decision"
    if evidence_type == "reasoning_trace":
        return "Reasoning Trace"
    if evidence_type == "intent_log":
        return "Intent Log"
    if evidence_type == "governance_decision":
        return "Governance Decision"
    if evidence_type == "lens_patch":
        return "Lens Patch"
    if evidence_type == "task_execution":
        return "Task Execution"
    if evidence_type == "execution_trace":
        return "Execution Trace"
    if evidence_type == "stage_result":
        return "Stage Result"
    if evidence_type == "artifact_result":
        return "Artifact Result"
    if evidence_type == "lens_receipt":
        return "Lens Receipt"
    if evidence_type == "writeback_receipt":
        return "Writeback Receipt"
    return evidence_type.replace("_", " ").title()


def _build_evidence_coverage(
    evidence_links: List[MemoryEvidenceSummary],
) -> EvidenceCoverageSummary:
    coverage = {
        "deliberation": 0,
        "execution": 0,
        "governance": 0,
        "support": 0,
        "derived": 0,
    }
    for link in evidence_links:
        if link.evidence_type in {
            "session_digest",
            "meeting_decision",
            "reasoning_trace",
        }:
            coverage["deliberation"] += 1
        if link.evidence_type in {
            "task_execution",
            "execution_trace",
            "stage_result",
            "artifact_result",
            "lens_receipt",
        }:
            coverage["execution"] += 1
        if link.evidence_type in {
            "writeback_receipt",
            "intent_log",
            "governance_decision",
            "lens_patch",
        }:
            coverage["governance"] += 1
        if link.link_role == "supports":
            coverage["support"] += 1
        if link.link_role == "derived_from":
            coverage["derived"] += 1
    return EvidenceCoverageSummary(**coverage)


def _evidence_priority(link: MemoryEvidenceSummary) -> int:
    if link.link_role == "supports" and link.evidence_type == "artifact_result":
        return 0
    if link.link_role == "supports" and link.evidence_type == "stage_result":
        return 1
    if link.link_role == "supports" and link.evidence_type == "task_execution":
        return 2
    if link.link_role == "supports" and link.evidence_type == "execution_trace":
        return 3
    if link.link_role == "supports" and link.evidence_type == "meeting_decision":
        return 4
    if link.link_role == "supports" and link.evidence_type == "governance_decision":
        return 5
    if link.link_role == "supports" and link.evidence_type == "lens_patch":
        return 6
    if link.link_role == "supports" and link.evidence_type == "intent_log":
        return 7
    if link.link_role == "supports" and link.evidence_type == "reasoning_trace":
        return 8
    if link.evidence_type == "session_digest":
        return 9
    if link.evidence_type == "lens_receipt":
        return 10
    if link.evidence_type == "writeback_receipt":
        return 11
    return 12


def _select_primary_evidence(
    evidence_links: List[MemoryEvidenceSummary],
) -> Optional[MemoryEvidenceSummary]:
    if not evidence_links:
        return None
    return sorted(
        evidence_links,
        key=lambda link: (_evidence_priority(link), link.created_at),
        reverse=False,
    )[0]


def _build_transition_cues(
    memory_item: WorkspaceMemoryItemSummary,
    evidence_links: List[MemoryEvidenceSummary],
    coverage: EvidenceCoverageSummary,
) -> List[TransitionCueSummary]:
    cues: List[TransitionCueSummary] = []
    has_operational_evidence = coverage.execution > 0 or coverage.governance > 0
    has_deliberation_evidence = coverage.deliberation > 0
    has_artifact_or_task_evidence = any(
        link.evidence_type
        in {"task_execution", "execution_trace", "stage_result", "artifact_result"}
        for link in evidence_links
    )
    has_decision_evidence = any(
        link.evidence_type
        in {"meeting_decision", "intent_log", "governance_decision", "lens_patch"}
        for link in evidence_links
    )

    if memory_item.lifecycle_status == "candidate":
        if has_deliberation_evidence and has_operational_evidence:
            cues.append(
                TransitionCueSummary(
                    id="verify-ready",
                    tone="positive",
                    title="Verification signal is available",
                    body=(
                        "This candidate is backed by both deliberation evidence and "
                        "downstream execution or governance receipts. Verify it when "
                        "the claim reflects the current working standard."
                    ),
                )
            )
        else:
            cues.append(
                TransitionCueSummary(
                    id="verify-hold",
                    tone="caution",
                    title="Hold as candidate until coverage improves",
                    body=(
                        "Keep this item in candidate state while additional "
                        "decisions, executions, or artifacts accumulate around the claim."
                    ),
                )
            )

    if memory_item.lifecycle_status == "active":
        cues.append(
            TransitionCueSummary(
                id="stale-usage",
                tone="neutral",
                title="Use stale for context drift",
                body=(
                    "Mark the item stale when the claim no longer matches the active "
                    "workspace context and no replacement claim is ready yet."
                ),
            )
        )
        if has_artifact_or_task_evidence or has_decision_evidence:
            cues.append(
                TransitionCueSummary(
                    id="supersede-usage",
                    tone="positive",
                    title="Supersede when a successor claim is ready",
                    body=(
                        "This item already has decision or execution evidence attached. "
                        "Create a successor when the current claim should remain visible "
                        "as history while a new operating claim takes over."
                    ),
                )
            )

    if coverage.support == 0 and coverage.derived > 0:
        cues.append(
            TransitionCueSummary(
                id="support-gap",
                tone="caution",
                title="Support evidence is still thin",
                body=(
                    "The current chain is dominated by derived receipts. Add or wait "
                    "for direct supporting evidence before promoting a weak claim."
                ),
            )
        )

    if not cues:
        cues.append(
            TransitionCueSummary(
                id="baseline",
                tone="neutral",
                title="Review the evidence chain before transitioning",
                body=(
                    "Use the evidence mix, recency, and projection history to decide "
                    "whether this claim should stay active, become stale, or move to a successor."
                ),
            )
        )
    return cues


def _build_successor_draft_suggestion(
    memory_item: WorkspaceMemoryItemSummary,
    evidence_links: List[MemoryEvidenceSummary],
    coverage: EvidenceCoverageSummary,
) -> Optional[SuccessorDraftSuggestionSummary]:
    if memory_item.lifecycle_status != "active":
        return None

    primary_evidence = _select_primary_evidence(evidence_links)
    primary_excerpt = (primary_evidence.excerpt or "").strip() if primary_evidence else ""
    primary_label = (
        _evidence_display_name(primary_evidence.evidence_type)
        if primary_evidence
        else "Evidence Chain"
    )
    claim = (
        primary_excerpt
        or memory_item.claim
        or memory_item.summary
        or "Refine the working claim based on the latest validated evidence."
    )
    title = (
        memory_item.title
        if "revision" in memory_item.title.lower()
        else f"{memory_item.title} Revision"
    )
    summary_parts = [
        f"Successor drafted from {primary_label.lower()}.",
        (
            f"Coverage: {coverage.deliberation} deliberation, "
            f"{coverage.execution} execution, {coverage.governance} governance."
        ),
    ]
    if primary_evidence and primary_evidence.evidence_id:
        summary_parts.append(f"Anchor evidence: {primary_evidence.evidence_id}.")

    return SuccessorDraftSuggestionSummary(
        title=title,
        claim=claim,
        summary=" ".join(summary_parts),
        primary_evidence_id=getattr(primary_evidence, "evidence_id", None),
        primary_evidence_type=getattr(primary_evidence, "evidence_type", None),
    )


def _build_transition_reason_suggestions(
    memory_item: WorkspaceMemoryItemSummary,
    primary_evidence: Optional[MemoryEvidenceSummary],
    coverage: EvidenceCoverageSummary,
) -> TransitionReasonSuggestions:
    anchor = (
        f"{_evidence_display_name(primary_evidence.evidence_type)} "
        f"{primary_evidence.evidence_id}"
        if primary_evidence
        else "the current evidence chain"
    )
    return TransitionReasonSuggestions(
        verify=(
            f"Verified after reviewing {anchor} with "
            f"{coverage.deliberation} deliberation signals and "
            f"{coverage.execution + coverage.governance} downstream execution or governance signals."
        ),
        stale=(
            f"Marked stale because the active workspace context moved beyond this claim "
            f"and no replacement was finalized from {anchor}."
        ),
        supersede=(
            f"Superseded after {anchor} established a newer operating claim "
            f"for {memory_item.title}."
        ),
    )


def _classify_workflow_evidence_diagnostics(
    diagnostics: Dict[str, Any],
) -> Literal["balanced", "tight", "sparse", "underused", "narrow", "empty"]:
    selected = diagnostics.get("selected_line_count")
    candidates = diagnostics.get("total_candidate_count")
    dropped = diagnostics.get("total_dropped_count")
    rendered_sections = diagnostics.get("rendered_section_count")
    utilization = diagnostics.get("budget_utilization_ratio")

    selected_count = selected if isinstance(selected, int) else 0
    candidate_count = candidates if isinstance(candidates, int) else 0
    dropped_count = dropped if isinstance(dropped, int) else 0
    rendered_section_count = (
        rendered_sections if isinstance(rendered_sections, int) else 0
    )
    utilization_ratio = (
        float(utilization) if isinstance(utilization, (int, float)) else 0.0
    )

    if selected_count == 0 and candidate_count == 0:
        return "empty"
    if dropped_count > 0 and utilization_ratio >= 0.85:
        return "tight"
    if selected_count > 0 and utilization_ratio < 0.4:
        return "underused"
    if selected_count == 0 and candidate_count > 0:
        return "sparse"
    if rendered_section_count <= 1:
        return "narrow"
    return "balanced"


def _serialize_workflow_evidence_health_session(session) -> Optional[WorkflowEvidenceHealthSessionSummary]:
    metadata = dict(getattr(session, "metadata", {}) or {})
    diagnostics = metadata.get("workflow_evidence_diagnostics")
    if not isinstance(diagnostics, dict):
        return None

    def _int_value(key: str) -> int:
        value = diagnostics.get(key)
        return value if isinstance(value, int) else 0

    def _float_value(key: str) -> float:
        value = diagnostics.get(key)
        return float(value) if isinstance(value, (int, float)) else 0.0

    return WorkflowEvidenceHealthSessionSummary(
        session_id=session.id,
        project_id=getattr(session, "project_id", None),
        thread_id=getattr(session, "thread_id", None),
        meeting_type=getattr(session, "meeting_type", "general") or "general",
        started_at=session.started_at,
        ended_at=getattr(session, "ended_at", None),
        profile=str(diagnostics.get("profile") or "general"),
        scope=str(diagnostics.get("scope") or "none"),
        total_candidate_count=_int_value("total_candidate_count"),
        selected_line_count=_int_value("selected_line_count"),
        total_line_budget=_int_value("total_line_budget"),
        total_dropped_count=_int_value("total_dropped_count"),
        rendered_section_count=_int_value("rendered_section_count"),
        budget_utilization_ratio=_float_value("budget_utilization_ratio"),
        classification=_classify_workflow_evidence_diagnostics(diagnostics),
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
