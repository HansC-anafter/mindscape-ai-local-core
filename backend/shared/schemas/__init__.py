"""Cross-pack shared schemas."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from backend.shared.schemas.spatial_scheduling import (
    SPATIAL_SCHEDULING_SCHEMA_VERSION,
    SpatialAnchor,
    SpatialEntityRef,
    SpatialScheduleSegment,
    SpatialSchedulingIR,
)

__all__ = [
    "SPATIAL_SCHEDULING_SCHEMA_VERSION",
    "SpatialAnchor",
    "SpatialEntityRef",
    "SpatialScheduleSegment",
    "SpatialSchedulingIR",
]
