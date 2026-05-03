"""Meeting attachment models for object runtime."""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.models.object_runtime.refs import ObjectRef
from backend.app.models.object_runtime.selection import (
    ObjectMeetingAttachWriteMode,
    ObjectRuntimeRole,
    SelectionResolveError,
)


class ObjectRoleEntry(BaseModel):
    """Role-bearing object context entry for attach and materialize transport."""

    model_config = ConfigDict(extra="forbid")

    role: ObjectRuntimeRole
    ref: ObjectRef


class ObjectMeetingAttachRequest(BaseModel):
    """Request payload for turning object refs into bounded meeting attachments."""

    model_config = ConfigDict(extra="forbid")

    meeting_type: str
    meeting_id: Optional[str] = None
    entries: List[ObjectRoleEntry] = Field(min_length=1)
    intent_summary: str
    write_mode: ObjectMeetingAttachWriteMode = "proposal_only"

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        raw_entries = payload.get("entries")
        legacy_objects = payload.pop("objects", None)
        legacy_target_ref = payload.pop("target_ref", None)

        normalized_entries: List[Any] = []
        if isinstance(raw_entries, list):
            normalized_entries.extend(raw_entries)
        if isinstance(legacy_objects, list):
            normalized_entries.extend(
                {"role": "source", "ref": raw_object} for raw_object in legacy_objects
            )
        if legacy_target_ref is not None:
            normalized_entries.append({"role": "target", "ref": legacy_target_ref})

        if normalized_entries:
            payload["entries"] = normalized_entries
        return payload

    @property
    def target_ref(self) -> Optional[ObjectRef]:
        for entry in self.entries:
            if entry.role == "target":
                return entry.ref
        return None

    @property
    def source_objects(self) -> List[ObjectRef]:
        return [entry.ref for entry in self.entries if entry.role == "source"]


class MeetingAttachmentSummary(BaseModel):
    """Bounded meeting attachment summary returned by the runtime."""

    model_config = ConfigDict(extra="forbid")

    role: ObjectRuntimeRole
    ref: ObjectRef
    projection_level: Literal["summary", "meeting"] = "meeting"


class ObjectMeetingAttachResponse(BaseModel):
    """Runtime response for meeting attachment requests."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    meeting_id: str
    status: Literal["attached", "materialized", "rejected"]
    attachments: List[MeetingAttachmentSummary] = Field(default_factory=list)
    target_ref: Optional[ObjectRef] = None
    staged_refs: List[ObjectRef] = Field(default_factory=list)
    review_routes: List[str] = Field(default_factory=list)
    errors: List[SelectionResolveError] = Field(default_factory=list)
