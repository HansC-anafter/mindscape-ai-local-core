"""Object action and relation models."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.object_runtime.catalog import ObjectAffordanceCapability
from backend.app.models.object_runtime.instance_index import ObjectInstanceRecord
from backend.app.models.object_runtime.meeting import ObjectRoleEntry
from backend.app.models.object_runtime.refs import ObjectRef
from backend.app.models.object_runtime.selection import (
    ObjectMaterializeWriteMode,
    SelectionResolveError,
)


class ObjectActionPlanRequest(BaseModel):
    """Request payload for planning a schema-backed object affordance."""

    model_config = ConfigDict(extra="forbid")

    instruction: str
    entries: List[ObjectRoleEntry] = Field(min_length=1)
    affordance_verb: Optional[str] = None
    write_mode: Optional[ObjectMaterializeWriteMode] = None
    meeting_id: Optional[str] = None
    request_context: Dict[str, Any] = Field(default_factory=dict)


class ObjectActionPlanResponse(BaseModel):
    """Structured plan for invoking an object affordance."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    status: Literal["planned", "needs_disambiguation", "unsupported", "rejected"]
    selected_affordance: Optional[ObjectAffordanceCapability] = None
    role_assignments: List[ObjectRoleEntry] = Field(default_factory=list)
    missing_roles: List[str] = Field(default_factory=list)
    write_mode: Optional[str] = None
    request_plan: Optional[Dict[str, Any]] = None
    errors: List[SelectionResolveError] = Field(default_factory=list)


class ObjectActionInvokeRequest(BaseModel):
    """Invoke a planned schema-backed object affordance."""

    model_config = ConfigDict(extra="forbid")

    instruction: str
    object_action_plan: Dict[str, Any]
    entries: List[ObjectRoleEntry] = Field(default_factory=list)
    meeting_id: Optional[str] = None
    thread_id: Optional[str] = None
    execution_id: Optional[str] = None
    request_context: Dict[str, Any] = Field(default_factory=dict)


class ObjectActionInvokeResponse(BaseModel):
    """Result of invoking an object affordance and closing addressable outputs."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    status: Literal["succeeded", "failed", "skipped"]
    action_plan_id: str
    execution_id: str
    task_id: str
    closure: Optional[Dict[str, Any]] = None
    executor_result: Dict[str, Any] = Field(default_factory=dict)
    errors: List[SelectionResolveError] = Field(default_factory=list)


class ObjectRelationRecord(BaseModel):
    """Durable relation/provenance edge between two addressable objects."""

    model_config = ConfigDict(extra="forbid")

    relation_id: Optional[str] = None
    workspace_id: Optional[str] = None
    source_ref: ObjectRef
    relation_kind: str = Field(min_length=1)
    target_ref: ObjectRef
    source_role: Optional[str] = None
    target_role: Optional[str] = None
    provenance_type: Optional[str] = None
    provenance_id: Optional[str] = None
    meeting_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ObjectRelationIndexRequest(BaseModel):
    """Batch write request for object relation/provenance edges."""

    model_config = ConfigDict(extra="forbid")

    source: Optional[str] = None
    relations: List[ObjectRelationRecord] = Field(default_factory=list)


class ObjectRelationIndexResponse(BaseModel):
    """Batch relation write result."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    indexed_count: int


class ObjectRelationSearchResponse(BaseModel):
    """Workspace-scoped relation lookup response."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    results: List[ObjectRelationRecord] = Field(default_factory=list)


class ObjectActionClosureRequest(BaseModel):
    """Persist the durable output objects and provenance for an executed action."""

    model_config = ConfigDict(extra="forbid")

    action_plan_id: str = Field(min_length=1)
    status: Literal["succeeded", "failed", "cancelled"] = "succeeded"
    entries: List[ObjectRoleEntry] = Field(default_factory=list)
    output_records: List[ObjectInstanceRecord] = Field(default_factory=list)
    output_relations: List[ObjectRelationRecord] = Field(default_factory=list)
    meeting_id: Optional[str] = None
    affordance_verb: Optional[str] = None
    execution_result: Dict[str, Any] = Field(default_factory=dict)


class ObjectActionClosureResponse(BaseModel):
    """Result of indexing action outputs and closure relations."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    action_plan_id: str
    status: Literal["succeeded", "failed", "cancelled"]
    indexed_output_count: int
    indexed_relation_count: int
    output_refs: List[ObjectRef] = Field(default_factory=list)
    relations: List[ObjectRelationRecord] = Field(default_factory=list)
