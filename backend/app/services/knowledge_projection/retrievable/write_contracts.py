"""Internal complete-generation contracts for the authorized vector writer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from backend.app.services.knowledge_graph.contracts import GraphProjectionWrite


_UNIT_KINDS = frozenset(
    {"text_span", "image_region", "video_segment", "audio_segment"}
)
_MODALITIES = frozenset({"text", "image", "video", "audio"})
_CHANNEL_STATES = frozenset(
    {
        "active",
        "pending",
        "degraded",
        "unsupported",
        "not_admitted",
        "failed",
        "revoked",
    }
)


def _required(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"knowledge_projection_{field_name}_required")
    return normalized


@dataclass(frozen=True)
class ExternalDocumentWrite:
    source_id: str
    doc_type: str
    title: str
    content: str
    embedding: tuple[float, ...]
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field_name in ("source_id", "doc_type", "content"):
            object.__setattr__(
                self,
                field_name,
                _required(getattr(self, field_name), field_name),
            )
        if not self.embedding:
            raise ValueError("knowledge_projection_embedding_required")


@dataclass(frozen=True)
class ProjectionEvidenceWrite:
    unit_key: str
    unit_kind: str
    owner_asset_ref: str
    content_hash: str
    media_type: Optional[str]
    anchor: Mapping[str, Any]
    derivative_refs: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.unit_kind not in _UNIT_KINDS:
            raise ValueError("knowledge_projection_evidence_kind_forbidden")
        if len(self.content_hash) != 64:
            raise ValueError("knowledge_projection_evidence_hash_invalid")
        _required(self.unit_key, "evidence_unit_key")
        _required(self.owner_asset_ref, "owner_asset_ref")
        if not self.anchor:
            raise ValueError("knowledge_projection_evidence_anchor_required")


@dataclass(frozen=True)
class ProjectionChannelWrite:
    unit_key: str
    channel_id: str
    modality: str
    profile_revision: str
    model_revision: Optional[str]
    dimension: Optional[int]
    calibration_revision: Optional[str]
    index_revision: Optional[str]
    required: bool
    state: str
    row_count: int
    byte_count: int
    reason: Optional[str] = None
    physical_store_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if self.modality not in _MODALITIES:
            raise ValueError("knowledge_projection_channel_modality_forbidden")
        if self.state not in _CHANNEL_STATES:
            raise ValueError("knowledge_projection_channel_state_forbidden")
        if self.row_count < 0 or self.byte_count < 0:
            raise ValueError("knowledge_projection_channel_counts_invalid")
        if self.state == "active" and (
            not self.model_revision
            or not self.index_revision
            or self.row_count < 1
        ):
            raise ValueError("knowledge_projection_channel_active_incomplete")
        if self.state != "active" and self.row_count != 0:
            raise ValueError("knowledge_projection_channel_inactive_rows_forbidden")


@dataclass(frozen=True)
class ProjectionFacetWrite:
    key: str
    value_type: str
    value: str | float | int | bool
    ordinal: int = 0


@dataclass(frozen=True)
class ProjectionRecordWrite:
    record_kind: str
    record_key: str
    search_text: str
    citation: Mapping[str, Any]
    values: Mapping[str, Any]
    content_hash: str
    facets: tuple[ProjectionFacetWrite, ...] = ()


@dataclass(frozen=True)
class RetrievableProjectionWrite:
    source_instance_id: str
    source_revision: str
    content_hash: str
    descriptor_id: str
    descriptor_revision: str
    projector_revision: str
    facet_schema_revision: str
    embedding_profile_revision: str
    projection_hash: str
    evidence_units: tuple[ProjectionEvidenceWrite, ...]
    channels: tuple[ProjectionChannelWrite, ...]
    records: tuple[ProjectionRecordWrite, ...] = ()
    relation_count: int = 0
    graph_complete: bool = False
    graph_required: bool = False
    graph: Optional[GraphProjectionWrite] = None

    def __post_init__(self) -> None:
        for field_name in (
            "source_instance_id",
            "source_revision",
            "descriptor_id",
            "descriptor_revision",
            "projector_revision",
            "facet_schema_revision",
            "embedding_profile_revision",
        ):
            _required(getattr(self, field_name), field_name)
        for field_name in ("content_hash", "projection_hash"):
            if len(getattr(self, field_name)) != 64:
                raise ValueError(f"knowledge_projection_{field_name}_invalid")
        evidence_keys = {unit.unit_key for unit in self.evidence_units}
        if len(evidence_keys) != len(self.evidence_units):
            raise ValueError("knowledge_projection_evidence_unit_duplicate")
        if any(channel.unit_key not in evidence_keys for channel in self.channels):
            raise ValueError("knowledge_projection_channel_unit_missing")
        covered_units = {channel.unit_key for channel in self.channels}
        if covered_units != evidence_keys:
            raise ValueError("knowledge_projection_channel_coverage_incomplete")
        if self.relation_count < 0:
            raise ValueError("knowledge_projection_relation_count_invalid")
        if self.graph is not None and self.relation_count != len(
            self.graph.relations
        ):
            raise ValueError("knowledge_projection_relation_count_mismatch")
        if self.graph_complete != (self.graph is not None):
            raise ValueError("knowledge_projection_graph_complete_mismatch")
        if self.graph is not None:
            record_keys = {record.record_key for record in self.records}
            for mention in self.graph.mentions:
                if (
                    mention.evidence_unit_key
                    and mention.evidence_unit_key not in evidence_keys
                ):
                    raise ValueError(
                        "knowledge_projection_graph_evidence_missing"
                    )
                if mention.record_key and mention.record_key not in record_keys:
                    raise ValueError(
                        "knowledge_projection_graph_record_missing"
                    )
            if any(
                set(relation.supporting_evidence_unit_keys) - evidence_keys
                for relation in self.graph.relations
            ):
                raise ValueError(
                    "knowledge_projection_graph_relation_evidence_missing"
                )


__all__ = [
    "ExternalDocumentWrite",
    "ProjectionChannelWrite",
    "ProjectionEvidenceWrite",
    "ProjectionFacetWrite",
    "ProjectionRecordWrite",
    "RetrievableProjectionWrite",
]
