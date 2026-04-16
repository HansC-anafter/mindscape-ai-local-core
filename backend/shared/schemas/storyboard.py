"""
Storyboard Shared Contract — Cross-Pack Schema

Shared data contract between:
  - performance_direction (Producer: intent, cue_assets, energy_level)
  - voice_engine (Producer: cue audio files)
  - sonic_space (Producer: soundscape audio)
  - video_renderer (Consumer: scene_manifest → clip_refs)
  - multi_media_studio (Orchestrator: timeline assembly, status, render_profile)

ADR: docs/architecture/decisions/ADR-2026-03-17-storyboard-shared-contract.md

Zero external dependencies beyond Pydantic + stdlib.
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

from .motion_generation_receipt import MotionGenerationReceipt


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NarrativeRole(str, Enum):
    """Scene's narrative function within the overall sequence."""
    ESTABLISH_STATE = "establish_state"
    DELIVER_INFO = "deliver_info"
    TRANSITION = "transition"
    CLIMAX = "climax"
    RESOLUTION = "resolution"


class StoryboardStatus(str, Enum):
    """ProductionRun lifecycle states."""
    DRAFT = "draft"
    PREVIEWING = "previewing"
    PREVIEW_DONE = "preview_done"
    PRODUCING = "producing"
    COMPLETED = "completed"
    FAILED = "failed"


class RendererType(str, Enum):
    """Which renderer produced the clip."""
    GENERATIVE = "generative"       # video_renderer (AI)
    HUMAN = "human"                 # performance_direction (human shoot)
    MANUAL_UPLOAD = "manual_upload" # direct user upload


class SourceType(str, Enum):
    """ProductionRun source strategy."""
    GENERATIVE = "generative"  # All scenes → VR
    HUMAN = "human"            # All scenes → human shoot
    HYBRID = "hybrid"          # Per-scene decision


class ObjectSelectionMode(str, Enum):
    """How an object target was selected from the source scene."""
    ALL = "all"
    NAMED = "named"
    MANUAL_MASK = "manual_mask"


class ObjectUsagePurpose(str, Enum):
    """Why an object asset is reused in a target scene."""
    FOREGROUND = "foreground"
    PROP = "prop"
    BACKGROUND_SUPPORT = "background_support"


class RepaintPolicy(str, Enum):
    """Whether a target scene may repaint the reused object."""
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


class WorldInterchangeKind(str, Enum):
    OPENUSD = "openusd"


OBJECT_REUSE_SCHEMA_VERSION = "object_reuse.v1"
OBJECT_WORKLOAD_SNAPSHOT_SCHEMA_VERSION = "object_workload_snapshot.v1"
CHARACTER_BINDING_MODES = {"reference_only", "adapter_only", "hybrid"}
PERFORMANCE_MODES = {"portrait_animation", "audio_driven_talking_head"}
PERFORMANCE_REPLAY_SCOPES = {
    "same_identity_only",
    "retargetable_cross_identity",
}
CHARACTER_ADAPTER_SCOPE_KINDS = {"scene", "subject"}
CHARACTER_ADAPTER_SLOT_ROLES = {
    "identity",
    "identity_face",
    "identity_body",
    "style",
}

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


