"""Typed contracts for one post-STT Workspace voice semantic turn."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.models.meeting_command import MeetingCommandAcceptResponse
from backend.app.models.object_runtime import ObjectRef


VOICE_INTERACTION_RESULT_SCHEMA_VERSION = "aol.voice_interaction_result.v1"
ANSWER_LANGUAGE_PATTERN = r"^(?:[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*|x(?:-[A-Za-z0-9]{1,8})+)$"

WorkspaceVoiceDecisionOutcome = Literal[
    "grounded_material",
    "grounded_answer",
    "clarification",
    "not_applicable",
]
WorkspaceVoiceExplicitReferenceKind = Literal[
    "selected",
    "hash",
    "hashtag",
    "comment",
]
WorkspaceVoiceReferenceResolutionStatus = Literal[
    "not_requested",
    "resolved",
    "unresolved",
    "ambiguous",
    "count_exceeded",
]
WorkspaceVoiceSemanticTurnStatus = Literal[
    "command_submitted",
    "clarification_required",
    "reference_unresolved",
    "reference_ambiguous",
    "reference_count_exceeded",
    "interaction_unavailable",
    "stale_target",
]


class WorkspaceVoiceClientAction(BaseModel):
    """Canonical pack-declared browser action carried through Meeting."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aol.client_action.v1"] = "aol.client_action.v1"
    pack_code: str = Field(min_length=1, max_length=128)
    intent_code: str = Field(min_length=1, max_length=128)
    action_code: str = Field(min_length=1, max_length=256)
    requires_confirmation: bool = False
    payload: Dict[str, Any] = Field(default_factory=dict)


class WorkspaceVoiceReferenceCandidate(BaseModel):
    """Bounded safe candidate returned for user clarification."""

    model_config = ConfigDict(extra="forbid")

    object_ref: ObjectRef
    display_label: str = Field(min_length=1, max_length=160)
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class WorkspaceVoiceEvidence(BaseModel):
    """Bounded pack evidence supporting one grounded answer."""

    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(min_length=1, max_length=512)
    title: Optional[str] = Field(default=None, max_length=160)
    excerpt: str = Field(min_length=1, max_length=320)
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class WorkspaceVoicePackCandidate(BaseModel):
    """Pack result candidate before generic-host safe projection."""

    model_config = ConfigDict(extra="forbid")

    object_ref: ObjectRef
    display_label: str = Field(min_length=1, max_length=160)
    score: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkspaceVoicePackEvidence(BaseModel):
    """Pack result evidence before generic-host safe projection."""

    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(min_length=1, max_length=512)
    title: Optional[str] = Field(default=None, max_length=160)
    excerpt: str = Field(min_length=1, max_length=320)
    score: float = Field(ge=0.0, le=1.0)
    asana_id: Optional[str] = Field(default=None, max_length=128)


class WorkspaceVoicePackInteractionResult(BaseModel):
    """Strict result accepted from one active installed pack tool."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aol.voice_interaction_result.v1"]
    outcome: WorkspaceVoiceDecisionOutcome
    decision_code: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0.0, le=1.0)
    candidates: List[WorkspaceVoicePackCandidate] = Field(
        default_factory=list,
        max_length=3,
    )
    evidence: List[WorkspaceVoicePackEvidence] = Field(
        default_factory=list,
        max_length=3,
    )
    answer_text: Optional[str] = Field(default=None, max_length=600)
    answer_language: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=35,
        pattern=ANSWER_LANGUAGE_PATTERN,
    )
    clarification_reason: Optional[str] = Field(default=None, max_length=128)
    client_action: Optional[WorkspaceVoiceClientAction] = None

    @model_validator(mode="after")
    def _validate_outcome_shape(self) -> "WorkspaceVoicePackInteractionResult":
        if self.outcome == "grounded_material" and len(self.candidates) != 1:
            raise ValueError("grounded_material_requires_one_candidate")
        if self.outcome == "grounded_answer" and (
            not self.answer_text or not self.evidence
        ):
            raise ValueError("grounded_answer_requires_text_and_evidence")
        if self.outcome == "clarification" and not self.clarification_reason:
            raise ValueError("clarification_requires_reason")
        return self


class WorkspaceVoiceReferenceResolution(BaseModel):
    """Result from the generic exact-only AOL reference resolver."""

    model_config = ConfigDict(extra="forbid")

    status: WorkspaceVoiceReferenceResolutionStatus = "not_requested"
    explicit_kind: Optional[WorkspaceVoiceExplicitReferenceKind] = None
    token: Optional[str] = Field(default=None, max_length=512)
    resolved_references: List[ObjectRef] = Field(default_factory=list, max_length=1)
    candidates: List[WorkspaceVoiceReferenceCandidate] = Field(
        default_factory=list,
        max_length=3,
    )
    reason: Optional[str] = Field(default=None, max_length=128)
    catalog_query_count: int = Field(default=0, ge=0, le=1)


class WorkspaceVoiceSemanticTurnResult(BaseModel):
    """One deterministic semantic decision and optional canonical Meeting write."""

    model_config = ConfigDict(extra="forbid")

    status: WorkspaceVoiceSemanticTurnStatus
    outcome: WorkspaceVoiceDecisionOutcome
    decision_code: str = Field(
        min_length=1,
        max_length=128,
        description="Semantic only; active_pack_voice_timeout is not a host cancellation receipt.",
    )
    transcript: str = Field(min_length=1, max_length=4000)
    command_response: Optional[MeetingCommandAcceptResponse] = None
    answer_text: Optional[str] = Field(default=None, max_length=600)
    answer_language: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=35,
        pattern=ANSWER_LANGUAGE_PATTERN,
    )
    resolved_references: List[ObjectRef] = Field(default_factory=list, max_length=2)
    candidates: List[WorkspaceVoiceReferenceCandidate] = Field(
        default_factory=list,
        max_length=3,
    )
    evidence: List[WorkspaceVoiceEvidence] = Field(
        default_factory=list,
        max_length=3,
    )
    client_action: Optional[WorkspaceVoiceClientAction] = None

    @model_validator(mode="after")
    def _validate_write_shape(self) -> "WorkspaceVoiceSemanticTurnResult":
        if self.status == "command_submitted" and self.command_response is None:
            raise ValueError("command_submitted_requires_command_response")
        if self.status != "command_submitted" and self.command_response is not None:
            raise ValueError("non_submitted_result_must_not_have_command_response")
        return self
