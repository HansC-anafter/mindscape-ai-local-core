"""Reference and selector models for the Addressable Object Layer."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ObjectSelectorFamily = Literal[
    "object_root",
    "dom_anchor",
    "image_region",
    "media_time_range",
    "storyboard_scene",
    "storyboard_slot",
    "timeline_clip",
    "pack_local_path",
    "graph_node",
]


class ObjectSelectorRegion(BaseModel):
    """Normalized rectangular selector bounds for visual and canvas objects."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    w: float
    h: float

    @model_validator(mode="after")
    def _validate_size(self) -> "ObjectSelectorRegion":
        if self.w <= 0 or self.h <= 0:
            raise ValueError("selector region width and height must be positive")
        return self


class ObjectSelector(BaseModel):
    """Typed sub-object selector used by AOL runtime payloads.

    Existing legacy selector dictionaries remain accepted by ObjectRef and
    SelectionHints when they do not declare selector_type.
    """

    model_config = ConfigDict(extra="forbid")

    selector_type: ObjectSelectorFamily
    surface_id: Optional[str] = None
    element_id: Optional[str] = None
    dom_id: Optional[str] = None
    css_selector: Optional[str] = None
    xpath: Optional[str] = None
    region: Optional[ObjectSelectorRegion] = None
    time_start_seconds: Optional[float] = None
    time_end_seconds: Optional[float] = None
    scene_id: Optional[str] = None
    slot_id: Optional[str] = None
    clip_id: Optional[str] = None
    path: Optional[str] = None
    node_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_selector_family_payload(self) -> "ObjectSelector":
        if self.selector_type == "dom_anchor" and not any(
            [self.dom_id, self.css_selector, self.xpath, self.element_id]
        ):
            raise ValueError(
                "dom_anchor selectors require dom_id, css_selector, xpath, or element_id"
            )
        if self.selector_type == "image_region" and self.region is None:
            raise ValueError("image_region selectors require region")
        if self.selector_type == "media_time_range":
            if self.time_start_seconds is None or self.time_end_seconds is None:
                raise ValueError(
                    "media_time_range selectors require time_start_seconds and time_end_seconds"
                )
            if self.time_start_seconds < 0 or self.time_end_seconds < 0:
                raise ValueError("media_time_range selector times must be non-negative")
            if self.time_end_seconds < self.time_start_seconds:
                raise ValueError(
                    "media_time_range selector end must be greater than or equal to start"
                )
        if self.selector_type == "storyboard_scene" and not self.scene_id:
            raise ValueError("storyboard_scene selectors require scene_id")
        if self.selector_type == "storyboard_slot" and not self.slot_id:
            raise ValueError("storyboard_slot selectors require slot_id")
        if self.selector_type == "timeline_clip" and not self.clip_id:
            raise ValueError("timeline_clip selectors require clip_id")
        if self.selector_type == "pack_local_path" and not self.path:
            raise ValueError("pack_local_path selectors require path")
        if self.selector_type == "graph_node" and not self.node_id:
            raise ValueError("graph_node selectors require node_id")
        return self


def _validate_object_selector_payload(value: Any) -> Optional[Dict[str, Any]]:
    """Validate typed selector payloads without rewriting legacy selectors."""

    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("selector must be an object")
    if "selector_type" not in value:
        return value
    return ObjectSelector.model_validate(value).model_dump(exclude_none=True)


class ObjectRef(BaseModel):
    """Stable transport identity for an addressable object."""

    model_config = ConfigDict(extra="forbid")

    uri: str
    owner_pack: str
    object_kind: str
    object_id: str
    workspace_id: Optional[str] = None
    version: Optional[str] = None
    selector: Optional[Dict[str, Any]] = None
    source_surface: Optional[str] = None

    @field_validator("selector", mode="before")
    @classmethod
    def _validate_selector(cls, value: Any) -> Optional[Dict[str, Any]]:
        return _validate_object_selector_payload(value)


class ObjectSummary(BaseModel):
    """Bounded runtime summary for object-aware UI and meeting entry."""

    model_config = ConfigDict(extra="forbid")

    ref: ObjectRef
    title: str
    subtitle: Optional[str] = None
    summary_text: Optional[str] = None
    status: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    thumbnail_ref: Optional[str] = None
    owner_surface_url: Optional[str] = None
    updated_at: Optional[str] = None
