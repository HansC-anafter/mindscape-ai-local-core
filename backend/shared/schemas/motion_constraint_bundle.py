"""
Motion Shared Contract — Constraint Bundle

Vendored into local-core so installed capability packs can resolve
``shared.schemas.motion_constraint_bundle`` without requiring the cloud repo at runtime.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .motion_artifact_refs import MotionArtifactRef


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
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["MotionConstraintBundle"]
