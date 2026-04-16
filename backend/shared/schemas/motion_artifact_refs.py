"""
Motion Shared Contract — Artifact References

Provider-neutral artifact ref envelope for motion outputs.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class MotionArtifactKind(str, Enum):
    PREVIEW = "preview"
    MOTION_NPZ = "motion_npz"
    MOTION_BVH = "motion_bvh"
    MOTION_FBX = "motion_fbx"
    ROOT_TRAJECTORY = "root_trajectory"
    FOOT_CONTACT = "foot_contact"
    CONSTRAINT_BUNDLE = "constraint_bundle"


class MotionArtifactRef(BaseModel):
    artifact_kind: str = Field(..., description="Portable motion artifact kind")
    format: str = Field(..., description="Artifact format such as npz, bvh, fbx, mp4")
    storage_key: Optional[str] = Field(None)
    file_path: Optional[str] = Field(None)
    reference_id: Optional[str] = Field(None)
    ig_reference_id: Optional[str] = Field(None)
    url: Optional[str] = Field(None)
    skeleton_family: Optional[str] = Field(
        None, description="Rig family such as soma, mixamo, ue_mannequin"
    )
    skeleton_version: Optional[str] = Field(
        None, description="Backend-specific rig version tag"
    )
    coordinate_space: Optional[str] = Field(
        None, description="Coordinate space hint such as y_up or z_up"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_locator(self) -> "MotionArtifactRef":
        if any(
            str(value or "").strip()
            for value in (
                self.storage_key,
                self.file_path,
                self.reference_id,
                self.ig_reference_id,
                self.url,
            )
        ):
            return self
        raise ValueError(
            "MotionArtifactRef requires one locator: storage_key, file_path, "
            "reference_id, ig_reference_id, or url"
        )


__all__ = ["MotionArtifactKind", "MotionArtifactRef"]
