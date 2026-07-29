"""Typed contracts for one bounded Meeting grounded-knowledge answer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RetrievalMode = Literal[
    "hybrid",
    "local_graph",
    "multi_hop",
    "global_graph",
]


class GroundedKnowledgeAnswerOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: Literal["search"] = "search"
    query: str = Field(min_length=1, max_length=8000)
    retrieval_mode: RetrievalMode
    scope: Literal["workspace", "active_group"] = "workspace"
    limit: int = Field(default=10, ge=1, le=20)


class GroundedKnowledgeAnswerPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1, max_length=8000)
    operations: tuple[GroundedKnowledgeAnswerOperation, ...] = Field(
        min_length=1,
        max_length=6,
    )
    frontier_preview: bool = False
    guided_learning_context: dict[str, Any] | None = None


class GroundedAnswerClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=4000)
    citation_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


class GroundedKnowledgeAnswerResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[
        "answered",
        "insufficient_evidence",
        "citation_verification_failed",
    ]
    answer_markdown: str = Field(max_length=24000)
    claims: tuple[GroundedAnswerClaim, ...] = Field(default=(), max_length=32)
    citations: tuple[dict[str, Any], ...] = Field(default=(), max_length=64)
    evidence_refs: tuple[dict[str, Any], ...] = Field(default=(), max_length=64)
    uncertainties: tuple[str, ...] = Field(default=(), max_length=16)
    safety_notes: tuple[str, ...] = Field(default=(), max_length=16)
    coverage: dict[str, Any] = Field(default_factory=dict)
    receipt: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "GroundedAnswerClaim",
    "GroundedKnowledgeAnswerOperation",
    "GroundedKnowledgeAnswerPlan",
    "GroundedKnowledgeAnswerResult",
    "RetrievalMode",
]
