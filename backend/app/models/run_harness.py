"""Contracts for selecting, executing, and observing local run harnesses."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunHarnessKind(str, Enum):
    COMPOSITION_GRAPH = "composition_graph"
    DETERMINISTIC_TOOL = "deterministic_tool"
    DURABLE_WORKFLOW = "durable_workflow"
    MEETING_ESCALATION = "meeting_escalation"


class RunIntentRiskClass(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class RunIntentSource(str, Enum):
    CHAT = "chat"
    MEETING = "meeting"
    COMPOSITION_GRAPH = "composition_graph"
    TOOL_RAIL = "tool_rail"
    WORKFLOW = "workflow"
    API = "api"


class RunHarnessStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    ESCALATED = "escalated"


class RunHarnessWaitKind(str, Enum):
    USER_INPUT = "user_input"
    HUMAN_APPROVAL = "human_approval"
    RESOURCE = "resource"
    CAPABILITY = "capability"
    MODEL = "model"
    EXTERNAL_AGENT = "external_agent"


class EscalationTrigger(str, Enum):
    POLICY_RISK = "policy_risk"
    LOW_CONFIDENCE = "low_confidence"
    CROSS_PACK_CONFLICT = "cross_pack_conflict"
    MISSING_TOOL = "missing_tool"
    WORKFLOW_STUCK = "workflow_stuck"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    RESOURCE_ADMISSION_DENIED = "resource_admission_denied"
    MODEL_UNAVAILABLE_FOR_REQUIRED_REASONING = (
        "model_unavailable_for_required_reasoning"
    )


class EscalationDisposition(str, Enum):
    QUEUE_MEETING = "queue_meeting"
    REQUEST_STRUCTURED_INPUT = "request_structured_input"
    REQUEST_APPROVAL = "request_approval"
    DETERMINISTIC_REPAIR = "deterministic_repair"
    RETRY_WITH_LOWER_CAPABILITY = "retry_with_lower_capability"
    FAIL_CLOSED = "fail_closed"


class SideEffectClass(str, Enum):
    NONE = "none"
    READONLY = "readonly"
    SOFT_WRITE = "soft_write"
    EXTERNAL_WRITE = "external_write"
    DESTRUCTIVE = "destructive"


class ToolAdmissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    WAIT = "wait"
    ESCALATE = "escalate"


class DurabilityMode(str, Enum):
    NONE = "none"
    CHECKPOINTED = "checkpointed"
    RESUMABLE = "resumable"
    REPLAYABLE = "replayable"


class RunHarnessCapabilitySnapshotRef(StrictModel):
    ref: str = Field(min_length=1)
    version: Optional[str] = None
    capability_codes: List[str] = Field(default_factory=list)
    digest: Optional[str] = None


class RunHarnessPermissionProfileRef(StrictModel):
    ref: str = Field(min_length=1)
    version: Optional[str] = None
    digest: Optional[str] = None


class RunHarnessPolicyBundleRef(StrictModel):
    ref: str = Field(min_length=1)
    version: Optional[str] = None
    digest: Optional[str] = None


class RunHarnessWorkspaceBoundary(StrictModel):
    workspace_id: str = Field(min_length=1)
    writable_roots: List[str] = Field(default_factory=list)
    readonly_roots: List[str] = Field(default_factory=list)
    network_allowlist: List[str] = Field(default_factory=list)
    allow_host_access: bool = False


class RunHarnessResourceEstimate(StrictModel):
    expected_latency_ms: Optional[int] = Field(default=None, ge=0)
    expected_cost_units: Optional[float] = Field(default=None, ge=0)
    expected_context_tokens: Optional[int] = Field(default=None, ge=0)
    worker_slots: int = Field(default=0, ge=0)


class RunIntentEnvelope(StrictModel):
    decision_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    origin_surface: RunIntentSource
    intent_text: str = Field(min_length=1)
    context_object_refs: List[str] = Field(default_factory=list)
    capability_snapshot_ref: RunHarnessCapabilitySnapshotRef
    permission_profile_ref: RunHarnessPermissionProfileRef
    policy_bundle_ref: RunHarnessPolicyBundleRef
    workspace_roots: List[str] = Field(default_factory=list)
    workspace_readonly_roots: List[str] = Field(default_factory=list)
    data_classification: str = "internal"
    requested_side_effects: List[SideEffectClass] = Field(default_factory=list)
    approval_mode: str = "policy"
    latency_budget_ms: Optional[int] = Field(default=None, ge=0)
    cost_budget: Optional[float] = Field(default=None, ge=0)
    context_budget: Optional[int] = Field(default=None, ge=0)
    delegation_depth_limit: int = Field(default=1, ge=0)
    idempotency_key: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    preferred_harness: Optional[RunHarnessKind] = None
    risk_class: RunIntentRiskClass = RunIntentRiskClass.LOW
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RunHarnessSelection(StrictModel):
    harness_kind: RunHarnessKind
    selection_reason_codes: List[str] = Field(min_length=1)
    requires_approval: bool = False
    requires_durability: bool = False
    requires_sandbox: bool = False
    selected_policy_version: str = Field(min_length=1)
    fallback_strategy: EscalationDisposition = EscalationDisposition.FAIL_CLOSED
    capability_misses: List[str] = Field(default_factory=list)
    resource_estimate: RunHarnessResourceEstimate = Field(
        default_factory=RunHarnessResourceEstimate
    )
    selected_at: datetime = Field(default_factory=_utc_now)


class RunHarnessTraceRef(StrictModel):
    trace_id: str = Field(min_length=1)
    node_ids: List[str] = Field(default_factory=list)


class RunHarnessArtifactLineageRef(StrictModel):
    artifact_ref: str = Field(min_length=1)
    parent_refs: List[str] = Field(default_factory=list)
    relation: str = "produced"


class RunHarnessPolicyEval(StrictModel):
    policy_ref: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    reason_codes: List[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=_utc_now)


class RunHarnessStepEvent(StrictModel):
    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    status: RunHarnessStatus
    payload_ref: Optional[str] = None
    occurred_at: datetime = Field(default_factory=_utc_now)


class RunHarnessAttempt(StrictModel):
    attempt_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    status: RunHarnessStatus = RunHarnessStatus.PENDING
    step_events: List[RunHarnessStepEvent] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RunHarnessEpisode(StrictModel):
    episode_id: str = Field(min_length=1)
    intent_envelope_ref: str = Field(min_length=1)
    selection_ref: str = Field(min_length=1)
    status: RunHarnessStatus = RunHarnessStatus.PENDING
    attempts: List[RunHarnessAttempt] = Field(default_factory=list)
    policy_evals: List[RunHarnessPolicyEval] = Field(default_factory=list)
    trace_refs: List[RunHarnessTraceRef] = Field(default_factory=list)
    artifact_lineage: List[RunHarnessArtifactLineageRef] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class RunHarnessWaitState(StrictModel):
    kind: RunHarnessWaitKind
    reason: str = Field(min_length=1)
    resume_token: Optional[str] = None
    retry_after_ms: Optional[int] = Field(default=None, ge=0)
    expires_at: Optional[datetime] = None


class RunHarnessFailure(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class RunHarnessScore(StrictModel):
    score: float = Field(ge=0, le=1)
    rubric: str = Field(min_length=1)
    reason_codes: List[str] = Field(default_factory=list)


class RunHarnessNextAction(StrictModel):
    disposition: EscalationDisposition
    reason: str = Field(min_length=1)
    payload_ref: Optional[str] = None


class RunHarnessResult(StrictModel):
    run_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    harness_kind: RunHarnessKind
    status: RunHarnessStatus
    output_artifact_refs: List[str] = Field(default_factory=list)
    failure: Optional[RunHarnessFailure] = None
    score: Optional[RunHarnessScore] = None
    next_action: Optional[RunHarnessNextAction] = None
    wait_state: Optional[RunHarnessWaitState] = None
    trace_refs: List[RunHarnessTraceRef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_wait_state(self) -> "RunHarnessResult":
        if self.status == RunHarnessStatus.WAITING and self.wait_state is None:
            raise ValueError("waiting results require wait_state")
        if self.status != RunHarnessStatus.WAITING and self.wait_state is not None:
            raise ValueError("wait_state is only valid for waiting results")
        return self


class RunHarnessObservation(StrictModel):
    workspace_id: str = Field(min_length=1)
    episode: RunHarnessEpisode
    result: RunHarnessResult
    source: str = "composition_graph_run"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EscalationDecision(StrictModel):
    trigger: EscalationTrigger
    disposition: EscalationDisposition
    reason_codes: List[str] = Field(min_length=1)
    wait_state: Optional[RunHarnessWaitState] = None


class RollbackPlanRef(StrictModel):
    ref: str = Field(min_length=1)
    required: bool = False


class SensitiveArtifactPolicy(StrictModel):
    allow_persistence: bool = False
    redact_trace_payloads: bool = True
    allowed_classifications: List[str] = Field(default_factory=lambda: ["public"])


class ContextQuarantinePolicy(StrictModel):
    enabled: bool = True
    allow_untrusted_context: bool = False
    quarantine_ref: Optional[str] = None


class CredentialExposurePolicy(StrictModel):
    allow_raw_credentials: bool = False
    allowed_secret_refs: List[str] = Field(default_factory=list)


class SandboxProfile(StrictModel):
    profile_ref: str = Field(min_length=1)
    workspace_boundary: RunHarnessWorkspaceBoundary
    context_quarantine: ContextQuarantinePolicy = Field(
        default_factory=ContextQuarantinePolicy
    )
    credential_exposure: CredentialExposurePolicy = Field(
        default_factory=CredentialExposurePolicy
    )
    sensitive_artifacts: SensitiveArtifactPolicy = Field(
        default_factory=SensitiveArtifactPolicy
    )


class ToolAdmissionPolicy(StrictModel):
    policy_ref: str = Field(min_length=1)
    allowed_tool_refs: List[str] = Field(default_factory=list)
    denied_tool_refs: List[str] = Field(default_factory=list)
    allowed_side_effects: List[SideEffectClass] = Field(
        default_factory=lambda: [SideEffectClass.NONE, SideEffectClass.READONLY]
    )
    require_approval_for: List[SideEffectClass] = Field(
        default_factory=lambda: [
            SideEffectClass.SOFT_WRITE,
            SideEffectClass.EXTERNAL_WRITE,
            SideEffectClass.DESTRUCTIVE,
        ]
    )
    rollback_plan_ref: Optional[RollbackPlanRef] = None


class ToolAdmissionResult(StrictModel):
    decision: ToolAdmissionDecision
    reason_codes: List[str] = Field(min_length=1)
    wait_state: Optional[RunHarnessWaitState] = None


class DurabilityRequirement(StrictModel):
    mode: DurabilityMode = DurabilityMode.NONE
    checkpoint_ref: Optional[str] = None
    resume_token: Optional[str] = None
    lease_timeout_ms: Optional[int] = Field(default=None, gt=0)
    stuck_after_ms: Optional[int] = Field(default=None, gt=0)
    idempotency_scope: Optional[str] = None
    replay_policy: Optional[str] = None
    rollback_policy_ref: Optional[str] = None


class RunHarnessSpec(StrictModel):
    spec_id: str = Field(min_length=1)
    spec_version: str = "run_harness_spec.v1"
    harness_kind: RunHarnessKind = RunHarnessKind.COMPOSITION_GRAPH
    graph_ref: str = Field(min_length=1)
    intent_envelope_ref: str = Field(min_length=1)
    selection_ref: str = Field(min_length=1)
    input_artifact_refs: List[str] = Field(default_factory=list)
    requested_output_refs: List[str] = Field(default_factory=list)
    required_tool_contract_refs: List[str] = Field(default_factory=list)
    workspace_boundary_ref: str = Field(min_length=1)
    policy_bundle_ref: str = Field(min_length=1)
    sandbox_profile_ref: str = Field(min_length=1)
    durability_requirement: DurabilityRequirement = Field(
        default_factory=DurabilityRequirement
    )
    trace_policy_ref: str = Field(min_length=1)
    expected_result_contract: str = "RunHarnessResult"
