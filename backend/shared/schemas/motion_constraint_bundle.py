"""
Motion Shared Contract — Constraint Bundle

Bounded policy envelope for portable motion generation constraints.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from .motion_artifact_refs import MotionArtifactRef


class MotionConstraintType(str, Enum):
    ROOT2D = "root2d"
    FULLBODY = "fullbody"
    LEFT_HAND = "left-hand"
    RIGHT_HAND = "right-hand"
    LEFT_FOOT = "left-foot"
    RIGHT_FOOT = "right-foot"


_END_EFFECTOR_TYPES = {
    MotionConstraintType.LEFT_HAND.value,
    MotionConstraintType.RIGHT_HAND.value,
    MotionConstraintType.LEFT_FOOT.value,
    MotionConstraintType.RIGHT_FOOT.value,
}


class MotionConstraintObject(BaseModel):
    type: MotionConstraintType = Field(..., description="Typed neutral motion constraint")
    frame_indices: list[int] = Field(default_factory=list)
    smooth_root_2d: list[list[float]] = Field(default_factory=list)
    global_root_heading: list[list[float]] = Field(default_factory=list)
    local_joints_rot: list[list[list[float]]] = Field(default_factory=list)
    root_positions: list[list[float]] = Field(default_factory=list)
    skeleton_family: Optional[str] = Field(None)
    skeleton_version: Optional[str] = Field(None)
    coordinate_space: Optional[str] = Field(None)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_constraint_payload(self) -> "MotionConstraintObject":
        if not self.frame_indices:
            raise ValueError("MotionConstraintObject.frame_indices must not be empty")
        if any(int(index) < 0 for index in self.frame_indices):
            raise ValueError("MotionConstraintObject.frame_indices must be >= 0")

        frame_count = len(self.frame_indices)
        constraint_type = self.type.value

        if constraint_type == MotionConstraintType.ROOT2D.value:
            if not self.smooth_root_2d:
                raise ValueError("root2d constraints require smooth_root_2d")
            if len(self.smooth_root_2d) != frame_count:
                raise ValueError("root2d smooth_root_2d length must match frame_indices")
            if self.global_root_heading and len(self.global_root_heading) != frame_count:
                raise ValueError(
                    "root2d global_root_heading length must match frame_indices"
                )
            return self

        if not self.local_joints_rot:
            raise ValueError(
                f"{constraint_type} constraints require local_joints_rot"
            )
        if not self.root_positions:
            raise ValueError(f"{constraint_type} constraints require root_positions")
        if len(self.local_joints_rot) != frame_count:
            raise ValueError(
                f"{constraint_type} local_joints_rot length must match frame_indices"
            )
        if len(self.root_positions) != frame_count:
            raise ValueError(
                f"{constraint_type} root_positions length must match frame_indices"
            )
        if self.smooth_root_2d and len(self.smooth_root_2d) != frame_count:
            raise ValueError(
                f"{constraint_type} smooth_root_2d length must match frame_indices"
            )
        return self

    @property
    def is_end_effector(self) -> bool:
        return self.type.value in _END_EFFECTOR_TYPES


class MotionConstraintBundle(BaseModel):
    constraint_bundle_id: str = Field(..., description="Constraint bundle identifier")
    source_family: str = Field(
        "text_constraints",
        description="Constraint source family such as text_constraints or midi_phrase",
    )
    timing_policy: dict[str, Any] = Field(default_factory=dict)
    contact_policy: dict[str, Any] = Field(default_factory=dict)
    spatial_policy: dict[str, Any] = Field(default_factory=dict)
    constraint_refs: list[MotionArtifactRef] = Field(default_factory=list)
    constraint_objects: list[MotionConstraintObject] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "MotionConstraintBundle",
    "MotionConstraintObject",
    "MotionConstraintType",
]
