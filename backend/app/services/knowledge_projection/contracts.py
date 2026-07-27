"""Typed contracts for the source-ledger, projection, and group-brain seams."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeSourceIntake(BaseModel):
    source_instance_id: str = Field(min_length=1, max_length=128)
    owner_type: str = Field(min_length=1, max_length=64)
    owner_id: str = Field(min_length=1, max_length=128)
    binding_id: Optional[str] = Field(default=None, max_length=128)
    source_revision: str = Field(min_length=1, max_length=256)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_type: str = Field(min_length=1, max_length=64)
    evidence_id: str = Field(min_length=1, max_length=256)
    cursor: Dict[str, Any] = Field(default_factory=dict)
    checkpoint: Dict[str, Any] = Field(default_factory=dict)
    last_result: Dict[str, Any] = Field(default_factory=dict)
    visibility: Literal["private", "workspace", "group"] = "private"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeSourceIntakeReceipt(BaseModel):
    intake_id: str
    source_instance_id: str
    source_revision: str
    content_hash: str
    created: bool


class KnowledgeProjectionEntry(BaseModel):
    memory_version_id: str
    stable_subject_key: str
    title: str = ""
    claim: str
    summary: str = ""
    lifecycle_status: str
    verification_status: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: List[str] = Field(default_factory=list)


class KnowledgeProjectionRequest(BaseModel):
    projection_type: str = Field(min_length=1, max_length=64)
    scope_type: Literal["workspace", "group", "agent", "human_review"]
    scope_id: str = Field(min_length=1, max_length=128)
    topology_snapshot_id: Optional[str] = Field(default=None, max_length=64)
    policy_revision: str = Field(min_length=1, max_length=64)
    generator_revision: str = Field(min_length=1, max_length=64)
    logical_generated_at: datetime
    artifact_ref: str = Field(min_length=1)
    entries: List[KnowledgeProjectionEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeProjectionResult(BaseModel):
    projection_id: str
    input_revision_hash: str
    content_hash: str
    markdown: str
    artifact_ref: str
    created: bool


class AgentClaim(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    agent_role: str = Field(min_length=1, max_length=128)
    stable_subject_key: str = Field(min_length=1, max_length=256)
    title: str = ""
    claim: str = Field(min_length=1, max_length=12000)
    summary: str = Field(default="", max_length=2000)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_refs: List[str] = Field(default_factory=list, max_length=100)

    @field_validator("evidence_refs")
    @classmethod
    def require_bounded_evidence_refs(cls, values: List[str]) -> List[str]:
        if any(not value or len(value) > 256 for value in values):
            raise ValueError("evidence refs must be non-empty and at most 256 chars")
        return list(dict.fromkeys(values))


class GroupSynthesisHandoff(BaseModel):
    run_id: str = Field(min_length=1, max_length=128)
    group_id: str = Field(min_length=1, max_length=64)
    topology_snapshot_id: str = Field(min_length=1, max_length=64)
    policy_revision: str = Field(min_length=1, max_length=64)
    claims: List[AgentClaim] = Field(min_length=1, max_length=500)


class GroupKnowledgePacketEntry(BaseModel):
    memory_item_id: str
    stable_subject_key: str
    title: str
    claim: str
    summary: str
    lifecycle_status: str
    verification_status: str
    confidence: float


class GroupKnowledgePacket(BaseModel):
    group_id: str
    topology_snapshot_id: str
    topology_revision: int
    requesting_workspace_id: str
    agent_role: str
    bound_agent_role: Optional[str] = None
    preview: bool = False
    agent_policy_revision: Optional[str] = None
    memory_revision_hash: str
    entries: List[GroupKnowledgePacketEntry]


class GroupSynthesisReceipt(BaseModel):
    receipt_id: str
    run_id: str
    group_id: str
    topology_snapshot_id: str
    input_hash: str
    status: str
    candidate_memory_ids: List[str]
    conflict_sets: List[Dict[str, Any]]
    review_projection_id: Optional[str] = None
    created: bool


class GroupSynthesisReviewCommand(BaseModel):
    synthesis_receipt_id: str = Field(min_length=1, max_length=64)
    decision: Literal["approve", "request_changes", "reject"]
    actor_user_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=4000)


class GroupSynthesisReviewReceipt(BaseModel):
    id: str
    synthesis_receipt_id: str
    decision: str
    actor_user_id: str
    reason: str
    decision_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    created: bool = True
