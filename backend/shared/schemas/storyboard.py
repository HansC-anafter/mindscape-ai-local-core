"""
Storyboard Shared Contract — Cross-Pack Schema

Shared data contract between:
  - performance_direction (Producer: intent, cue_assets, energy_level)
  - voice_engine (Producer: cue audio files)
  - sonic_space (Producer: soundscape audio)
  - video_renderer (Consumer: scene_manifest -> clip_refs)
  - multi_media_studio (Orchestrator: timeline assembly, status, render_profile)

Vendored into local-core so installed capability packs can resolve
``shared.schemas.storyboard`` without requiring the cloud repo at runtime.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class NarrativeRole(str, Enum):
    ESTABLISH_STATE = "establish_state"
    DELIVER_INFO = "deliver_info"
    TRANSITION = "transition"
    CLIMAX = "climax"
    RESOLUTION = "resolution"


class StoryboardStatus(str, Enum):
    DRAFT = "draft"
    PREVIEWING = "previewing"
    PREVIEW_DONE = "preview_done"
    PRODUCING = "producing"
    COMPLETED = "completed"
    FAILED = "failed"


class RendererType(str, Enum):
    GENERATIVE = "generative"
    HUMAN = "human"
    MANUAL_UPLOAD = "manual_upload"


class SourceType(str, Enum):
    GENERATIVE = "generative"
    HUMAN = "human"
    HYBRID = "hybrid"


class ObjectSelectionMode(str, Enum):
    ALL = "all"
    NAMED = "named"
    MANUAL_MASK = "manual_mask"


class ObjectUsagePurpose(str, Enum):
    FOREGROUND = "foreground"
    PROP = "prop"
    BACKGROUND_SUPPORT = "background_support"


class RepaintPolicy(str, Enum):
    FORBID = "forbid"
    ALLOW = "allow"


class ImpactRegionMode(str, Enum):
    OBJECT_ONLY = "object_only"
    CONTACT_ZONE = "contact_zone"
    LOCAL_SCENE = "local_scene"


class QualityGateState(str, Enum):
    AUTO_APPROVED = "auto_approved"
    MANUAL_REQUIRED = "manual_required"
    ESCALATE_LOCAL_SCENE = "escalate_local_scene"


OBJECT_REUSE_SCHEMA_VERSION = "object_reuse.v1"
OBJECT_WORKLOAD_SNAPSHOT_SCHEMA_VERSION = "object_workload_snapshot.v1"

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _stable_short_hash(*parts: Any) -> str:
    payload = "|".join(str(part).strip() for part in parts if str(part).strip())
    if not payload:
        return uuid.uuid4().hex[:12]
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _slugify_token(value: Any, *, fallback: str = "object") -> str:
    lowered = str(value or "").strip().lower()
    token = _NON_ALNUM_RE.sub("_", lowered).strip("_")
    return token or fallback


def _normalize_string_list(values: Any) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = str(raw or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _normalize_bbox_payload(value: Any) -> Optional[dict[str, int]]:
    if not isinstance(value, dict):
        return None
    try:
        x = int(value.get("x", 0))
        y = int(value.get("y", 0))
        width = int(value.get("width", 0))
        height = int(value.get("height", 0))
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return {
        "x": max(x, 0),
        "y": max(y, 0),
        "width": width,
        "height": height,
    }


def _normalize_usage_bindings_payload(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values:
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(mode="python")
        if not isinstance(raw, dict):
            continue
        scene_id = str(raw.get("scene_id") or "").strip()
        if not scene_id:
            continue
        key = scene_id.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "scene_id": scene_id,
                "purpose": raw.get("purpose") or ObjectUsagePurpose.PROP.value,
                "placement_policy": raw.get("placement_policy") or "inherit",
                "transform_override": dict(raw.get("transform_override") or {}),
                "crop_policy": raw.get("crop_policy"),
                "scale_policy": raw.get("scale_policy"),
                "repaint_policy": raw.get("repaint_policy") or RepaintPolicy.FORBID.value,
                "rerender_mode_override": raw.get("rerender_mode_override"),
                "impact_region_override": _normalize_bbox_payload(
                    raw.get("impact_region_override")
                ),
            }
        )
    return normalized


def _upgrade_legacy_usage_bindings(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    payload = dict(data)
    explicit_bindings = _normalize_usage_bindings_payload(payload.get("usage_bindings"))
    legacy_scene_ids = _normalize_string_list(
        payload.get("legacy_usage_scene_ids") or payload.get("usage_scene_ids")
    )
    if not explicit_bindings and legacy_scene_ids:
        explicit_bindings = [
            {
                "scene_id": scene_id,
                "purpose": ObjectUsagePurpose.PROP.value,
                "placement_policy": "inherit",
                "transform_override": {},
                "crop_policy": None,
                "scale_policy": None,
                "repaint_policy": RepaintPolicy.FORBID.value,
            }
            for scene_id in legacy_scene_ids
        ]
    payload["usage_bindings"] = explicit_bindings
    if legacy_scene_ids:
        payload["legacy_usage_scene_ids"] = legacy_scene_ids
    payload.setdefault("schema_version", OBJECT_REUSE_SCHEMA_VERSION)
    return payload


class SceneIntent(BaseModel):
    emotional_function: str = ""
    narrative_role: NarrativeRole = NarrativeRole.ESTABLISH_STATE
    capture_moment: Optional[str] = None
    persona_target: str = "character"


class CueAssets(BaseModel):
    pre_roll: Optional[str] = None
    in_take: Optional[str] = None
    recovery: Optional[str] = None
    soundscape: Optional[str] = None


class ClipRef(BaseModel):
    storage_key: str
    url: Optional[str] = None
    local_path: Optional[str] = None
    storage_type: str = "local"
    content_type: str = "video/mp4"
    renderer: RendererType = RendererType.GENERATIVE
    metadata: dict[str, Any] = Field(default_factory=dict)


class RenderProfile(BaseModel):
    profile_id: str = "vr_preview_local"
    comfy_address: str = "http://localhost:8188"
    overrides: dict[str, Any] = Field(default_factory=dict)


class ObjectUsageBinding(BaseModel):
    scene_id: str
    purpose: ObjectUsagePurpose = ObjectUsagePurpose.PROP
    placement_policy: str = "inherit"
    transform_override: dict[str, Any] = Field(default_factory=dict)
    crop_policy: Optional[str] = None
    scale_policy: Optional[str] = None
    repaint_policy: RepaintPolicy = RepaintPolicy.FORBID
    rerender_mode_override: Optional[ImpactRegionMode] = None
    impact_region_override: Optional[dict[str, int]] = None

    @model_validator(mode="after")
    def normalize_impact_region_override(self) -> "ObjectUsageBinding":
        self.impact_region_override = _normalize_bbox_payload(self.impact_region_override)
        return self


class ObjectTarget(BaseModel):
    object_id: str = ""
    object_instance_id: str = ""
    object_semantic_key: str = ""
    alias_keys: list[str] = Field(default_factory=list)
    selector_mode: ObjectSelectionMode = ObjectSelectionMode.NAMED
    label: str = ""
    region_hint: Any = None
    preserve_attributes: list[str] = Field(default_factory=list)
    source_reference_fingerprint: str = ""

    @model_validator(mode="after")
    def apply_identity_defaults(self) -> "ObjectTarget":
        alias_keys = _normalize_string_list(self.alias_keys)
        semantic_seed = (
            self.object_semantic_key
            or self.label
            or self.object_id
            or (alias_keys[0] if alias_keys else "")
        )
        self.object_semantic_key = _slugify_token(semantic_seed)
        if not self.object_id:
            self.object_id = self.object_semantic_key
        fingerprint = self.source_reference_fingerprint or "unknown_reference"
        if not self.object_instance_id:
            region_hint_repr = ""
            if self.region_hint not in (None, "", {}):
                try:
                    region_hint_repr = json.dumps(self.region_hint, sort_keys=True)
                except TypeError:
                    region_hint_repr = str(self.region_hint)
            self.object_instance_id = f"obj_{_stable_short_hash(self.object_semantic_key, fingerprint, region_hint_repr)}"
        self.alias_keys = _normalize_string_list(
            [*alias_keys, self.object_id, self.label, self.object_semantic_key]
        )
        self.preserve_attributes = _normalize_string_list(self.preserve_attributes)
        return self


class ObjectAssetRef(BaseModel):
    asset_ref: Any = None
    source_scene_ref: str = ""
    object_target_id: str = ""
    object_instance_id: str = ""
    lineage_parent_asset_id: Optional[str] = None
    version: Optional[str] = None
    source_reference_fingerprint: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObjectReusePlan(BaseModel):
    schema_version: str = OBJECT_REUSE_SCHEMA_VERSION
    usage_bindings: list[ObjectUsageBinding] = Field(default_factory=list)
    legacy_usage_scene_ids: list[str] = Field(default_factory=list)
    transform_defaults: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_usage_scene_ids(cls, data: Any) -> Any:
        return _upgrade_legacy_usage_bindings(data)

    @model_validator(mode="after")
    def derive_legacy_projection(self) -> "ObjectReusePlan":
        self.schema_version = self.schema_version or OBJECT_REUSE_SCHEMA_VERSION
        self.legacy_usage_scene_ids = _normalize_string_list(
            binding.scene_id for binding in self.usage_bindings
        )
        return self


class ObjectWorkloadSnapshot(BaseModel):
    schema_version: str = OBJECT_WORKLOAD_SNAPSHOT_SCHEMA_VERSION
    source_scene_id: str = ""
    source_reference_id: str = ""
    source_reference_fingerprint: str = ""
    source_image_ref: dict[str, Any] = Field(default_factory=dict)
    selection_mode: ObjectSelectionMode = ObjectSelectionMode.NAMED
    policy_mode: str = "portable"
    binding_mode: str = "frozen_workload_snapshot"
    workflow_commit_id: Optional[str] = None
    model_binding_ref: Any = None
    usage_bindings: list[ObjectUsageBinding] = Field(default_factory=list)
    legacy_usage_scene_ids: list[str] = Field(default_factory=list)
    source_workload_ref: Optional[str] = None
    source_run_ref: Optional[str] = None
    source_projection_ref: Optional[str] = None
    impact_region_mode: Optional[ImpactRegionMode] = None
    impact_region_bbox: Optional[dict[str, int]] = None
    impact_region_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    affected_object_instance_ids: list[str] = Field(default_factory=list)
    quality_gate_state: Optional[QualityGateState] = None

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_usage_scene_ids(cls, data: Any) -> Any:
        upgraded = _upgrade_legacy_usage_bindings(data)
        if isinstance(upgraded, dict):
            upgraded["schema_version"] = (
                upgraded.get("schema_version")
                if upgraded.get("schema_version")
                not in {None, "", OBJECT_REUSE_SCHEMA_VERSION}
                else OBJECT_WORKLOAD_SNAPSHOT_SCHEMA_VERSION
            )
        return upgraded

    @model_validator(mode="after")
    def derive_legacy_projection(self) -> "ObjectWorkloadSnapshot":
        self.schema_version = self.schema_version or OBJECT_WORKLOAD_SNAPSHOT_SCHEMA_VERSION
        self.legacy_usage_scene_ids = _normalize_string_list(
            binding.scene_id for binding in self.usage_bindings
        )
        if not isinstance(self.source_image_ref, dict):
            self.source_image_ref = {}
        self.impact_region_bbox = _normalize_bbox_payload(self.impact_region_bbox)
        self.affected_object_instance_ids = _normalize_string_list(
            self.affected_object_instance_ids
        )
        return self


class DirectionIR(BaseModel):
    ir_id: str = Field(default_factory=lambda: f"ir_{uuid.uuid4().hex[:12]}")
    intent: SceneIntent = Field(default_factory=SceneIntent)
    must_preserve: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    free_variation: list[str] = Field(default_factory=list)
    avoid_failure_modes: list[str] = Field(default_factory=list)
    composition_anchors: list[str] = Field(default_factory=list)
    style_anchors: list[str] = Field(default_factory=list)
    subject_anchors: list[str] = Field(default_factory=list)
    object_targets: list[ObjectTarget] = Field(default_factory=list)
    object_constraints: list[str] = Field(default_factory=list)
    source_reference_ids: list[str] = Field(default_factory=list)
    lens_stack: list[dict[str, Any]] = Field(default_factory=list)
    runtime_hints: dict[str, Any] = Field(default_factory=dict)
    compilation_provenance: dict[str, Any] = Field(default_factory=dict)


class Scene(BaseModel):
    scene_id: str = Field(default_factory=lambda: f"sc_{uuid.uuid4().hex[:8]}")
    scene_manifest: dict[str, Any] = Field(default_factory=dict)
    intent: Optional[SceneIntent] = None
    duration_sec: float = 5.0
    energy_level: float = 0.5
    reference_ids: list[str] = Field(default_factory=list)
    direction_ir: Optional[DirectionIR] = None
    object_assets: list[ObjectAssetRef] = Field(default_factory=list)
    object_reuse_plan: Optional[ObjectReusePlan] = None
    object_workload_snapshot: Optional[ObjectWorkloadSnapshot] = None
    cue_assets: Optional[CueAssets] = None
    clip_refs: list[ClipRef] = Field(default_factory=list)
    transitions: dict[str, Any] = Field(default_factory=dict)


class StoryboardManifest(BaseModel):
    storyboard_id: str = Field(default_factory=lambda: f"sb_{uuid.uuid4().hex[:12]}")
    workspace_id: str = ""
    scenes: list[Scene] = Field(default_factory=list)
    render_profile: Optional[RenderProfile] = None
    global_settings: dict[str, Any] = Field(default_factory=dict)
    status: StoryboardStatus = StoryboardStatus.DRAFT
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
