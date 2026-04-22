"""Cross-pack shared schemas."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from backend.shared.schemas.spatial_scheduling import (
    SPATIAL_CONSTRAINT_SECTION_KEYS,
    SPATIAL_SCHEDULING_SCHEMA_VERSION,
    SpatialAnchor,
    SpatialConstraintItem,
    SpatialConstraintSummary,
    SpatialConsumerPromptSegment,
    SpatialEntityRef,
    SpatialScheduleSegment,
    SpatialSchedulingIR,
)

__all__ = [
    "SPATIAL_CONSTRAINT_SECTION_KEYS",
    "SPATIAL_SCHEDULING_SCHEMA_VERSION",
    "SpatialAnchor",
    "SpatialConstraintItem",
    "SpatialConstraintSummary",
    "SpatialConsumerPromptSegment",
    "SpatialEntityRef",
    "SpatialScheduleSegment",
    "SpatialSchedulingIR",
]
