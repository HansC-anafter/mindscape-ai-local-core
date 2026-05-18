from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


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
