"""Object catalog and capability models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.object_runtime.refs import ObjectSelectorFamily


class ObjectAction(BaseModel):
    """Contextual runtime action exposed for a resolved object."""

    model_config = ConfigDict(extra="forbid")

    action_code: str
    label: str
    description: str
    verb: str
    mode: str
    requires_review: bool = False
    target_kind: Optional[str] = None


class ObjectResolverCapabilities(BaseModel):
    """Resolver capability flags for one installed object kind."""

    model_config = ConfigDict(extra="forbid")

    summary: bool = False
    detail: bool = False
    relations: bool = False
    actions: bool = False


class ObjectMeetingProjectionCapabilities(BaseModel):
    """Meeting entry capability summary for one object kind."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    verbs: List[str] = Field(default_factory=list)


class ObjectMaterializerCapabilities(BaseModel):
    """Materialization capability summary for one object kind."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    verbs: List[str] = Field(default_factory=list)
    write_modes: List[str] = Field(default_factory=list)
    output_types: List[str] = Field(default_factory=list)


class ObjectGraphProjectionCapabilities(BaseModel):
    """Graph projection capability summary for one object kind."""

    model_config = ConfigDict(extra="forbid")

    available: bool = False
    node_kinds: List[str] = Field(default_factory=list)
    relation_kinds: List[str] = Field(default_factory=list)


class ObjectAffordanceCapability(BaseModel):
    """Callable object affordance declared by an installed pack."""

    model_config = ConfigDict(extra="forbid")

    verb: str
    label: Optional[str] = None
    description: Optional[str] = None
    object_kinds: List[str] = Field(default_factory=list)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    required_roles: List[str] = Field(default_factory=list)
    write_modes: List[str] = Field(default_factory=list)
    planner_backend: str
    executor_backend: Optional[str] = None


class ObjectCatalogEntry(BaseModel):
    """Installed runtime object capability entry."""

    model_config = ConfigDict(extra="forbid")

    owner_pack: str
    object_kind: str
    display_name: str
    canonical_schema: Optional[str] = None
    id_field: str
    summary_fields: List[str] = Field(default_factory=list)
    supports: List[str] = Field(default_factory=list)
    granularity: Optional[str] = None
    selector_families: List[ObjectSelectorFamily] = Field(default_factory=list)
    indexer_backend: Optional[str] = None
    mention_fields: List[str] = Field(default_factory=list)
    owner_surface_patterns: List[str] = Field(default_factory=list)
    resolver_capabilities: ObjectResolverCapabilities = Field(
        default_factory=ObjectResolverCapabilities
    )
    meeting_projection_capabilities: ObjectMeetingProjectionCapabilities = Field(
        default_factory=ObjectMeetingProjectionCapabilities
    )
    materializer_capabilities: ObjectMaterializerCapabilities = Field(
        default_factory=ObjectMaterializerCapabilities
    )
    graph_projection_capabilities: ObjectGraphProjectionCapabilities = Field(
        default_factory=ObjectGraphProjectionCapabilities
    )
    affordances: List[ObjectAffordanceCapability] = Field(default_factory=list)


class ObjectCatalogResponse(BaseModel):
    """Workspace-scoped object catalog response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    catalog_version: str
    entries: List[ObjectCatalogEntry] = Field(default_factory=list)
