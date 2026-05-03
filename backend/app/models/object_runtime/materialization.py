"""Object materialization models."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.models.object_runtime.meeting import ObjectRoleEntry
from backend.app.models.object_runtime.refs import ObjectRef
from backend.app.models.object_runtime.selection import (
    ObjectMaterializeWriteMode,
    SelectionResolveError,
)


class ObjectMaterializeRequest(BaseModel):
    """Request payload for generic runtime review/promote materialization."""

    model_config = ConfigDict(extra="forbid")

    object_ref: ObjectRef
    verb: str
    intent_summary: str
    meeting_id: Optional[str] = None
    write_mode: ObjectMaterializeWriteMode = "staged"
    context_entries: List[ObjectRoleEntry] = Field(default_factory=list)
    request_context: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_context_objects(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        raw_entries = payload.get("context_entries")
        legacy_objects = payload.pop("context_objects", None)

        normalized_entries: List[Any] = []
        if isinstance(raw_entries, list):
            normalized_entries.extend(raw_entries)
        if isinstance(legacy_objects, list):
            normalized_entries.extend(
                {"role": "source", "ref": raw_object} for raw_object in legacy_objects
            )

        if normalized_entries:
            payload["context_entries"] = normalized_entries
        return payload


class ObjectMaterializeResponse(BaseModel):
    """Runtime response for generic object materialization requests."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    status: Literal["planned", "materialized", "rejected"]
    verb: str
    object_ref: ObjectRef
    staged_refs: List[ObjectRef] = Field(default_factory=list)
    review_routes: List[str] = Field(default_factory=list)
    canonical_routes: List[str] = Field(default_factory=list)
    request_plan: Optional[Dict[str, Any]] = None
    errors: List[SelectionResolveError] = Field(default_factory=list)
