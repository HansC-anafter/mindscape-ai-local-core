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

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


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
