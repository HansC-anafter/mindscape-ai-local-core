"""
Motion Shared Contract — Generation Contract

Provider-neutral request envelope between upstream orchestration and motion_runtime.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .motion_artifact_refs import MotionArtifactRef
from .motion_constraint_bundle import MotionConstraintBundle


def _new_contract_id() -> str:
    return f"mcontract_{uuid4().hex[:12]}"


class MotionPromptSegment(BaseModel):
    text: str = Field(..., description="Natural-language or symbolic prompt segment")
    role: str = Field(
        "instruction",
        description="Segment role such as instruction, style, timing, or safety",
    )
    weight: float = Field(1.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MotionGenerationContract(BaseModel):
    contract_id: str = Field(default_factory=_new_contract_id)
    workspace_id: str = Field(..., description="Workspace identifier")
    source_family: str = Field(
        "text_to_motion",
        description="Neutral source family such as text_to_motion or midi_phrase_motion",
    )
    prompt_segments: list[MotionPromptSegment] = Field(default_factory=list)
    constraint_bundle: Optional[MotionConstraintBundle] = Field(None)
    constraint_refs: list[MotionArtifactRef] = Field(default_factory=list)
    duration_sec: float = Field(4.0, gt=0.0)
    fps: int = Field(30, ge=1)
    seed: Optional[int] = Field(None)
    artifact_policy: dict[str, Any] = Field(default_factory=dict)
    target_skeleton_family: Optional[str] = Field(None)
    coordinate_space: str = Field("y_up")
    retarget_profile: Optional[str] = Field(None)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["MotionGenerationContract", "MotionPromptSegment"]
