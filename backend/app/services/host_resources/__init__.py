"""Host resource control-plane helpers."""

from .advisor import (
    HostResourceAdvice,
    build_admission_preview,
    evaluate_runner_requirements,
)
from .manager import (
    cancel_route_reservation,
    create_route_reservation,
    get_host_resource_snapshot,
    list_active_route_reservations,
    list_host_resource_lanes,
    resume_lane,
    pause_lane,
)

__all__ = [
    "HostResourceAdvice",
    "build_admission_preview",
    "cancel_route_reservation",
    "create_route_reservation",
    "evaluate_runner_requirements",
    "get_host_resource_snapshot",
    "list_active_route_reservations",
    "list_host_resource_lanes",
    "pause_lane",
    "resume_lane",
]
