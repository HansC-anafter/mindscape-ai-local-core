"""Portable retrievable source, projection, citation, and receipt contracts."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .evidence_units import EvidenceUnit


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        protected_namespaces=(),
    )


class RetrievableSourceRef(_StrictModel):
    owner_capability_code: str = Field(pattern=r"^[a-z0-9_]+$")
    descriptor_id: str = Field(pattern=r"^[a-z0-9_]+$")
    source_kind: Literal["object", "artifact", "memory", "document"]
    source_instance_id: str = Field(min_length=1, max_length=255)
    source_revision: str = Field(min_length=1, max_length=255)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_ref: str = Field(min_length=1, max_length=1024)
    workspace_id: str = Field(min_length=1, max_length=255)
    group_id: Optional[str] = Field(default=None, max_length=255)


class ProjectionCitation(_StrictModel):
    knowledge_resource_id: Optional[str] = Field(default=None, max_length=255)
    source_instance_id: str = Field(min_length=1, max_length=255)
    source_revision: str = Field(min_length=1, max_length=255)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_ref: str = Field(min_length=1, max_length=1024)
    anchor_kind: Literal[
        "text_span",
        "image_region",
        "video_time_range",
        "audio_time_range",
        "object",
        "record",
    ]
    anchor_value: dict[str, Any]
    unit_kind: Literal["text_span", "image_region", "video_segment", "audio_segment"]
    owner_surface_ref: Optional[str] = Field(default=None, max_length=1024)
    preview_ref: Optional[str] = Field(default=None, max_length=1024)
    projector_revision: str = Field(min_length=1, max_length=255)
    projection_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class PortableFacet(_StrictModel):
    name: str = Field(pattern=r"^[a-z0-9_]+$")
    value_type: Literal["string", "number", "boolean", "timestamp", "enum", "ref"]
    value: str | float | int | bool


class PortableRecord(_StrictModel):
    record_id: str = Field(min_length=1, max_length=255)
    record_kind: str = Field(pattern=r"^[a-z0-9_]+$")
    values: dict[str, Any] = Field(max_length=128)
    facets: tuple[PortableFacet, ...] = Field(default=(), max_length=128)
    citation: ProjectionCitation


class EvidenceRelation(_StrictModel):
    relation_id: str = Field(min_length=1, max_length=255)
    source_evidence_unit_id: str = Field(min_length=1, max_length=255)
    target_evidence_unit_id: str = Field(min_length=1, max_length=255)
    relation_kind: str = Field(pattern=r"^[a-z0-9_]+$")
    origin: Literal["owner_declared", "extracted"]
    owner_relation_revision: Optional[str] = Field(default=None, max_length=255)
    extractor_revision: Optional[str] = Field(default=None, max_length=255)
    citation: ProjectionCitation

    @model_validator(mode="after")
    def validate_origin_revision(self) -> "EvidenceRelation":
        if self.origin == "owner_declared" and not self.owner_relation_revision:
            raise ValueError("knowledge_relation_owner_revision_required")
        if self.origin == "extracted" and not self.extractor_revision:
            raise ValueError("knowledge_relation_extractor_revision_required")
        return self


class RetrievableProjectionEnvelope(_StrictModel):
    source: RetrievableSourceRef
    contract_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    projector_revision: str = Field(min_length=1, max_length=255)
    projection_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_units: tuple[EvidenceUnit, ...] = Field(max_length=2000)
    records: tuple[PortableRecord, ...] = Field(default=(), max_length=50000)
    relations: tuple[EvidenceRelation, ...] = Field(default=(), max_length=20000)


class ProjectionChannelReceipt(_StrictModel):
    channel_id: str = Field(pattern=r"^[a-z0-9_.-]+$")
    modality: Literal["text", "image", "video", "audio"]
    state: Literal[
        "active",
        "unsupported",
        "not_admitted",
        "pending",
        "degraded",
        "failed",
    ]
    model_revision: Optional[str] = Field(default=None, max_length=255)
    index_revision: Optional[str] = Field(default=None, max_length=255)
    vector_count: int = Field(default=0, ge=0)
    reason: Optional[str] = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_active_receipt(self) -> "ProjectionChannelReceipt":
        if self.state == "active" and (
            not self.model_revision or not self.index_revision or self.vector_count < 1
        ):
            raise ValueError("knowledge_channel_active_receipt_incomplete")
        if self.state != "active" and self.vector_count:
            raise ValueError("knowledge_channel_inactive_vector_count_forbidden")
        return self


class ProjectionReceipt(_StrictModel):
    source_instance_id: str = Field(min_length=1, max_length=255)
    source_revision: str = Field(min_length=1, max_length=255)
    projection_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    state: Literal["active", "pending", "degraded", "blocked", "revoked", "failed"]
    channel_receipts: tuple[ProjectionChannelReceipt, ...] = Field(default=(), max_length=16)
    evidence_unit_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    next_checkpoint: Optional[str] = Field(default=None, max_length=1024)
