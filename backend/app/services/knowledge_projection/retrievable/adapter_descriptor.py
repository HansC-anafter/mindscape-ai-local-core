"""Validated installed-pack projection adapter descriptors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical_json import canonical_sha256


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectionLimits(_StrictModel):
    max_chunks: int = Field(ge=1, le=2000)
    max_records_per_page: int = Field(ge=1, le=50000)
    max_entities: int = Field(default=10000, ge=1, le=10000)
    max_relations: int = Field(default=20000, ge=1, le=20000)


class GraphProjectionProfile(_StrictModel):
    direct_relations: bool = False
    extraction_profile: Optional[str] = Field(
        default=None,
        pattern=r"^capabilities\.[a-z0-9_]+(?:\.[A-Za-z0-9_]+)+:[A-Za-z_][A-Za-z0-9_]*$",
    )


class KnowledgeProjectionAdapterDescriptor(_StrictModel):
    capability_code: str = Field(pattern=r"^[a-z0-9_]+$")
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    descriptor_id: str = Field(pattern=r"^[a-z0-9_]+$")
    source_kind: Literal["object", "artifact", "memory", "document"]
    object_kinds: tuple[str, ...] = Field(default=(), max_length=64)
    artifact_selectors: tuple[str, ...] = Field(default=(), max_length=64)
    contract_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    compiler_backend: str
    projection_profiles: tuple[
        Literal["semantic_text", "typed_records", "evidence_graph"],
        ...,
    ] = Field(min_length=1, max_length=3)
    evidence_unit_kinds: tuple[
        Literal["text_span", "image_region", "video_segment", "audio_segment"],
        ...,
    ] = Field(min_length=1, max_length=4)
    derived_text_kinds: tuple[
        Literal["caption", "transcript", "ocr_text", "vision_summary"],
        ...,
    ] = Field(default=(), max_length=4)
    trigger_modes: tuple[
        Literal["source_revision", "explicit_reindex", "revoke"],
        ...,
    ] = Field(min_length=1, max_length=3)
    facet_schema_module: Optional[str] = None
    graph_profile: GraphProjectionProfile = Field(default_factory=GraphProjectionProfile)
    limits: ProjectionLimits
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    capability_dir: Optional[Path] = None

    @model_validator(mode="after")
    def validate_owner_and_source(self) -> "KnowledgeProjectionAdapterDescriptor":
        prefix = f"capabilities.{self.capability_code}."
        if not self.compiler_backend.startswith(prefix) or ":" not in self.compiler_backend:
            raise ValueError("knowledge_projection_backend_must_be_capability_owned")
        if self.facet_schema_module and not self.facet_schema_module.startswith(prefix):
            raise ValueError("knowledge_projection_facet_schema_must_be_capability_owned")
        extraction = self.graph_profile.extraction_profile
        if extraction and not extraction.startswith(prefix):
            raise ValueError("knowledge_projection_extraction_profile_must_be_capability_owned")
        if self.source_kind == "object" and not self.object_kinds:
            raise ValueError("knowledge_projection_object_kinds_required")
        if self.source_kind != "object" and self.object_kinds:
            raise ValueError("knowledge_projection_object_kinds_forbidden")
        if self.source_kind == "artifact" and not self.artifact_selectors:
            raise ValueError("knowledge_projection_artifact_selectors_required")
        if self.source_kind != "artifact" and self.artifact_selectors:
            raise ValueError("knowledge_projection_artifact_selectors_forbidden")
        if len(set(self.projection_profiles)) != len(self.projection_profiles):
            raise ValueError("knowledge_projection_profiles_duplicate")
        if len(set(self.evidence_unit_kinds)) != len(self.evidence_unit_kinds):
            raise ValueError("knowledge_projection_evidence_unit_kinds_duplicate")
        if len(set(self.trigger_modes)) != len(self.trigger_modes):
            raise ValueError("knowledge_projection_trigger_modes_duplicate")
        return self

    @property
    def descriptor_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"capability_dir"})
        return canonical_sha256(payload)

    @classmethod
    def from_manifest_entry(
        cls,
        *,
        capability_code: str,
        capability_version: str,
        manifest_hash: str,
        capability_dir: Path,
        raw: Mapping[str, Any],
    ) -> "KnowledgeProjectionAdapterDescriptor":
        return cls(
            capability_code=capability_code,
            capability_version=capability_version,
            descriptor_id=raw.get("id"),
            source_kind=raw.get("source_kind"),
            object_kinds=tuple(raw.get("object_kinds") or ()),
            artifact_selectors=tuple(raw.get("artifact_selectors") or ()),
            contract_version=raw.get("contract_version"),
            compiler_backend=raw.get("compiler_backend"),
            projection_profiles=tuple(raw.get("projection_profiles") or ()),
            evidence_unit_kinds=tuple(raw.get("evidence_unit_kinds") or ()),
            derived_text_kinds=tuple(raw.get("derived_text_kinds") or ()),
            trigger_modes=tuple(raw.get("trigger_modes") or ()),
            facet_schema_module=raw.get("facet_schema_module"),
            graph_profile=raw.get("graph_profile") or {},
            limits=raw.get("limits") or {},
            manifest_hash=manifest_hash,
            capability_dir=capability_dir,
        )
