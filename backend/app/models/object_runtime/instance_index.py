"""Object instance index models."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.object_runtime.refs import ObjectRef


class ObjectInstanceRecord(BaseModel):
    """Workspace-scoped searchable read-model row for a concrete object."""

    model_config = ConfigDict(extra="forbid")

    ref: ObjectRef
    title: str
    subtitle: Optional[str] = None
    summary_text: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    thumbnail_ref: Optional[str] = None
    owner_surface_url: Optional[str] = None
    mention_tokens: List[str] = Field(default_factory=list)
    mention_text: str = ""
    search_text: str = ""
    affordance_verbs: List[str] = Field(default_factory=list)
    stale: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[str] = None


class ObjectInstanceIndexRequest(BaseModel):
    """Batch index request from an owner-pack object indexer."""

    model_config = ConfigDict(extra="forbid")

    source: Optional[str] = None
    records: List[ObjectInstanceRecord] = Field(default_factory=list)


class ObjectInstanceIndexResponse(BaseModel):
    """Batch index write result."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    indexed_count: int


class ObjectInstanceSyncRequest(BaseModel):
    """Workspace-scoped indexer discovery/sync request."""

    model_config = ConfigDict(extra="forbid")

    owner_pack: Optional[str] = None
    object_kind: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=500)
    force: bool = False
    reason: Optional[str] = None


class ObjectInstanceSyncSourceResult(BaseModel):
    """Per catalog-indexer sync outcome."""

    model_config = ConfigDict(extra="forbid")

    owner_pack: str
    object_kind: str
    indexer_backend: str
    indexed_count: int = 0
    status: Literal["synced", "skipped", "failed"] = "synced"
    message: Optional[str] = None


class ObjectInstanceSyncResponse(BaseModel):
    """Object instance sync result across discovered owner-pack indexers."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    indexed_count: int
    sources: List[ObjectInstanceSyncSourceResult] = Field(default_factory=list)


class ObjectSearchResponse(BaseModel):
    """Concrete object instance search response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    query: str
    results: List[ObjectInstanceRecord] = Field(default_factory=list)


class ObjectReadRequest(BaseModel):
    """Read a concrete workspace object instance from a stable ObjectRef."""

    model_config = ConfigDict(extra="forbid")

    object_ref: Dict[str, Any]


class ObjectReadResponse(BaseModel):
    """Workspace-scoped read response for a concrete object instance."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    object: ObjectInstanceRecord


class ObjectMentionCompletionItem(BaseModel):
    """Command-bar mention completion item backed by the object index."""

    model_config = ConfigDict(extra="forbid")

    id: str
    token: str
    label: str
    description: str
    ref: ObjectRef
    owner_pack: str
    object_kind: str
    score: float = 0.0
    source: str = "object_instance_registry"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ObjectMentionCompletionResponse(BaseModel):
    """Mention completion response for the meeting command bar."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    query: str
    results: List[ObjectMentionCompletionItem] = Field(default_factory=list)
