"""Strict pack-neutral request schemas for enriched document projections."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectionFacetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9_.-]+$", max_length=128)
    value_type: Literal["string", "number", "boolean", "enum", "ref"]
    value: str | float | int | bool
    ordinal: int = Field(default=0, ge=0, le=1000)


class ProjectionRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_kind: str = Field(pattern=r"^[a-z0-9_.-]+$", max_length=128)
    record_key: str = Field(min_length=1, max_length=256)
    search_text: str = Field(min_length=1, max_length=32768)
    citation: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    facets: tuple[ProjectionFacetInput, ...] = Field(
        default=(),
        max_length=64,
    )


class GraphEntityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_key: str = Field(min_length=1, max_length=512)
    entity_type: str = Field(min_length=1, max_length=128)
    resolver_revision: str = Field(
        default="owner-declared.v1",
        min_length=1,
        max_length=128,
    )


class GraphMentionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_key: str = Field(min_length=1, max_length=512)
    evidence_unit_key: Optional[str] = Field(
        default="chunk-0",
        max_length=256,
    )
    record_key: Optional[str] = Field(default=None, max_length=256)
    surface_text: str = Field(min_length=1, max_length=4096)
    mention_type: str = Field(default="owner_declared", max_length=128)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    citation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_anchor(self) -> "GraphMentionInput":
        if not self.evidence_unit_key and not self.record_key:
            raise ValueError("owner_declared_graph_mention_anchor_required")
        return self


class GraphRelationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relation_key: str = Field(min_length=1, max_length=512)
    source_entity_key: str = Field(min_length=1, max_length=512)
    target_entity_key: str = Field(min_length=1, max_length=512)
    relation_kind: str = Field(min_length=1, max_length=128)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    supporting_evidence_unit_keys: tuple[str, ...] = Field(
        default=("chunk-0",),
        min_length=1,
        max_length=64,
    )
    supporting_citations: tuple[dict[str, Any], ...] = Field(
        default=(),
        max_length=64,
    )
    owner_relation_revision: str = Field(
        default="owner-declared.v1",
        min_length=1,
        max_length=128,
    )


class GraphCommunityInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    community_key: str = Field(min_length=1, max_length=256)
    level: int = Field(default=0, ge=0, le=32)
    parent_community_key: Optional[str] = Field(
        default=None,
        max_length=256,
    )
    entity_keys: tuple[str, ...] = Field(min_length=1, max_length=512)
    relation_keys: tuple[str, ...] = Field(default=(), max_length=1024)


class GraphCommunityReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    community_key: str = Field(min_length=1, max_length=256)
    summary: str = Field(min_length=1, max_length=32768)
    findings: tuple[dict[str, Any], ...] = Field(default=(), max_length=128)
    rank: float = Field(default=1.0, ge=0.0)
    supporting_citations: tuple[dict[str, Any], ...] = Field(
        default=(),
        max_length=128,
    )


class OwnerDeclaredGraphInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    algorithm_revision: str = Field(
        default="owner-declared.communities.v1",
        min_length=1,
        max_length=128,
    )
    resolver_revision: str = Field(
        default="owner-declared.entities.v1",
        min_length=1,
        max_length=128,
    )
    entities: tuple[GraphEntityInput, ...] = Field(
        min_length=1,
        max_length=1000,
    )
    mentions: tuple[GraphMentionInput, ...] = Field(
        min_length=1,
        max_length=2000,
    )
    relations: tuple[GraphRelationInput, ...] = Field(
        default=(),
        max_length=2000,
    )
    communities: tuple[GraphCommunityInput, ...] = Field(
        default=(),
        max_length=256,
    )
    reports: tuple[GraphCommunityReportInput, ...] = Field(
        default=(),
        max_length=256,
    )


__all__ = [
    "OwnerDeclaredGraphInput",
    "ProjectionRecordInput",
]
