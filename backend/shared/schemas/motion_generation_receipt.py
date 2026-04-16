"""
Motion Shared Contract — Generation Receipt

Provider-neutral normalized result envelope emitted by motion_runtime.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .motion_artifact_refs import MotionArtifactRef


def _new_motion_id() -> str:
    return f"motion_{uuid4().hex[:12]}"


class MotionGenerationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MotionGenerationReceipt(BaseModel):
    motion_id: str = Field(default_factory=_new_motion_id)
    provider: str = Field(..., description="Concrete backend provider label")
    source_family: str = Field("text_to_motion")
    status: str = Field(MotionGenerationStatus.COMPLETED.value)
    duration_sec: float = Field(..., ge=0.0)
    fps: int = Field(..., ge=1)
    skeleton_family: Optional[str] = Field(None)
    skeleton_version: Optional[str] = Field(None)
    coordinate_space: Optional[str] = Field(None)
    retarget_profile: Optional[str] = Field(None)
    root_trajectory_ref: Optional[MotionArtifactRef] = Field(None)
    foot_contact_ref: Optional[MotionArtifactRef] = Field(None)
    artifact_refs: list[MotionArtifactRef] = Field(default_factory=list)
    timing_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["MotionGenerationReceipt", "MotionGenerationStatus"]