def _normalize_choice(value: Any, allowed: set[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in allowed:
        return normalized
    return ""


def _normalize_optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return max(normalized, 0)


def _normalize_optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_model_list(values: Any, model_cls: type[BaseModel]) -> list[Any]:
    if not isinstance(values, list):
        return []
    normalized: list[Any] = []
    seen: set[str] = set()
    for raw in values:
        if isinstance(raw, model_cls):
            item = raw
        elif isinstance(raw, dict):
            item = model_cls.model_validate(raw)
        elif hasattr(raw, "model_dump"):
            item = model_cls.model_validate(raw.model_dump(mode="python"))
        else:
            continue
        marker = json.dumps(
            item.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(item)
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


def _normalize_structured_dict_list(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values:
        if isinstance(raw, dict):
            payload = dict(raw)
        elif hasattr(raw, "model_dump"):
            payload = dict(raw.model_dump(mode="json"))
        else:
            continue
        marker = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(payload)
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


# ---------------------------------------------------------------------------
# Core Value Objects
# ---------------------------------------------------------------------------

class SceneIntent(BaseModel):
    """Director's intent layer — produced by performance_direction."""
    emotional_function: str = ""
    narrative_role: NarrativeRole = NarrativeRole.ESTABLISH_STATE
    capture_moment: Optional[str] = None
    persona_target: str = "character"


class CueAssets(BaseModel):
    """Voice cue assets — synthesized by voice_engine, arranged by PD."""
    pre_roll: Optional[str] = None    # Pre-shot state building (storage_key)
    in_take: Optional[str] = None     # Ultra-short in-shot cue (storage_key)
    recovery: Optional[str] = None    # Drift correction cue (storage_key)
    soundscape: Optional[str] = None  # Mood soundscape from sonic_space (storage_key)


class ClipRef(BaseModel):
    """Reference to a rendered/captured media asset."""
    storage_key: str
    url: Optional[str] = None
    local_path: Optional[str] = None
    storage_type: str = "local"        # "local" | "cloud" | "comfyui"
    content_type: str = "video/mp4"
    renderer: RendererType = RendererType.GENERATIVE
    metadata: dict[str, Any] = Field(default_factory=dict)


class RenderProfile(BaseModel):
    """
    Rendering quality configuration — the ONLY difference between Preview and Production.

    Preview:  profile_id="vr_preview_local", steps=4, width=512
    Production: profile_id="wan22_t2v_base", steps=20, width=1280
    """
    profile_id: str = "vr_preview_local"
    comfy_address: str = "http://localhost:8188"
    overrides: dict[str, Any] = Field(default_factory=dict)


class ObjectUsageBinding(BaseModel):
    """Per-scene reuse binding for a registered object asset."""
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
        self.impact_region_override = _normalize_bbox_payload(
            self.impact_region_override
        )
        return self


class ObjectTarget(BaseModel):
    """Stable identity for an intended object across packs and reruns."""
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
    """Stable object asset reference carried across scene composition and reruns."""
    asset_ref: Any = None
    source_scene_ref: str = ""
    object_target_id: str = ""
    object_instance_id: str = ""
    lineage_parent_asset_id: Optional[str] = None
    version: Optional[str] = None
    source_reference_fingerprint: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObjectReusePlan(BaseModel):
    """Canonical object reuse plan with legacy upgrade support."""
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
    """Durable workload truth for object extraction/reuse tasks."""
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


class SceneControlRef(BaseModel):
    control_kind: str = ""
    ref: dict[str, Any] = Field(default_factory=dict)
    provider: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_payload(self) -> "SceneControlRef":
        self.control_kind = str(self.control_kind or "").strip()
        self.provider = str(self.provider or "").strip()
        if not isinstance(self.ref, dict):
            self.ref = {}
        if not isinstance(self.metadata, dict):
            self.metadata = {}
        return self


class SceneSpatialMetadata(BaseModel):
    coordinate_system: str = ""
    unit_scale: float = 1.0
    up_axis: str = "Y"
    forward_axis: str = "-Z"
    grounding_mode: str = ""


class MediaAssetRef(BaseModel):
    workspace_artifact_id: str = ""
    storage_key: str = ""
    local_path: str = ""
    url: str = ""
    mime_type: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_payload(self) -> "MediaAssetRef":
        self.workspace_artifact_id = str(self.workspace_artifact_id or "").strip()
        self.storage_key = str(self.storage_key or "").strip()
        self.local_path = str(self.local_path or "").strip()
        self.url = str(self.url or "").strip()
        self.mime_type = str(self.mime_type or "").strip()
        if not isinstance(self.metadata, dict):
            self.metadata = {}
        return self

    def has_locator(self) -> bool:
        return any(
            (
                self.workspace_artifact_id,
                self.storage_key,
                self.local_path,
                self.url,
            )
        )


class CaptureBundleRef(BaseModel):
    capture_bundle_id: str = ""
    source_kind: str = ""
    workspace_artifact_id: str = ""
    video_ref: Optional[MediaAssetRef] = None
    frame_refs: list[MediaAssetRef] = Field(default_factory=list)
    multiview_frame_count: int = 0
    producer_tool: str = ""

    @model_validator(mode="after")
    def normalize_payload(self) -> "CaptureBundleRef":
        self.capture_bundle_id = str(self.capture_bundle_id or "").strip()
        self.source_kind = str(self.source_kind or "").strip()
        self.workspace_artifact_id = str(self.workspace_artifact_id or "").strip()
        self.multiview_frame_count = max(int(self.multiview_frame_count or 0), 0)
        self.producer_tool = str(self.producer_tool or "").strip()
        if self.multiview_frame_count == 0 and self.frame_refs:
            self.multiview_frame_count = len(self.frame_refs)
        return self

    def suggests_reconstruction(self) -> bool:
        return (
            (self.video_ref is not None and self.video_ref.has_locator())
            or self.multiview_frame_count >= 20
            or len(self.frame_refs) >= 20
        )


class SceneConsistencyContract(BaseModel):
    must_hold: list[str] = Field(default_factory=list)
    allowed_variation: list[str] = Field(default_factory=list)
    degradation_policy: str = "reference_only"

    @model_validator(mode="after")
    def normalize_lists(self) -> "SceneConsistencyContract":
        self.must_hold = _normalize_string_list(self.must_hold)
        self.allowed_variation = _normalize_string_list(self.allowed_variation)
        self.degradation_policy = str(self.degradation_policy or "reference_only").strip()
        return self


class SceneBinding(BaseModel):
    scene_id: str = ""
    scene_scope: str = "default"
    package_id: str = ""
    variant_id: str = "main"

    @model_validator(mode="after")
    def normalize_payload(self) -> "SceneBinding":
        self.scene_id = str(self.scene_id or "").strip()
        self.scene_scope = str(self.scene_scope or "default").strip() or "default"
        self.package_id = str(self.package_id or "").strip()
        self.variant_id = str(self.variant_id or "main").strip() or "main"
        return self


class ScenePackageSelector(BaseModel):
    artifact_id: str = ""
    package_id: str = ""
    scene_scope: str = "default"
    variant_id: str = "main"
    provider: str = ""
    status: str = "generated"
    generation_mode: str = ""

    @model_validator(mode="after")
    def normalize_payload(self) -> "ScenePackageSelector":
        self.artifact_id = str(self.artifact_id or "").strip()
        self.package_id = str(self.package_id or "").strip()
        self.scene_scope = str(self.scene_scope or "default").strip() or "default"
        self.variant_id = str(self.variant_id or "main").strip() or "main"
        self.provider = str(self.provider or "").strip()
        self.status = str(self.status or "generated").strip() or "generated"
        self.generation_mode = str(self.generation_mode or "").strip()
        return self

    def has_selector_fields(self) -> bool:
        return any(
            [
                self.artifact_id,
                self.package_id,
                self.provider,
                self.generation_mode,
                self.scene_scope not in {"", "default"},
                self.variant_id not in {"", "main"},
                self.status not in {"", "generated"},
            ]
        )


class ScenePackageRef(BaseModel):
    artifact_id: str = ""
    package_id: str = ""
    provider: str = ""
    generation_mode: str = ""
    scene_scope: str = "default"
    variant_id: str = "main"
    status: str = "generated"
    source_reference_ids: list[str] = Field(default_factory=list)
    scene_subject_policy: str = ""
    subject_removal_status: str = ""
    swap_ready: bool = False
    control_refs: list[SceneControlRef] = Field(default_factory=list)
    spatial_metadata: SceneSpatialMetadata = Field(default_factory=SceneSpatialMetadata)
    consistency_contract: SceneConsistencyContract = Field(default_factory=SceneConsistencyContract)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_payload(self) -> "ScenePackageRef":
        self.artifact_id = str(self.artifact_id or "").strip()
        self.package_id = str(self.package_id or "").strip()
        self.provider = str(self.provider or "").strip()
        self.generation_mode = str(self.generation_mode or "").strip()
        self.scene_scope = str(self.scene_scope or "default").strip() or "default"
        self.variant_id = str(self.variant_id or "main").strip() or "main"
        self.status = str(self.status or "generated").strip() or "generated"
        self.source_reference_ids = _normalize_string_list(self.source_reference_ids)
        self.scene_subject_policy = str(self.scene_subject_policy or "").strip()
        self.subject_removal_status = str(self.subject_removal_status or "").strip()
        self.swap_ready = bool(self.swap_ready)
        if not isinstance(self.provenance, dict):
            self.provenance = {}
        return self


class SceneSubjectLocator(BaseModel):
    reference_id: str = ""
    frame_index: Optional[int] = None
    person_track_id: str = ""
    bbox: dict[str, int] = Field(default_factory=dict)
    mask_asset_ref: dict[str, Any] = Field(default_factory=dict)
    anchor_asset_ref: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_payload(self) -> "SceneSubjectLocator":
        self.reference_id = str(self.reference_id or "").strip()
        self.frame_index = _normalize_optional_int(self.frame_index)
        self.person_track_id = str(self.person_track_id or "").strip()
        self.bbox = dict(_normalize_bbox_payload(self.bbox) or {})
        if not isinstance(self.mask_asset_ref, dict):
            self.mask_asset_ref = {}
        if not isinstance(self.anchor_asset_ref, dict):
            self.anchor_asset_ref = {}
        if not isinstance(self.provenance, dict):
            self.provenance = {}
        return self


class SceneSubjectRef(BaseModel):
    subject_id: str = ""
    cast_id: str = ""
    role_id: str = ""
    source_reference_ids: list[str] = Field(default_factory=list)
    locators: list[SceneSubjectLocator] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_payload(self) -> "SceneSubjectRef":
        self.subject_id = str(self.subject_id or "").strip()
        self.cast_id = str(self.cast_id or "").strip()
        self.role_id = str(self.role_id or "").strip()
        self.source_reference_ids = _normalize_string_list(self.source_reference_ids)
        self.locators = _normalize_model_list(self.locators, SceneSubjectLocator)
        if not self.subject_id:
            subject_seed = [
                self.cast_id,
                self.role_id,
                *self.source_reference_ids,
            ]
            if subject_seed:
                self.subject_id = f"subj_{_stable_short_hash(*subject_seed)}"
        if not isinstance(self.provenance, dict):
            self.provenance = {}
        return self


class CharacterAdapterSlot(BaseModel):
    slot_id: str = ""
    slot_role: str = ""
    scope_kind: str = ""
    subject_id: str = ""
    role_id: str = ""
    adapter_kind: str = ""
    backend_capability: str = ""
    binding_mode: str = ""
    package_refs: list[dict[str, Any]] = Field(default_factory=list)
    strength: Optional[float] = None
    clip_strength: Optional[float] = None
    source_reference_ids: list[str] = Field(default_factory=list)
    mask_asset_ref: dict[str, Any] = Field(default_factory=dict)
    anchor_asset_ref: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_payload(self) -> "CharacterAdapterSlot":
        self.slot_id = str(self.slot_id or "").strip()
        self.slot_role = str(self.slot_role or "").strip().lower()
        if self.slot_role in CHARACTER_ADAPTER_SLOT_ROLES:
            self.slot_role = self.slot_role
        self.subject_id = str(self.subject_id or "").strip()
        self.role_id = str(self.role_id or "").strip()
        self.adapter_kind = str(self.adapter_kind or "").strip().lower()
        self.backend_capability = str(self.backend_capability or "").strip().lower()
        self.binding_mode = _normalize_choice(
            self.binding_mode,
            CHARACTER_BINDING_MODES,
        )
        self.package_refs = _normalize_structured_dict_list(self.package_refs)
        self.strength = _normalize_optional_float(self.strength)
        self.clip_strength = _normalize_optional_float(self.clip_strength)
        self.source_reference_ids = _normalize_string_list(self.source_reference_ids)
        if not isinstance(self.mask_asset_ref, dict):
            self.mask_asset_ref = {}
        if not isinstance(self.anchor_asset_ref, dict):
            self.anchor_asset_ref = {}
        if not isinstance(self.provenance, dict):
            self.provenance = {}
        normalized_scope = _normalize_choice(
            self.scope_kind,
            CHARACTER_ADAPTER_SCOPE_KINDS,
        )
        if not normalized_scope:
            normalized_scope = "subject" if self.subject_id else "scene"
        self.scope_kind = normalized_scope
        if not self.slot_id:
            slot_seed: list[Any] = [
                self.scope_kind,
                self.subject_id,
                self.role_id,
                self.slot_role,
                self.binding_mode,
            ]
            primary_package_id = ""
            if self.package_refs:
                primary_package_id = str(
                    self.package_refs[0].get("package_id")
                    or self.package_refs[0].get("artifact_id")
                    or ""
                ).strip()
            if primary_package_id:
                slot_seed.append(primary_package_id)
            slot_seed = [part for part in slot_seed if str(part or "").strip()]
            if slot_seed:
                self.slot_id = f"slot_{_stable_short_hash(*slot_seed)}"
        return self


def _build_legacy_character_adapter_slot(
    *,
    binding_mode: str,
    package_refs: list[dict[str, Any]],
    source_reference_ids: list[str],
) -> Optional[CharacterAdapterSlot]:
    normalized_package_refs = _normalize_structured_dict_list(package_refs)
    normalized_binding_mode = _normalize_choice(binding_mode, CHARACTER_BINDING_MODES)
    normalized_source_reference_ids = _normalize_string_list(source_reference_ids)
    if not normalized_package_refs and not normalized_binding_mode:
        return None
    return CharacterAdapterSlot(
        slot_id="legacy_identity_primary",
        slot_role="identity",
        scope_kind="scene",
        binding_mode=normalized_binding_mode,
        package_refs=normalized_package_refs,
        source_reference_ids=normalized_source_reference_ids,
    )


def _legacy_character_adapter_slot_to_mirror(
    slots: list[CharacterAdapterSlot],
) -> Optional[CharacterAdapterSlot]:
    if len(slots) != 1:
        return None
    slot = slots[0]
    if slot.scope_kind != "scene":
        return None
    if slot.slot_role not in {"identity", "identity_face", "identity_body"}:
        return None
    return slot


class WorldInterchangeRef(BaseModel):
    kind: WorldInterchangeKind = WorldInterchangeKind.OPENUSD
    stage_ref: dict[str, Any] = Field(default_factory=dict)
    entry_layer_ref: dict[str, Any] = Field(default_factory=dict)
    layer_refs: list[dict[str, Any]] = Field(default_factory=list)
    variant_selections: dict[str, str] = Field(default_factory=dict)
    composition_metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_payload(self) -> "WorldInterchangeRef":
        if not isinstance(self.stage_ref, dict):
            self.stage_ref = {}
        if not isinstance(self.entry_layer_ref, dict):
            self.entry_layer_ref = {}
        self.layer_refs = _normalize_structured_dict_list(self.layer_refs)
        normalized_variants: dict[str, str] = {}
        if isinstance(self.variant_selections, dict):
            for raw_key, raw_value in self.variant_selections.items():
                key = str(raw_key or "").strip()
                value = str(raw_value or "").strip()
                if key and value:
                    normalized_variants[key] = value
        self.variant_selections = normalized_variants
        if not isinstance(self.composition_metadata, dict):
            self.composition_metadata = {}
        if not isinstance(self.provenance, dict):
            self.provenance = {}
        return self


# ---------------------------------------------------------------------------
# Direction IR (Intermediate Representation)
# ---------------------------------------------------------------------------

class DirectionIR(BaseModel):
    """
    Direction Compilation Intermediate Representation.

    Compiled from references + intent + lenses. Consumed by two renderers:
      - Human Renderer (PD Pack) → performer_cue, shot_card, briefing
      - Generative Renderer (VR) → scene_manifest → clip_refs

    See: Direction Compilation Research §十二
    """
    ir_id: str = Field(default_factory=lambda: f"ir_{uuid.uuid4().hex[:12]}")
    intent: SceneIntent = Field(default_factory=SceneIntent)
    must_preserve: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    free_variation: list[str] = Field(default_factory=list)
    avoid_failure_modes: list[str] = Field(default_factory=list)
    composition_anchors: list[str] = Field(default_factory=list)
    style_anchors: list[str] = Field(default_factory=list)
    subject_anchors: list[str] = Field(default_factory=list)
    role_requirements: list[dict[str, Any]] = Field(default_factory=list)
    character_bindings: list[dict[str, Any]] = Field(default_factory=list)
    scene_subjects: list[SceneSubjectRef] = Field(default_factory=list)
    character_adapter_slots: list[CharacterAdapterSlot] = Field(default_factory=list)
    character_package_refs: list[dict[str, Any]] = Field(default_factory=list)
    character_binding_mode: str = ""
    performance_requirements: list[str] = Field(default_factory=list)
    performance_bindings: list[dict[str, Any]] = Field(default_factory=list)
    performance_package_refs: list[dict[str, Any]] = Field(default_factory=list)
    speaker_audio_refs: list[dict[str, Any]] = Field(default_factory=list)
    driving_clip_refs: list[dict[str, Any]] = Field(default_factory=list)
    performance_mode: str = ""
    runtime_capability_requirements: list[str] = Field(default_factory=list)
    review_prerequisites: list[str] = Field(default_factory=list)
    performance_replay_scope: str = ""
    require_retargetable_performance_replay: bool = False
    scene_generation_requirements: list[str] = Field(default_factory=list)
    scene_bindings: list[SceneBinding] = Field(default_factory=list)
    scene_package_refs: list[ScenePackageRef] = Field(default_factory=list)
    object_targets: list[ObjectTarget] = Field(default_factory=list)
    object_constraints: list[str] = Field(default_factory=list)
    source_reference_ids: list[str] = Field(default_factory=list)
    subject_reference_ids: list[str] = Field(default_factory=list)
    lens_stack: list[dict[str, Any]] = Field(default_factory=list)
    runtime_hints: dict[str, Any] = Field(default_factory=dict)
    compilation_provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_extended_contract(self) -> "DirectionIR":
        self.role_requirements = _normalize_structured_dict_list(
            self.role_requirements
        )
        self.character_bindings = _normalize_structured_dict_list(
            self.character_bindings
        )
        self.scene_subjects = _normalize_model_list(
            self.scene_subjects,
            SceneSubjectRef,
        )
        self.character_adapter_slots = _normalize_model_list(
            self.character_adapter_slots,
            CharacterAdapterSlot,
        )
        self.character_package_refs = _normalize_structured_dict_list(
            self.character_package_refs
        )
        self.character_binding_mode = _normalize_choice(
            self.character_binding_mode,
            CHARACTER_BINDING_MODES,
        )
        if not self.character_adapter_slots:
            legacy_slot = _build_legacy_character_adapter_slot(
                binding_mode=self.character_binding_mode,
                package_refs=self.character_package_refs,
                source_reference_ids=(
                    self.subject_reference_ids or self.source_reference_ids
                ),
            )
            if legacy_slot is not None:
                self.character_adapter_slots = [legacy_slot]
        elif not self.character_package_refs and not self.character_binding_mode:
            mirrored_legacy_slot = _legacy_character_adapter_slot_to_mirror(
                self.character_adapter_slots
            )
            if mirrored_legacy_slot is not None:
                self.character_package_refs = _normalize_structured_dict_list(
                    mirrored_legacy_slot.package_refs
                )
                self.character_binding_mode = mirrored_legacy_slot.binding_mode
        self.performance_requirements = _normalize_string_list(
            self.performance_requirements
        )
        self.performance_bindings = _normalize_structured_dict_list(
            self.performance_bindings
        )
        self.performance_package_refs = _normalize_structured_dict_list(
            self.performance_package_refs
        )
        self.speaker_audio_refs = _normalize_structured_dict_list(
            self.speaker_audio_refs
        )
        self.driving_clip_refs = _normalize_structured_dict_list(
            self.driving_clip_refs
        )
        self.performance_mode = _normalize_choice(
            self.performance_mode,
            PERFORMANCE_MODES,
        )
        self.runtime_capability_requirements = _normalize_string_list(
            self.runtime_capability_requirements
        )
        self.review_prerequisites = _normalize_string_list(
            self.review_prerequisites
        )
        self.performance_replay_scope = _normalize_choice(
            self.performance_replay_scope,
            PERFORMANCE_REPLAY_SCOPES,
        )
        self.require_retargetable_performance_replay = bool(
            self.require_retargetable_performance_replay
        )
        self.scene_generation_requirements = _normalize_string_list(
            self.scene_generation_requirements
        )
        self.source_reference_ids = _normalize_string_list(self.source_reference_ids)
        self.subject_reference_ids = _normalize_string_list(
            self.subject_reference_ids
        )
        return self


# ---------------------------------------------------------------------------
# Scene — Atomic unit of Storyboard
# ---------------------------------------------------------------------------

class Scene(BaseModel):
    """Single scene — the atomic unit of a Storyboard."""
    scene_id: str = Field(default_factory=lambda: f"sc_{uuid.uuid4().hex[:8]}")

    # VR consumes this: prompt, dimensions, etc.
    scene_manifest: dict[str, Any] = Field(default_factory=dict)

    # PD fills this
    intent: Optional[SceneIntent] = None
    duration_sec: float = 5.0
    energy_level: float = 0.5           # 0.0–1.0

    # References (L0–L4)
    reference_ids: list[str] = Field(default_factory=list)

    # Direction IR (if compiled from Direction Compilation pipeline)
    direction_ir: Optional[DirectionIR] = None
    scene_package_selector: Optional[ScenePackageSelector] = None
    scene_package_ref: Optional[ScenePackageRef] = None
    world_interchange_refs: list[WorldInterchangeRef] = Field(default_factory=list)
    motion_receipt: Optional[MotionGenerationReceipt] = None
    scene_consistency_contract: SceneConsistencyContract = Field(
        default_factory=SceneConsistencyContract
    )
    object_assets: list[ObjectAssetRef] = Field(default_factory=list)
    object_reuse_plan: Optional[ObjectReusePlan] = None
    object_workload_snapshot: Optional[ObjectWorkloadSnapshot] = None

    # Voice + soundscape cues
    cue_assets: Optional[CueAssets] = None

    # VR / Human renderer fills this
    clip_refs: list[ClipRef] = Field(default_factory=list)

    # Scene-to-scene transitions
    transitions: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# StoryboardManifest — The top-level shared contract
# ---------------------------------------------------------------------------

class StoryboardManifest(BaseModel):
    """
    Complete storyboard — the cross-pack shared contract.

    Produced by: performance_direction (pd_storyboard_gen)
    Consumed by: video_renderer (per-scene render), multi_media_studio (timeline assembly)
    """
    storyboard_id: str = Field(default_factory=lambda: f"sb_{uuid.uuid4().hex[:12]}")
    workspace_id: str = ""
    scenes: list[Scene] = Field(default_factory=list)
    render_profile: Optional[RenderProfile] = None
    global_settings: dict[str, Any] = Field(default_factory=dict)
    status: StoryboardStatus = StoryboardStatus.DRAFT
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
